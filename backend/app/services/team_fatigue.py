import httpx
import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

MLB_BASE = "https://statsapi.mlb.com/api/v1"
CURRENT_SEASON = date.today().year

# Each team's home city time zone and coordinates
TEAM_CITY_INFO: dict[int, dict[str, Any]] = {
    133: {"name": "Oakland Athletics",        "tz": "America/Los_Angeles", "lat": 37.75,  "lon": -122.20},
    134: {"name": "Pittsburgh Pirates",       "tz": "America/New_York",   "lat": 40.45,  "lon": -80.01},
    135: {"name": "San Diego Padres",         "tz": "America/Los_Angeles","lat": 32.71,  "lon": -117.16},
    136: {"name": "Seattle Mariners",         "tz": "America/Los_Angeles","lat": 47.59,  "lon": -122.33},
    137: {"name": "San Francisco Giants",     "tz": "America/Los_Angeles","lat": 37.78,  "lon": -122.39},
    138: {"name": "St. Louis Cardinals",      "tz": "America/Chicago",    "lat": 38.62,  "lon": -90.19},
    139: {"name": "Tampa Bay Rays",           "tz": "America/New_York",   "lat": 27.77,  "lon": -82.65},
    140: {"name": "Texas Rangers",            "tz": "America/Chicago",    "lat": 32.75,  "lon": -97.08},
    141: {"name": "Toronto Blue Jays",        "tz": "America/Toronto",    "lat": 43.64,  "lon": -79.39},
    142: {"name": "Minnesota Twins",          "tz": "America/Chicago",    "lat": 44.98,  "lon": -93.28},
    143: {"name": "Philadelphia Phillies",    "tz": "America/New_York",   "lat": 39.91,  "lon": -75.17},
    144: {"name": "Atlanta Braves",           "tz": "America/New_York",   "lat": 33.89,  "lon": -84.47},
    145: {"name": "Chicago White Sox",        "tz": "America/Chicago",    "lat": 41.83,  "lon": -87.63},
    146: {"name": "Miami Marlins",            "tz": "America/New_York",   "lat": 25.78,  "lon": -80.22},
    147: {"name": "New York Yankees",         "tz": "America/New_York",   "lat": 40.83,  "lon": -73.93},
    158: {"name": "Milwaukee Brewers",        "tz": "America/Chicago",    "lat": 43.03,  "lon": -87.97},
    108: {"name": "Los Angeles Angels",       "tz": "America/Los_Angeles","lat": 33.80,  "lon": -117.88},
    109: {"name": "Arizona Diamondbacks",     "tz": "America/Phoenix",    "lat": 33.45,  "lon": -112.07},
    110: {"name": "Baltimore Orioles",        "tz": "America/New_York",   "lat": 39.28,  "lon": -76.62},
    111: {"name": "Boston Red Sox",           "tz": "America/New_York",   "lat": 42.35,  "lon": -71.10},
    112: {"name": "Chicago Cubs",             "tz": "America/Chicago",    "lat": 41.95,  "lon": -87.66},
    113: {"name": "Cincinnati Reds",          "tz": "America/New_York",   "lat": 39.10,  "lon": -84.51},
    114: {"name": "Cleveland Guardians",      "tz": "America/New_York",   "lat": 41.50,  "lon": -81.69},
    115: {"name": "Colorado Rockies",         "tz": "America/Denver",     "lat": 39.76,  "lon": -104.99},
    116: {"name": "Detroit Tigers",           "tz": "America/Detroit",    "lat": 42.34,  "lon": -83.05},
    117: {"name": "Houston Astros",           "tz": "America/Chicago",    "lat": 29.76,  "lon": -95.36},
    118: {"name": "Kansas City Royals",       "tz": "America/Chicago",    "lat": 39.05,  "lon": -94.48},
    119: {"name": "Los Angeles Dodgers",      "tz": "America/Los_Angeles","lat": 34.07,  "lon": -118.24},
    120: {"name": "Washington Nationals",     "tz": "America/New_York",   "lat": 38.87,  "lon": -77.01},
    121: {"name": "New York Mets",            "tz": "America/New_York",   "lat": 40.76,  "lon": -73.85},
}

TZ_OFFSET = {
    "America/Los_Angeles": -8,
    "America/Phoenix":     -7,
    "America/Denver":      -7,
    "America/Chicago":     -6,
    "America/Detroit":     -5,
    "America/New_York":    -5,
    "America/Toronto":     -5,
}


class TeamFatigueService:

    async def get_fatigue(self, team_id: int, game_date: Optional[date] = None) -> dict[str, Any]:
        today = game_date or date.today()
        lookback_start = today - timedelta(days=10)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{MLB_BASE}/schedule",
                    params={
                        "teamId": team_id,
                        "startDate": lookback_start.strftime("%Y-%m-%d"),
                        "endDate": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
                        "sportId": 1,
                        "hydrate": "venue,team",
                    },
                )
                if resp.status_code != 200:
                    return self._neutral(team_id)
                data = resp.json()
        except httpx.RequestError:
            return self._neutral(team_id)

        games = self._parse_recent_games(data, team_id, today)
        return self._compute_fatigue(team_id, games, today)

    def _parse_recent_games(self, data: dict, team_id: int, today: date) -> list[dict]:
        games = []
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                status = g.get("status", {}).get("abstractGameState", "")
                if status not in ("Final", "Live"):
                    continue
                away = g.get("teams", {}).get("away", {})
                home = g.get("teams", {}).get("home", {})
                is_home = home.get("team", {}).get("id") == team_id
                opponent_city_id = away.get("team", {}).get("id") if is_home else home.get("team", {}).get("id")
                venue = g.get("venue", {})
                game_dt = g.get("gameDate", "")
                game_time = None
                if game_dt:
                    try:
                        game_time = datetime.fromisoformat(game_dt.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                # Use gameDate (actual play date) not officialDate — postponed/rescheduled
                # games get a future officialDate while gameDate stays accurate.
                actual_date = None
                if game_time:
                    derived = game_time.date()
                    # Discard if somehow in the future (data error)
                    if derived <= today:
                        actual_date = derived.isoformat()
                elif g.get("officialDate"):
                    try:
                        od = date.fromisoformat(g["officialDate"])
                        if od <= today:
                            actual_date = od.isoformat()
                    except ValueError:
                        pass

                if actual_date is None:
                    continue  # skip games with bad/future dates

                games.append({
                    "date": actual_date,
                    "game_time": game_time,
                    "is_home": is_home,
                    "venue_id": venue.get("id"),
                    "opponent_team_id": opponent_city_id,
                })
        return sorted(games, key=lambda x: x["date"] or "", reverse=True)

    def _compute_fatigue(self, team_id: int, games: list[dict], today: date) -> dict[str, Any]:
        if not games:
            return self._neutral(team_id)

        # Days of rest
        last_game_date = None
        for g in games:
            try:
                last_game_date = date.fromisoformat(g["date"])
                break
            except (ValueError, TypeError):
                continue

        rest_days = (today - last_game_date).days if last_game_date else 2

        # Consecutive road games
        consecutive_road = 0
        for g in games:
            if not g["is_home"]:
                consecutive_road += 1
            else:
                break

        # Travel direction penalty: west travel is hardest (lose sleep hours)
        travel_penalty = self._travel_penalty(team_id, games)

        # Day game after night game
        dagn = self._is_dagn(games)

        # Games in last 7 days
        seven_days_ago = today - timedelta(days=7)
        recent_game_count = sum(
            1 for g in games
            if g["date"] and date.fromisoformat(g["date"]) >= seven_days_ago
        )

        # Compute fatigue score (0-10, higher = MORE fatigued = worse for that team)
        fatigue = 5.0
        fatigue -= min(rest_days * 1.5, 3.0)          # more rest = less fatigued
        fatigue += min(consecutive_road * 0.5, 2.5)   # long road trip = more fatigued
        fatigue += travel_penalty                       # west travel penalty
        fatigue += 1.5 if dagn else 0                  # DAGN penalty
        fatigue += max(0, (recent_game_count - 5) * 0.3)  # heavy schedule

        fatigue = round(max(0.0, min(10.0, fatigue)), 2)

        # Under score: fatigued OFFENSE = fewer runs = under-friendly
        # We'll use this as an input to the dog scorer and the main engine
        under_contribution = round(10 - fatigue, 2)  # inverted for under model

        return {
            "team_id": team_id,
            "rest_days": rest_days,
            "consecutive_road_games": consecutive_road,
            "travel_penalty": round(travel_penalty, 2),
            "is_dagn": dagn,
            "recent_game_count_7d": recent_game_count,
            "fatigue_score": fatigue,       # 0-10, higher = more tired
            "under_score": under_contribution,  # 0-10 for under model
        }

    def _travel_penalty(self, team_id: int, games: list[dict]) -> float:
        """West-bound travel is hardest (lose hours). Cross-country = maximum penalty."""
        home_info = TEAM_CITY_INFO.get(team_id, {})
        home_tz_offset = TZ_OFFSET.get(home_info.get("tz", "America/New_York"), -5)

        # Find the city of the previous away game
        for g in games:
            if not g["is_home"] and g["opponent_team_id"]:
                prev_city = TEAM_CITY_INFO.get(g["opponent_team_id"], {})
                prev_tz_offset = TZ_OFFSET.get(prev_city.get("tz", "America/New_York"), -5)
                tz_diff = home_tz_offset - prev_tz_offset  # negative = traveling west
                if tz_diff < 0:
                    return min(abs(tz_diff) * 0.5, 2.0)  # west = bad, up to 2.0 penalty
                return 0.0
        return 0.0

    def _is_dagn(self, games: list[dict]) -> bool:
        """True if the most recent game was a night game (after 6pm ET)."""
        if not games or not games[0].get("game_time"):
            return False
        try:
            gt = games[0]["game_time"]
            if ZoneInfo:
                et = gt.astimezone(ZoneInfo("America/New_York"))
            else:
                import datetime
                et = gt.astimezone(datetime.timezone.utc)
            return et.hour >= 18
        except Exception:
            return False

    def _neutral(self, team_id: int) -> dict[str, Any]:
        return {
            "team_id": team_id,
            "rest_days": 1,
            "consecutive_road_games": 0,
            "travel_penalty": 0.0,
            "is_dagn": False,
            "recent_game_count_7d": 5,
            "fatigue_score": 5.0,
            "under_score": 5.0,
        }
