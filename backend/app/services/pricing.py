"""
Pricing engine — converts model scores into fair odds and computes edge vs market.

This is the keystone: without it, "score 75" is just a number. With it, every pick
becomes a measurable hypothesis (our_prob vs market_prob → edge in %).

Calibration (initial — should be refined from tracked results once we have n>200):
  - Score 50 → market-neutral probability (no edge)
  - Score 100 → maximum reasonable model edge (~10% over market)
  - Score   0 → maximum anti-signal (model says PASS)

The edge tiers (CRUSH / EDGE / FAIR / PASS) drive filtering downstream — only
EDGE-or-better legs should appear in parlays once we trust the calibration.
"""
from typing import Optional


# ── Probability ↔ American odds (vig-stripped where noted) ───────────────────

def american_to_prob(american: int) -> float:
    """Convert American odds to implied probability (includes book vig)."""
    if american >= 0:
        return 100.0 / (american + 100.0)
    return -american / (-american + 100.0)


def prob_to_american(prob: float) -> int:
    """Convert true probability to fair American odds (no vig)."""
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return int(round(-100.0 * prob / (1.0 - prob)))
    return int(round(100.0 * (1.0 - prob) / prob))


def devig_two_way(p1: float, p2: float) -> tuple[float, float]:
    """Strip the vig from a two-way market by normalizing the implied probs."""
    s = p1 + p2
    if s <= 0:
        return p1, p2
    return p1 / s, p2 / s


# ── Score → probability (the model's "fair" estimate) ────────────────────────

# Slope: how much each point of score moves probability vs the 50% neutral baseline.
# At slope = 0.0024, score=100 → 62% (12% above neutral). Justified by the fact
# that a real edge in MLB unders rarely exceeds 8-10% on a per-bet basis.
_UNDER_SLOPE = 0.0024
_DOG_SLOPE   = 0.0016   # dogs harder to move — smaller swings
_FAV_SLOPE   = 0.0014   # fav-cover lift smaller still (RL is already favored math)


def under_prob_from_score(under_score_100: float) -> float:
    """Convert 0-100 under_score → model's probability the under hits."""
    p = 0.50 + (under_score_100 - 50.0) * _UNDER_SLOPE
    return max(0.30, min(0.70, p))


def dog_win_prob_from_score(dog_score_100: float, market_ml: Optional[int]) -> float:
    """
    Convert dog_score (0-100) and the market moneyline into our model's win prob.
    Anchors on market ML (already pretty efficient) and adjusts by score.
    """
    if market_ml is None:
        # No market — score-only estimate (rarely usable but doesn't crash)
        return max(0.30, min(0.55, 0.40 + (dog_score_100 - 50.0) * 0.0020))
    base = american_to_prob(market_ml)
    p = base + (dog_score_100 - 50.0) * _DOG_SLOPE
    return max(0.30, min(0.65, p))


def fav_cover_prob_from_score(
    fav_score_100: float,
    market_ml: Optional[int],
    rl_runs: float = 1.5,
) -> float:
    """
    Convert fav_score + ML → probability the favorite covers the run line.
    Larger run lines (-2.5, -3.5) drop the base cover probability sharply.
    """
    if market_ml is None:
        base = 0.45
    else:
        fav_prob = american_to_prob(market_ml)
        # Cover rate at -1.5 is roughly fav_ml_prob - 0.18 (empirical MLB avg)
        if rl_runs <= 1.5:
            base = fav_prob - 0.18
        elif rl_runs <= 2.5:
            base = fav_prob - 0.32
        else:
            base = fav_prob - 0.45
    p = base + (fav_score_100 - 50.0) * _FAV_SLOPE
    return max(0.10, min(0.65, p))


def dog_rl_cover_prob_from_ml(market_ml: Optional[int]) -> float:
    """+1.5 RL cover probability for a dog at a given ML. Empirical lift ~18%."""
    if market_ml is None:
        return 0.66  # generic dog +1.5 cover rate
    win_prob = american_to_prob(market_ml)
    return max(0.50, min(0.90, win_prob + 0.20))


# ── Edge math (the whole point) ──────────────────────────────────────────────

def edge_pct(our_prob: float, market_american: int) -> float:
    """
    Edge = (our_prob × payout_multiple) - (1 - our_prob)
    Returns expected return per $1 bet, as a percentage.
    Positive = +EV bet, negative = lose money on average.
    """
    if market_american >= 0:
        payout = market_american / 100.0
    else:
        payout = 100.0 / -market_american
    ev = our_prob * payout - (1.0 - our_prob)
    return round(ev * 100.0, 2)


def classify_edge(edge_percent: float) -> dict:
    """
    Translate EV % into a human-readable tier.
    CRUSH    +8%+  — only the most mispriced lines
    EDGE     +3-8% — solid +EV plays
    FAIR     0-3%  — flat-to-marginal
    PASS     <0%   — book has us; should be filtered out
    """
    if edge_percent >= 8.0:
        return {"tier": "CRUSH", "color": "#00ff87", "icon": "💎"}
    if edge_percent >= 3.0:
        return {"tier": "EDGE",  "color": "#a3e635", "icon": "📈"}
    if edge_percent >= 0.0:
        return {"tier": "FAIR",  "color": "#fbbf24", "icon": "⚖️"}
    return {"tier": "PASS", "color": "#ef4444", "icon": "🚫"}


# ── Public helper: compute the full edge bundle for one leg ──────────────────

def price_leg(our_prob: float, market_american: Optional[int]) -> dict:
    """
    Returns the standard edge bundle attached to every parlay leg:
      - our_fair_odds : what we'd price this bet at
      - market_odds   : the market price (may be None if not posted)
      - edge_pct      : EV % per $1 risked (None if no market)
      - tier          : CRUSH / EDGE / FAIR / PASS / UNPRICED
      - color / icon  : UI hints
    """
    fair = prob_to_american(our_prob)
    if market_american is None:
        return {
            "our_fair_odds": fair,
            "market_odds": None,
            "edge_pct": None,
            "tier": "UNPRICED",
            "color": "#666",
            "icon": "❓",
            "our_prob": round(our_prob, 4),
        }
    e = edge_pct(our_prob, market_american)
    cls = classify_edge(e)
    return {
        "our_fair_odds": fair,
        "market_odds": market_american,
        "edge_pct": e,
        "tier": cls["tier"],
        "color": cls["color"],
        "icon": cls["icon"],
        "our_prob": round(our_prob, 4),
    }
