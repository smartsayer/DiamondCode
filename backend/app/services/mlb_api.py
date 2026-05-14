import httpx
from datetime import date, datetime, timezone
from typing import Any, Optional
from app.config import get_settings

settings = get_settings()
CURRENT_SEASON = date.today().year


class MLBStatsAPI:
    """
    Official MLB Stats API (statsapi.mlb.com) — no auth required.
    Docs: https://statsapi.mlb.com/docs/
    """

    BASE = settings.mlb_stats_base_url

    async def get_schedule(self, game_date: Optional[date] = None) -> list[dict[str, Any]]:
        """Return today's games with venue, pitcher, and umpire info."""
        target = (game_date or date.today()).strftime("%Y-%m-%d")
        params = {
            "sportId": 1,
            "date": target,
            "hydrate": "team,venue,probablePitcher(note),officials,weather,linescore",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self.BASE}/schedule", params=params)
            resp.raise_for_status()
            data = resp.json()

        games = []
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                games.append(self._parse_game(g))
        return games

    def _parse_game(self, g: dict[str, Any]) -> dict[str, Any]:
        venue = g.get("venue", {})
        away = g.get("teams", {}).get("away", {})
        home = g.get("teams", {}).get("home", {})

        # Extract HP umpire from officials list (available pre-game via schedule hydration)
        hp_umpire = None
        for official in g.get("officials", []):
            if official.get("officialType") == "Home Plate":
                o = official.get("official", {})
                hp_umpire = {"id": o.get("id"), "name": o.get("fullName")}
                break

        return {
            "game_pk": g["gamePk"],
            "game_date": g.get("officialDate"),
            "game_time_utc": g.get("gameDate"),
            "status": g.get("status", {}).get("detailedState"),
            "venue_id": venue.get("id"),
            "venue_name": venue.get("name"),
            "away_team_id": away.get("team", {}).get("id"),
            "away_team": away.get("team", {}).get("name"),
            "away_team_abbr": away.get("team", {}).get("abbreviation"),
            "away_pitcher_id": away.get("probablePitcher", {}).get("id"),
            "away_pitcher_name": away.get("probablePitcher", {}).get("fullName"),
            "home_team_id": home.get("team", {}).get("id"),
            "home_team": home.get("team", {}).get("name"),
            "home_team_abbr": home.get("team", {}).get("abbreviation"),
            "home_pitcher_id": home.get("probablePitcher", {}).get("id"),
            "home_pitcher_name": home.get("probablePitcher", {}).get("fullName"),
            "home_pitcher_throws": home.get("probablePitcher", {}).get("pitchHand", {}).get("code"),
            "away_pitcher_throws": away.get("probablePitcher", {}).get("pitchHand", {}).get("code"),
            "hp_umpire": hp_umpire,
            "abstract_state": g.get("status", {}).get("abstractGameState", "Preview"),
            "detailed_state": g.get("status", {}).get("detailedState", "Scheduled"),
            "live_score": self._parse_linescore(g),
            "series_game_number": g.get("seriesGameNumber", 1),
            "games_in_series": g.get("gamesInSeries", 3),
        }

    def _parse_linescore(self, g: dict[str, Any]) -> dict[str, Any]:
        ls = g.get("linescore", {})
        if not ls:
            return {"away_runs": None, "home_runs": None, "inning": None, "inning_half": None}
        teams = ls.get("teams", {})
        return {
            "away_runs": teams.get("away", {}).get("runs"),
            "home_runs": teams.get("home", {}).get("runs"),
            "away_hits": teams.get("away", {}).get("hits"),
            "home_hits": teams.get("home", {}).get("hits"),
            "inning": ls.get("currentInning"),
            "inning_half": ls.get("inningHalf"),
            "outs": ls.get("outs"),
        }

    async def get_umpire_for_game(self, game_pk: int) -> Optional[dict[str, Any]]:
        """Fallback: fetch HP umpire from boxscore (only works for in-progress/completed games)."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self.BASE}/game/{game_pk}/boxscore")
            if resp.status_code != 200:
                return None
            data = resp.json()

        for official in data.get("officials", []):
            if official.get("officialType") == "Home Plate":
                o = official.get("official", {})
                return {"id": o.get("id"), "name": o.get("fullName")}
        return None

    async def get_bullpen_usage(self, team_id: int, lookback_days: int = 3) -> dict[str, Any]:
        """Pull recent pitcher appearances to estimate bullpen fatigue."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.BASE}/teams/{team_id}/roster",
                params={"rosterType": "active", "hydrate": f"person(stats(type=gameLog,season={CURRENT_SEASON}))"},
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()

        relievers = []
        for player in data.get("roster", []):
            person = player.get("person", {})
            pos = player.get("position", {}).get("abbreviation", "")
            if pos == "P" and player.get("status", {}).get("code") == "A":
                stats = person.get("stats", [])
                relievers.append({
                    "id": person.get("id"),
                    "name": person.get("fullName"),
                    "stats": stats,
                })
        return {"team_id": team_id, "relievers": relievers}
