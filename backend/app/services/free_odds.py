"""
Free odds fetcher — Action Network public scoreboard + ESPN fallback.
Returns data in The Odds API format so LineMovementService works unchanged.
No API key required. Falls back silently on any error.
"""
import httpx
from datetime import date
from typing import Any, Optional

# Action Network internal book IDs → (odds-api-style key, title)
_AN_BOOKS: dict[int, tuple[str, str]] = {
    15:  ("draftkings",  "DraftKings"),
    16:  ("fanduel",     "FanDuel"),
    25:  ("betmgm",      "BetMGM"),
    30:  ("caesars",     "Caesars"),
    19:  ("pinnacle",    "Pinnacle"),
    4:   ("williamhill", "Caesars (WH)"),   # William Hill / Caesars alt
    3:   ("barstool",    "Barstool"),
}

_WANTED_BOOK_IDS = set(_AN_BOOKS.keys())

_AN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.actionnetwork.com/",
}


async def fetch_free_odds(game_date: Optional[date] = None) -> list[dict[str, Any]]:
    """
    Fetch MLB moneylines + totals from Action Network's public scoreboard API.
    Returns a list of game dicts in Odds API format.
    Falls back to ESPN if Action Network fails.
    """
    # Action Network scoreboard — today's games only (no date param needed)
    url = "https://api.actionnetwork.com/web/v1/scoreboard/mlb"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=_AN_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                games = data.get("games") or []
                if games:
                    result = []
                    for game in games:
                        mapped = _map_an_game(game)
                        if mapped:
                            result.append(mapped)
                    if result:
                        return result
    except httpx.RequestError:
        pass

    # Fallback: ESPN scoreboard
    return await _espn_fallback(game_date)


def _map_an_game(game: dict) -> Optional[dict[str, Any]]:
    away_team_id = game.get("away_team_id")
    home_team_id = game.get("home_team_id")

    teams = {t["id"]: t for t in (game.get("teams") or [])}
    home_info = teams.get(home_team_id, {})
    away_info = teams.get(away_team_id, {})

    home_name = home_info.get("full_name") or home_info.get("display_name", "")
    away_name = away_info.get("full_name") or away_info.get("display_name", "")
    if not home_name or not away_name:
        return None

    odds_list = game.get("odds") or []
    bookmakers = []

    for odd in odds_list:
        book_id = odd.get("book_id")
        if book_id not in _WANTED_BOOK_IDS:
            continue
        # Only use full-game odds (not F5, NRFI, etc.)
        if odd.get("type") not in (None, "game", 1):
            continue

        bk_key, bk_title = _AN_BOOKS[book_id]
        markets = []

        # Moneyline (h2h)
        ml_home = odd.get("ml_home")
        ml_away = odd.get("ml_away")
        if ml_home is not None and ml_away is not None:
            markets.append({
                "key": "h2h",
                "outcomes": [
                    {"name": away_name, "price": int(ml_away)},
                    {"name": home_name, "price": int(ml_home)},
                ],
            })

        # Game total — AN uses "over"/"under" for the juice, "total" for the number
        total = odd.get("total")
        over_price = odd.get("over")
        under_price = odd.get("under")
        if total is not None:
            markets.append({
                "key": "totals",
                "outcomes": [
                    {"name": "Over",  "point": float(total), "price": int(over_price or -110)},
                    {"name": "Under", "point": float(total), "price": int(under_price or -110)},
                ],
            })

        if markets:
            bookmakers.append({"key": bk_key, "title": bk_title, "markets": markets})

    if not bookmakers:
        return None

    return {
        "away_team": away_name,
        "home_team": home_name,
        "bookmakers": bookmakers,
        "source": "action_network",
    }


async def _espn_fallback(game_date: Optional[date] = None) -> list[dict[str, Any]]:
    """ESPN scoreboard — consensus odds when available."""
    target_date = (game_date or date.today()).strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={target_date}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except httpx.RequestError:
        return []

    events = data.get("events") or []
    result = []
    for event in events:
        mapped = _map_espn_event(event)
        if mapped:
            result.append(mapped)
    return result


def _map_espn_event(event: dict) -> Optional[dict[str, Any]]:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]

    competitors = comp.get("competitors") or []
    home_name = away_name = None
    for c in competitors:
        team = (c.get("team") or {}).get("displayName", "")
        if c.get("homeAway") == "home":
            home_name = team
        else:
            away_name = team

    if not home_name or not away_name:
        return None

    odds_list = comp.get("odds") or []
    if not odds_list:
        return {"away_team": away_name, "home_team": home_name, "bookmakers": [], "source": "espn"}

    markets = []
    odd = odds_list[0]

    home_ml = (odd.get("homeTeamOdds") or {}).get("moneyLine")
    away_ml = (odd.get("awayTeamOdds") or {}).get("moneyLine")
    if home_ml is not None and away_ml is not None:
        markets.append({
            "key": "h2h",
            "outcomes": [
                {"name": away_name, "price": int(away_ml)},
                {"name": home_name, "price": int(home_ml)},
            ],
        })

    total = odd.get("overUnder")
    if total is not None:
        markets.append({
            "key": "totals",
            "outcomes": [
                {"name": "Over",  "point": float(total), "price": -110},
                {"name": "Under", "point": float(total), "price": -110},
            ],
        })

    bookmakers = [{"key": "espn_consensus", "title": "ESPN Consensus", "markets": markets}] if markets else []
    return {
        "away_team": away_name,
        "home_team": home_name,
        "bookmakers": bookmakers,
        "source": "espn",
    }
