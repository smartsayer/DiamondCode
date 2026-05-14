from typing import Any, Optional

"""
EDGE Engine — pre-flop chip-stack plays.

Three scorers built around the philosophy of starting every game already ahead:

  1. NRFI    — No Run First Inning. If it hits, you're winning by minute 10.
  2. F5      — First 5 innings under. Isolates to highest-certainty data
              (the two starting pitchers); removes bullpen + late-game noise.
  3. TEAM TOTAL — Single-side under. Only ONE team has to underperform.
"""

NRFI_VERDICTS = [
    (72, "NRFI Lock"),
    (62, "NRFI Strong"),
    (54, "NRFI Lean"),
    (0,  "Pass"),
]

F5_VERDICTS = [
    (78, "F5 Lock"),
    (66, "F5 Strong"),
    (55, "F5 Moderate"),
    (0,  "F5 Skip"),
]

TT_VERDICTS = [
    (75, "TT Lock"),
    (63, "TT Strong"),
    (52, "TT Lean"),
    (0,  "TT Skip"),
]

LATE_VERDICTS = [
    (76, "Pen Lock"),
    (64, "Pen Strong"),
    (54, "Pen Lean"),
    (0,  "Pen Skip"),
]


class EdgeEngine:

    def score_nrfi(
        self,
        away_pitcher: dict[str, Any],
        home_pitcher: dict[str, Any],
        away_offense: dict[str, Any],
        home_offense: dict[str, Any],
        umpire_data: dict[str, Any],
        weather_data: dict[str, Any],
        park_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        NRFI probability — both teams scoreless in inning 1.

        P(NRFI) = P(away no run T1) × P(home no run B1)
        Each side ≈ base 76% adjusted by: opposing pitcher K% / recent form,
        top of order K%, ump zone, weather, park.
        """
        # Probability home pitcher holds away offense scoreless in T1
        away_held = self._side_holds_scoreless(
            pitcher=home_pitcher,
            opposing_offense=away_offense,
            ump=umpire_data,
            weather=weather_data,
            park=park_data,
        )
        # Probability away pitcher holds home offense scoreless in B1
        home_held = self._side_holds_scoreless(
            pitcher=away_pitcher,
            opposing_offense=home_offense,
            ump=umpire_data,
            weather=weather_data,
            park=park_data,
        )
        nrfi_prob = round(away_held * home_held * 100, 1)

        return {
            "nrfi_probability": nrfi_prob,
            "away_pitcher_hold_pct": round(away_held * 100, 1),
            "home_pitcher_hold_pct": round(home_held * 100, 1),
            "verdict": self._verdict(nrfi_prob, NRFI_VERDICTS),
            "key_factors": self._nrfi_factors(
                away_pitcher, home_pitcher, away_offense, home_offense, umpire_data
            ),
        }

    def score_f5(
        self,
        away_pitcher: dict[str, Any],
        home_pitcher: dict[str, Any],
        away_offense: dict[str, Any],
        home_offense: dict[str, Any],
        park_data: dict[str, Any],
        weather_data: dict[str, Any],
        umpire_data: dict[str, Any],
        full_game_total: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        F5 under score 0-100. Heavily weighted on starting pitcher quality.
        Removes bullpen and late-game variance entirely.

        Weights:
          Pitcher Quality   50%
          Team Offense      18%  (top-of-order tiers face starters in F5)
          Park              12%
          Weather           10%
          Umpire            10%
        """
        pitcher_score = (
            self._u(away_pitcher) + self._u(home_pitcher)
        ) / 2.0
        offense_score = (self._u(away_offense) + self._u(home_offense)) / 2.0
        park_score = self._u(park_data)
        weather_score = self._u(weather_data)
        umpire_score = self._u(umpire_data)

        weighted = (
            pitcher_score * 0.50 +
            offense_score * 0.18 +
            park_score    * 0.12 +
            weather_score * 0.10 +
            umpire_score  * 0.10
        ) * 10.0
        f5_score = round(max(0.0, min(100.0, weighted)), 1)

        # F5 line typically 55-58% of full game total
        projected_f5_line = round(full_game_total * 0.56, 1) if full_game_total else None

        return {
            "f5_score": f5_score,
            "verdict": self._verdict(f5_score, F5_VERDICTS),
            "projected_f5_line": projected_f5_line,
            "components": {
                "pitcher": round(pitcher_score, 2),
                "offense": round(offense_score, 2),
                "park": round(park_score, 2),
                "weather": round(weather_score, 2),
                "umpire": round(umpire_score, 2),
            },
        }

    def score_team_totals(
        self,
        away_team: str,
        home_team: str,
        away_offense: dict[str, Any],
        home_offense: dict[str, Any],
        away_pitcher: dict[str, Any],
        home_pitcher: dict[str, Any],
        away_bullpen: dict[str, Any],
        home_bullpen: dict[str, Any],
        park_data: dict[str, Any],
        weather_data: dict[str, Any],
        full_game_total: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Score each team's individual under as a standalone bet.
        Good when ONE team is cold/facing an ace but the other side is a coin flip.
        """
        away_tt = self._team_under_score(
            team_offense=away_offense,
            opposing_pitcher=home_pitcher,
            opposing_bullpen=home_bullpen,
            park=park_data,
            weather=weather_data,
        )
        home_tt = self._team_under_score(
            team_offense=home_offense,
            opposing_pitcher=away_pitcher,
            opposing_bullpen=away_bullpen,
            park=park_data,
            weather=weather_data,
        )

        # Suggested team total line: half of full game ± offense skew
        away_proj = round(full_game_total / 2.0 - 0.25, 1) if full_game_total else None
        home_proj = round(full_game_total / 2.0 + 0.25, 1) if full_game_total else None

        # Identify the better side
        if away_tt["score"] >= home_tt["score"]:
            best_side, best_team = "away", away_team
            best_score = away_tt["score"]
            best_verdict = away_tt["verdict"]
            best_line = away_proj
        else:
            best_side, best_team = "home", home_team
            best_score = home_tt["score"]
            best_verdict = home_tt["verdict"]
            best_line = home_proj

        return {
            "away_tt_score": away_tt["score"],
            "away_tt_verdict": away_tt["verdict"],
            "home_tt_score": home_tt["score"],
            "home_tt_verdict": home_tt["verdict"],
            "best_side": best_side,
            "best_team": best_team,
            "best_score": best_score,
            "best_verdict": best_verdict,
            "best_projected_total": best_line,
            "away_projected_total": away_proj,
            "home_projected_total": home_proj,
        }

    def score_late_innings(
        self,
        away_pitcher: dict[str, Any],
        home_pitcher: dict[str, Any],
        away_bullpen: dict[str, Any],
        home_bullpen: dict[str, Any],
        away_offense: dict[str, Any],
        home_offense: dict[str, Any],
        park_data: dict[str, Any],
        weather_data: dict[str, Any],
        umpire_data: dict[str, Any],
        full_game_total: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Bullpen-leveraged full 9-inning under score.

        Why this exists: F5 markets have thin liquidity and worse pricing.
        The full 9 line is where the volume is. Innings 6-9 are 100% bullpen,
        and bullpen quality + freshness is the single biggest swing factor in
        late-game scoring. This scorer over-weights bullpen relative to the
        main slate model so you can find unders the full-game line is mispricing.

        Weights:
          Bullpen Quality + Fatigue (both)   35%
          Starter Quality (depth proxy)      20%
          Park Factor                        12%
          Weather                            10%
          Team Offense (both)                10%
          Bullpen Disparity Penalty           8%
          Umpire                              5%
        """
        # Combined bullpen score — both teams averaged
        away_pen = self._u(away_bullpen)
        home_pen = self._u(home_bullpen)
        bullpen_combined = (away_pen + home_pen) / 2.0

        # Disparity penalty — if one bullpen is gassed, late innings get ugly
        # even if the other is fresh. Take the WORSE bullpen as a constraint.
        weaker_pen = min(away_pen, home_pen)
        # Reward when both pens are at least decent (>=6.0)
        floor_bonus = 1.0 if weaker_pen >= 6.0 else 0.0
        # Penalize hard when either pen is gassed (<=3.5)
        gassed_penalty = -1.5 if weaker_pen <= 3.5 else 0.0
        disparity_score = max(0.0, min(10.0, weaker_pen + floor_bonus + gassed_penalty))

        # Starter quality acts as a depth proxy — efficient starters limit
        # bullpen exposure, amplifying the bullpen edge
        starter_score = (self._u(away_pitcher) + self._u(home_pitcher)) / 2.0
        offense_score = (self._u(away_offense) + self._u(home_offense)) / 2.0
        park_score = self._u(park_data)
        weather_score = self._u(weather_data)
        umpire_score = self._u(umpire_data)

        weighted = (
            bullpen_combined * 0.35 +
            starter_score    * 0.20 +
            park_score       * 0.12 +
            weather_score    * 0.10 +
            offense_score    * 0.10 +
            disparity_score  * 0.08 +
            umpire_score     * 0.05
        ) * 10.0

        late_score = round(max(0.0, min(100.0, weighted)), 1)

        return {
            "late_score": late_score,
            "verdict": self._verdict(late_score, LATE_VERDICTS),
            "full_game_total": full_game_total,
            "components": {
                "bullpen_combined": round(bullpen_combined, 2),
                "weaker_bullpen": round(weaker_pen, 2),
                "starter_avg": round(starter_score, 2),
                "park": round(park_score, 2),
                "weather": round(weather_score, 2),
                "offense_avg": round(offense_score, 2),
                "umpire": round(umpire_score, 2),
            },
            "notes": self._late_notes(away_bullpen, home_bullpen, away_pitcher, home_pitcher),
        }

    def _late_notes(self, ap_bp, hp_bp, ap, hp) -> list[str]:
        """Plain-English bullpen + starter context for the full-game under play."""
        notes = []

        # Bullpen freshness
        away_ip = ap_bp.get("total_recent_ip", 0.0) if ap_bp else 0.0
        home_ip = hp_bp.get("total_recent_ip", 0.0) if hp_bp else 0.0
        away_pct = ap_bp.get("pct_fatigued", 0.0) if ap_bp else 0.0
        home_pct = hp_bp.get("pct_fatigued", 0.0) if hp_bp else 0.0

        if away_ip <= 2.0 and home_ip <= 2.0:
            notes.append(f"Both pens fresh ({away_ip}/{home_ip} IP last 3d)")
        else:
            if away_ip >= 5.0:
                notes.append(f"Away pen taxed ({away_ip} IP last 3d)")
            if home_ip >= 5.0:
                notes.append(f"Home pen taxed ({home_ip} IP last 3d)")

        if away_pct >= 0.5:
            notes.append(f"{int(away_pct*100)}% of away pen used recently")
        if home_pct >= 0.5:
            notes.append(f"{int(home_pct*100)}% of home pen used recently")

        # Starter depth proxy via K%
        away_k = ap.get("k_pct", 22.0) if ap else 22.0
        home_k = hp.get("k_pct", 22.0) if hp else 22.0
        if away_k >= 28 and home_k >= 28:
            notes.append("Both SP high-K — should pitch deep")
        elif min(away_k, home_k) <= 18:
            notes.append("Low-K starter — early bullpen exposure likely")

        return notes

    # ── internals ─────────────────────────────────────────────────────────────

    def _side_holds_scoreless(
        self,
        pitcher: dict[str, Any],
        opposing_offense: dict[str, Any],
        ump: dict[str, Any],
        weather: dict[str, Any],
        park: dict[str, Any],
    ) -> float:
        """Probability this pitcher holds the opposing lineup scoreless in 1 inning."""
        # Base MLB single-half-inning scoreless rate is ~76%
        prob = 0.76

        # Pitcher quality drives the largest swing
        p_score = self._u(pitcher)  # 0-10
        prob += (p_score - 5.0) * 0.018  # ±9% range

        # Pitcher recent trend (already baked into pitcher under_score via recent_form_adjustment)
        # but we can amplify cold/dominant trends slightly
        trend = pitcher.get("recent_trend", "neutral")
        if trend == "dominant":
            prob += 0.025
        elif trend == "hot":
            prob += 0.012
        elif trend == "struggling":
            prob -= 0.020
        elif trend == "cold":
            prob -= 0.040

        # Opposing offense quality (low rpg = easier to hold scoreless)
        rpg = opposing_offense.get("runs_per_game_10d", 4.5) if opposing_offense else 4.5
        prob += (4.5 - rpg) * 0.015  # cold offense bumps prob

        # Strikeout-heavy opposing lineup (high K% lineups score less in 1st)
        k_pct = opposing_offense.get("k_pct_season", 22.0) / 100.0 if opposing_offense else 0.22
        prob += (k_pct - 0.22) * 0.30

        # Umpire zone (wide zone = strikeouts up = more holds)
        ump_score = self._u(ump)  # 5.0 neutral, higher = more pitcher-friendly
        prob += (ump_score - 5.0) * 0.008

        # Weather (under-friendly weather slightly helps NRFI)
        w_score = self._u(weather)
        prob += (w_score - 5.0) * 0.005

        # Park factor
        park_score = self._u(park)
        prob += (park_score - 5.0) * 0.004

        return max(0.50, min(0.94, prob))

    def _team_under_score(
        self,
        team_offense: dict[str, Any],
        opposing_pitcher: dict[str, Any],
        opposing_bullpen: dict[str, Any],
        park: dict[str, Any],
        weather: dict[str, Any],
    ) -> dict[str, Any]:
        # Heavier weight on the team's own offense + the pitcher they face
        offense_under = self._u(team_offense)
        pitcher_under = self._u(opposing_pitcher)
        bullpen_under = self._u(opposing_bullpen)
        park_under = self._u(park)
        weather_under = self._u(weather)

        weighted = (
            offense_under * 0.40 +
            pitcher_under * 0.35 +
            bullpen_under * 0.10 +
            park_under    * 0.10 +
            weather_under * 0.05
        ) * 10.0

        score = round(max(0.0, min(100.0, weighted)), 1)
        return {"score": score, "verdict": self._verdict(score, TT_VERDICTS)}

    def _nrfi_factors(self, ap, hp, ao, ho, ump) -> list[str]:
        notes = []
        for label, p in (("Away SP", ap), ("Home SP", hp)):
            trend = p.get("recent_trend", "neutral")
            if trend in ("dominant", "hot"):
                notes.append(f"{label} {trend} ({p.get('era','?')} ERA)")
            elif trend in ("struggling", "cold"):
                notes.append(f"{label} {trend} (last 3)")

        for label, off in (("Away bats", ao), ("Home bats", ho)):
            streak = off.get("streak", "neutral") if off else "neutral"
            if streak == "cold":
                notes.append(f"{label} cold ({off.get('runs_per_game_10d','?')} rpg L10)")
            elif streak == "hot":
                notes.append(f"{label} hot ({off.get('runs_per_game_10d','?')} rpg L10)")

        return notes

    def _u(self, data: Any) -> float:
        return float((data or {}).get("under_score", 5.0))

    def _verdict(self, score: float, table: list[tuple[float, str]]) -> str:
        for threshold, label in table:
            if score >= threshold:
                return label
        return table[-1][1]
