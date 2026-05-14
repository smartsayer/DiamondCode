import httpx
import json
import os
from datetime import date
from typing import Any, Optional
from app.config import get_settings

settings = get_settings()

SHARP_BOOK_PRIORITY = ["pinnacle", "draftkings", "fanduel", "betmgm", "caesars"]

# Disk path for the closing-line cache — survives server restarts.
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "closing_lines.json")
_CACHE_FILE = os.path.normpath(_CACHE_FILE)


def _load_disk_cache() -> dict:
    """Load today's closing lines from disk, discarding stale entries from prior days."""
    today = date.today().isoformat()
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            return data.get("lines", {})
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return {}


def _save_disk_cache(lines: dict) -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump({"date": date.today().isoformat(), "lines": lines}, f)
    except OSError:
        pass


class LineMovementService:
    """
    Tracks closing line and live line using The Odds API.
    Closing line = sharpest pre-game consensus (locked when game goes Live).
    Live line = current in-game odds (updates continuously during the game).
    Closing lines are persisted to disk so server restarts don't lose them.
    """

    BASE = "https://api.the-odds-api.com/v4"
    SPORT = "baseball_mlb"

    # Class-level cache populated on first use from disk; written back on each Preview update.
    _closing_cache: dict[str, dict[str, Any]] = {}
    _cache_loaded: bool = False

    def _ensure_cache_loaded(self) -> None:
        if not LineMovementService._cache_loaded:
            LineMovementService._closing_cache = _load_disk_cache()
            LineMovementService._cache_loaded = True

    async def get_current_totals(self) -> list[dict[str, Any]]:
        """Fetch current MLB totals + moneylines from The Odds API (one call)."""
        if not settings.odds_api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.BASE}/sports/{self.SPORT}/odds",
                    params={
                        "apiKey": settings.odds_api_key,
                        "regions": "us",
                        "markets": "totals,h2h",
                        "oddsFormat": "american",
                        "dateFormat": "iso",
                        "bookmakers": ",".join(SHARP_BOOK_PRIORITY),
                    },
                )
                if resp.status_code != 200:
                    return []
                return resp.json()
        except httpx.RequestError:
            return []

    def parse_movement(
        self,
        current_games: list[dict[str, Any]],
        away_team: str,
        home_team: str,
        game_state: str = "Preview",
    ) -> dict[str, Any]:
        """
        Return closing line, live line, and movement for a game.
        game_state: "Preview" | "Live" | "Final"
        """
        self._ensure_cache_loaded()
        match = self._find_game(current_games, away_team, home_team)
        cache_key = self._cache_key(away_team, home_team)

        current_total = self._extract_total(match) if match else None
        current_total_book = self._extract_total_book(match) if match else None

        if game_state == "Preview":
            # Update closing cache with the latest pre-game line and persist to disk
            if current_total is not None:
                self._closing_cache[cache_key] = {
                    "total": current_total,
                    "book": current_total_book,
                }
                _save_disk_cache(self._closing_cache)
            closing_total = current_total
            live_total = None
            closing_book = current_total_book
        else:
            # Game is Live or Final — use locked closing; never overwrite with live line
            cached = self._closing_cache.get(cache_key, {})
            closing_total = cached.get("total")      # None if we never saw this game pre-game
            closing_book = cached.get("book")
            live_total = current_total

        # If we have no closing line at all, we can't compute movement
        if closing_total is None and live_total is None:
            return self._no_data()

        opening = closing_total if closing_total is not None else live_total
        live = live_total if live_total is not None else closing_total
        movement = round(live - opening, 1) if (live is not None and opening is not None) else 0.0

        signal = self._interpret_movement(movement)
        under_score = self._movement_to_score(movement)

        return {
            "closing_total": closing_total,
            "closing_book": closing_book,
            "live_total": live_total,
            "current_total": live,
            "movement": movement,
            "signal": signal,
            "under_score": under_score,
            "game_state": game_state,
            "has_data": True,
        }

    def extract_moneyline(
        self,
        current_games: list[dict[str, Any]],
        away_team: str,
        home_team: str,
        game_state: str = "Preview",
    ) -> dict[str, Any]:
        """
        Return which side is the underdog from the sharpest book available.
        For Live/Final games, shows both closing and live moneylines.
        """
        self._ensure_cache_loaded()
        match = self._find_game(current_games, away_team, home_team)
        if not match:
            # Even with no live match, return cached closing if we have it
            cache_key = self._cache_key(away_team, home_team)
            cached = self._closing_cache.get(f"{cache_key}_ml", {})
            closing_away = cached.get("away")
            closing_home = cached.get("home")
            book_used = cached.get("book")
            if closing_away is None and closing_home is None:
                return {"dog_side": None, "away_ml": None, "home_ml": None,
                        "closing_away_ml": None, "closing_home_ml": None}
            dog_side = "away" if (closing_away or 0) > (closing_home or 0) else "home" if (closing_home or 0) > (closing_away or 0) else None
            return {
                "dog_side": dog_side,
                "away_ml": None, "home_ml": None,
                "closing_away_ml": closing_away,
                "closing_home_ml": closing_home,
                "live_away_ml": None, "live_home_ml": None,
                "book": book_used, "odds_sourced": True,
            }

        away_ml, home_ml, book_used = self._extract_ml(match, away_team, home_team)

        cache_key = self._cache_key(away_team, home_team)
        if game_state == "Preview" and away_ml is not None:
            self._closing_cache[f"{cache_key}_ml"] = {
                "away": away_ml, "home": home_ml, "book": book_used
            }
            _save_disk_cache(self._closing_cache)
            closing_away, closing_home = away_ml, home_ml
            live_away, live_home = None, None
        else:
            cached = self._closing_cache.get(f"{cache_key}_ml", {})
            # Use locked pre-game closing ML; never substitute live ML for it
            closing_away = cached.get("away")
            closing_home = cached.get("home")
            live_away = away_ml
            live_home = home_ml

        # Dog identification uses CLOSING line — don't let in-game swings flip the label
        ref_away = closing_away if closing_away is not None else away_ml
        ref_home = closing_home if closing_home is not None else home_ml

        if ref_away is None or ref_home is None:
            dog_side = None
        elif ref_away > ref_home:
            dog_side = "away"
        elif ref_home > ref_away:
            dog_side = "home"
        else:
            dog_side = None

        return {
            "dog_side": dog_side,
            "away_ml": away_ml,
            "home_ml": home_ml,
            "closing_away_ml": closing_away,
            "closing_home_ml": closing_home,
            "live_away_ml": live_away,
            "live_home_ml": live_home,
            "book": book_used,
            "odds_sourced": away_ml is not None,
        }

    def best_prices(
        self,
        current_games: list[dict[str, Any]],
        away_team: str,
        home_team: str,
    ) -> dict[str, Any]:
        """
        Best price across all books for totals (over/under) and moneyline.
        Line shopping = guaranteed 1-3% edge over taking the first price.
        """
        match = self._find_game(current_games, away_team, home_team)
        if not match:
            return {"has_data": False}

        best_over = best_under = best_away_ml = best_home_ml = None
        best_over_book = best_under_book = best_away_ml_book = best_home_ml_book = None
        away_lower = away_team.lower()
        home_lower = home_team.lower()

        for bookmaker in match.get("bookmakers", []):
            book_title = bookmaker.get("title", bookmaker.get("key", ""))
            for market in bookmaker.get("markets", []):
                key = market.get("key")
                if key == "totals":
                    for o in market.get("outcomes", []):
                        price = o.get("price")
                        if price is None:
                            continue
                        if o.get("name") == "Over" and (best_over is None or price > best_over):
                            best_over, best_over_book = price, book_title
                        elif o.get("name") == "Under" and (best_under is None or price > best_under):
                            best_under, best_under_book = price, book_title
                elif key == "h2h":
                    for o in market.get("outcomes", []):
                        name = o.get("name", "").lower()
                        price = o.get("price")
                        if price is None:
                            continue
                        if any(w in name for w in away_lower.split()):
                            if best_away_ml is None or price > best_away_ml:
                                best_away_ml, best_away_ml_book = price, book_title
                        elif any(w in name for w in home_lower.split()):
                            if best_home_ml is None or price > best_home_ml:
                                best_home_ml, best_home_ml_book = price, book_title

        return {
            "has_data": True,
            "best_over_price": best_over,
            "best_over_book": best_over_book,
            "best_under_price": best_under,
            "best_under_book": best_under_book,
            "best_away_ml": best_away_ml,
            "best_away_ml_book": best_away_ml_book,
            "best_home_ml": best_home_ml,
            "best_home_ml_book": best_home_ml_book,
        }

    # ── internals ──────────────────────────────────────────────────────────────

    def _find_game(self, games: list[dict], away: str, home: str) -> Optional[dict]:
        away_lower = away.lower()
        home_lower = home.lower()
        best = None
        for game in games:
            ga = game.get("away_team", "").lower()
            gh = game.get("home_team", "").lower()
            if (any(w in ga for w in away_lower.split()) and
                    any(w in gh for w in home_lower.split())):
                # Prefer games with more bookmakers (more data = better match)
                if best is None or len(game.get("bookmakers", [])) > len(best.get("bookmakers", [])):
                    best = game
        return best

    def _extract_total(self, game: dict) -> Optional[float]:
        for bm_key in SHARP_BOOK_PRIORITY:
            for bookmaker in game.get("bookmakers", []):
                if bookmaker.get("key") != bm_key:
                    continue
                for market in bookmaker.get("markets", []):
                    if market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            if outcome.get("name") == "Over":
                                return float(outcome.get("point", 0))
        # Fallback: first available book
        for bookmaker in game.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome.get("name") == "Over":
                            return float(outcome.get("point", 0))
        return None

    def _extract_total_book(self, game: dict) -> Optional[str]:
        for bm_key in SHARP_BOOK_PRIORITY:
            for bookmaker in game.get("bookmakers", []):
                if bookmaker.get("key") == bm_key:
                    for market in bookmaker.get("markets", []):
                        if market.get("key") == "totals":
                            return bookmaker.get("title", bm_key)
        return None

    def _extract_ml(
        self, game: dict, away_team: str, home_team: str
    ) -> tuple[Optional[float], Optional[float], Optional[str]]:
        away_lower = away_team.lower()
        home_lower = home_team.lower()

        for bm_key in SHARP_BOOK_PRIORITY:
            for bookmaker in game.get("bookmakers", []):
                if bookmaker.get("key") != bm_key:
                    continue
                for market in bookmaker.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    away_ml = home_ml = None
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name", "").lower()
                        price = outcome.get("price")
                        if any(w in name for w in away_lower.split()):
                            away_ml = price
                        elif any(w in name for w in home_lower.split()):
                            home_ml = price
                    if away_ml is not None and home_ml is not None:
                        return away_ml, home_ml, bookmaker.get("title", bm_key)

        return None, None, None

    def _cache_key(self, away: str, home: str) -> str:
        return f"{away.lower().split()[-1]}_{home.lower().split()[-1]}"

    def _interpret_movement(self, movement: float) -> str:
        if movement <= -1.5:
            return "Sharp UNDER — major line drop"
        if movement <= -0.5:
            return "Lean UNDER — line dropped"
        if movement >= 1.5:
            return "Sharp OVER — line rose significantly"
        if movement >= 0.5:
            return "Lean OVER — line ticked up"
        return "Neutral"

    def _movement_to_score(self, movement: float) -> float:
        score = 5.0 - (movement * 2.5)
        return round(max(0.0, min(10.0, score)), 2)

    def _no_data(self) -> dict[str, Any]:
        return {
            "closing_total": None,
            "closing_book": None,
            "live_total": None,
            "current_total": None,
            "movement": 0.0,
            "signal": "No line data",
            "under_score": 5.0,
            "game_state": "Preview",
            "has_data": False,
        }
