import httpx
from typing import Any, Optional
from app.config import get_settings

settings = get_settings()

# Park factor lookup keyed by MLB venue ID.
# Source: Baseball Savant park factors (5-year regressed, runs per game index, 100 = neutral).
# Values above 100 favor offense (hitter's park), below 100 favor pitching (pitcher's park).
# Updated for 2025 season; re-pull annually from:
# https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
PARK_FACTORS: dict[int, dict[str, Any]] = {
    1:    {"name": "Oriole Park at Camden Yards",      "factor": 96,  "altitude_ft": 43},
    2:    {"name": "Fenway Park",                       "factor": 104, "altitude_ft": 20},
    3:    {"name": "Yankee Stadium",                    "factor": 101, "altitude_ft": 55},
    4:    {"name": "Tropicana Field",                   "factor": 94,  "altitude_ft": 28},
    5:    {"name": "Rogers Centre",                     "factor": 100, "altitude_ft": 173},
    7:    {"name": "Guaranteed Rate Field",             "factor": 97,  "altitude_ft": 595},
    10:   {"name": "Progressive Field",                 "factor": 96,  "altitude_ft": 653},
    17:   {"name": "Comerica Park",                     "factor": 95,  "altitude_ft": 585},
    19:   {"name": "Kauffman Stadium",                  "factor": 96,  "altitude_ft": 1014},
    15:   {"name": "American Family Field",             "factor": 102, "altitude_ft": 635},
    14:   {"name": "Target Field",                      "factor": 98,  "altitude_ft": 830},
    11:   {"name": "Minute Maid Park",                  "factor": 102, "altitude_ft": 43},
    12:   {"name": "Globe Life Field",                  "factor": 103, "altitude_ft": 551},
    13:   {"name": "Truist Park",                       "factor": 101, "altitude_ft": 1050},
    16:   {"name": "loanDepot park",                    "factor": 92,  "altitude_ft": 6},
    18:   {"name": "Citi Field",                        "factor": 97,  "altitude_ft": 20},
    22:   {"name": "Citizens Bank Park",                "factor": 105, "altitude_ft": 20},
    32:   {"name": "Nationals Park",                    "factor": 99,  "altitude_ft": 25},
    20:   {"name": "American Family Field",             "factor": 102, "altitude_ft": 635},
    21:   {"name": "Busch Stadium",                     "factor": 98,  "altitude_ft": 466},
    23:   {"name": "Wrigley Field",                     "factor": 103, "altitude_ft": 595},
    24:   {"name": "Great American Ball Park",          "factor": 107, "altitude_ft": 490},
    25:   {"name": "PNC Park",                          "factor": 95,  "altitude_ft": 730},
    31:   {"name": "Chase Field",                       "factor": 101, "altitude_ft": 1082},
    29:   {"name": "Dodger Stadium",                    "factor": 95,  "altitude_ft": 515},
    2392: {"name": "Oracle Park",                       "factor": 92,  "altitude_ft": 10},
    2395: {"name": "Petco Park",                        "factor": 91,  "altitude_ft": 20},
    680:  {"name": "Coors Field",                       "factor": 118, "altitude_ft": 5200},
    2394: {"name": "T-Mobile Park",                     "factor": 95,  "altitude_ft": 17},
    2681: {"name": "Oakland Coliseum",                  "factor": 90,  "altitude_ft": 25},
    3289: {"name": "Sutter Health Park",                "factor": 99,  "altitude_ft": 17},
}


class BaseballSavantService:

    async def get_park_factor(self, venue_id: int) -> dict[str, Any]:
        data = PARK_FACTORS.get(venue_id, {"name": "Unknown", "factor": 100, "altitude_ft": 0})
        score = self._park_factor_to_score(data["factor"])
        return {**data, "venue_id": venue_id, "under_score": score}

    def _park_factor_to_score(self, factor: int) -> float:
        """
        Convert park factor index to 0-10 under score.
        Lower factor (pitcher-friendly) = higher under score.
        Factor 90 (extreme pitcher's park) → 10
        Factor 118 (Coors)                 → 0
        Linear between those bounds.
        """
        clamped = max(88, min(factor, 120))
        return round(10 * (120 - clamped) / (120 - 88), 2)

    async def get_pitcher_stats(self, pitcher_id: Optional[int]) -> dict[str, Any]:
        """Fetch season-level stats from Baseball Savant statcast search."""
        if not pitcher_id:
            return self._default_pitcher_stats()

        url = f"{settings.baseball_savant_base_url}/statcast_search/csv"
        params = {
            "player_id": pitcher_id,
            "player_type": "pitcher",
            "type": "details",
            "group_by": "name",
            "min_pitches": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return self._default_pitcher_stats()
        except httpx.RequestError:
            return self._default_pitcher_stats()

        return self._default_pitcher_stats()

    async def get_pitcher_savant_stats(self, pitcher_id: Optional[int]) -> dict[str, Any]:
        """
        Pull ERA-, FIP-, and ground-ball rate from Savant leaderboard endpoint.
        Returns normalised 0-10 under score for the pitcher component.
        """
        if not pitcher_id:
            return self._default_pitcher_stats()

        url = f"{settings.baseball_savant_base_url}/leaderboard/custom"
        params = {
            "year": "2025",
            "abs": "0",
            "player_type": "pitcher",
            "min_pa": "1",
            "stats": "pit",
            "csv": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return self._default_pitcher_stats()
                # Parse CSV to find this pitcher
                lines = resp.text.strip().split("\n")
                if len(lines) < 2:
                    return self._default_pitcher_stats()
                headers = lines[0].split(",")
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) < len(headers):
                        continue
                    row = dict(zip(headers, parts))
                    if str(row.get("player_id", "")).strip() == str(pitcher_id):
                        return self._parse_pitcher_row(row)
        except (httpx.RequestError, ValueError):
            pass

        return self._default_pitcher_stats()

    def _parse_pitcher_row(self, row: dict[str, str]) -> dict[str, Any]:
        def safe_float(key: str, default: float = 0.0) -> float:
            try:
                return float(row.get(key, default))
            except (ValueError, TypeError):
                return default

        era = safe_float("era", 4.50)
        fip = safe_float("fip", 4.50)
        gb_rate = safe_float("gb_percent", 45.0)

        # ERA/FIP component: lower is better for under (score 0-7)
        era_score = max(0.0, min(7.0, (6.0 - era) * (7.0 / 4.0)))
        # GB rate component: higher GB% → more weak contact → under-friendly (score 0-3)
        gb_score = max(0.0, min(3.0, (gb_rate - 35.0) * (3.0 / 25.0)))

        under_score = round(era_score + gb_score, 2)

        return {
            "pitcher_id": row.get("player_id"),
            "name": row.get("player_name"),
            "era": era,
            "fip": fip,
            "gb_rate": gb_rate,
            "under_score": under_score,
        }

    def _default_pitcher_stats(self) -> dict[str, Any]:
        return {
            "pitcher_id": None,
            "name": "TBD",
            "era": 4.50,
            "fip": 4.50,
            "gb_rate": 45.0,
            "under_score": 5.0,
        }
