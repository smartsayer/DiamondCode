import httpx
from typing import Any
from app.config import get_settings

settings = get_settings()

# Stadium coordinates keyed by MLB venue ID
STADIUM_COORDS: dict[int, dict[str, float]] = {
    1:    {"lat": 39.2838, "lon": -76.6218, "orientation_deg": 35},   # Camden Yards (NE)
    2:    {"lat": 42.3467, "lon": -71.0972, "orientation_deg": 95},   # Fenway (E)
    3:    {"lat": 40.8296, "lon": -73.9262, "orientation_deg": 45},   # Yankee Stadium
    4:    {"lat": 27.7683, "lon": -82.6534, "orientation_deg": 0},    # Tropicana (dome)
    5:    {"lat": 43.6414, "lon": -79.3894, "orientation_deg": 0},    # Rogers Centre (dome)
    7:    {"lat": 41.8300, "lon": -87.6339, "orientation_deg": 170},  # Guaranteed Rate
    10:   {"lat": 41.4962, "lon": -81.6852, "orientation_deg": 348},  # Progressive Field
    17:   {"lat": 42.3390, "lon": -83.0485, "orientation_deg": 350},  # Comerica Park
    19:   {"lat": 39.0517, "lon": -94.4803, "orientation_deg": 45},   # Kauffman
    14:   {"lat": 44.9817, "lon": -93.2778, "orientation_deg": 350},  # Target Field
    11:   {"lat": 29.7573, "lon": -95.3555, "orientation_deg": 0},    # Minute Maid (retractable)
    12:   {"lat": 32.7473, "lon": -97.0820, "orientation_deg": 0},    # Globe Life (retractable)
    13:   {"lat": 33.8907, "lon": -84.4677, "orientation_deg": 345},  # Truist Park
    16:   {"lat": 25.7781, "lon": -80.2197, "orientation_deg": 0},    # loanDepot (retractable)
    18:   {"lat": 40.7571, "lon": -73.8458, "orientation_deg": 5},    # Citi Field
    22:   {"lat": 39.9061, "lon": -75.1665, "orientation_deg": 50},   # Citizens Bank Park
    32:   {"lat": 38.8730, "lon": -77.0074, "orientation_deg": 65},   # Nationals Park
    21:   {"lat": 38.6226, "lon": -90.1928, "orientation_deg": 345},  # Busch Stadium
    23:   {"lat": 41.9484, "lon": -87.6553, "orientation_deg": 90},   # Wrigley Field
    24:   {"lat": 39.0974, "lon": -84.5064, "orientation_deg": 350},  # GABP
    25:   {"lat": 40.4469, "lon": -80.0057, "orientation_deg": 5},    # PNC Park
    31:   {"lat": 33.4453, "lon": -112.0667, "orientation_deg": 0},   # Chase Field (retractable)
    29:   {"lat": 34.0739, "lon": -118.2400, "orientation_deg": 350}, # Dodger Stadium
    2392: {"lat": 37.7786, "lon": -122.3893, "orientation_deg": 95},  # Oracle Park
    2395: {"lat": 32.7076, "lon": -117.1570, "orientation_deg": 300}, # Petco Park
    680:  {"lat": 39.7559, "lon": -104.9942, "orientation_deg": 345}, # Coors Field
    2394: {"lat": 47.5914, "lon": -122.3325, "orientation_deg": 28},  # T-Mobile Park
    2681: {"lat": 37.7516, "lon": -122.2005, "orientation_deg": 60},  # Oakland Coliseum
}

DOME_OR_RETRACTABLE = {4, 5, 11, 12, 16, 31}


class WeatherService:

    async def get_game_weather(self, venue_id: int) -> dict[str, Any]:
        if venue_id in DOME_OR_RETRACTABLE:
            # Domes are weather-neutral. No air, no wind, no signal.
            # Returning 5.0 (true neutral) instead of 7.0 — refuse to fake
            # influence we don't have. The model should not get free under
            # credit for a controlled environment.
            return {
                "venue_id": venue_id,
                "is_dome": True,
                "temp_f": 72,
                "wind_mph": 0,
                "wind_dir_deg": 0,
                "humidity_pct": 50,
                "conditions": "Dome/Retractable",
                "under_score": 5.0,
                "notes": "Dome — weather neutral (no signal)",
            }

        coords = STADIUM_COORDS.get(venue_id)
        if not coords or not settings.openweather_api_key:
            return self._neutral_weather(venue_id)

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": coords["lat"],
            "lon": coords["lon"],
            "units": "imperial",
            "appid": settings.openweather_api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return self._neutral_weather(venue_id)
                data = resp.json()
        except httpx.RequestError:
            return self._neutral_weather(venue_id)

        temp_f = data.get("main", {}).get("temp", 72)
        humidity = data.get("main", {}).get("humidity", 50)
        wind_speed = data.get("wind", {}).get("speed", 0)
        wind_dir = data.get("wind", {}).get("deg", 0)
        conditions = data.get("weather", [{}])[0].get("main", "Clear")

        under_score = self._compute_weather_score(
            temp_f, wind_speed, wind_dir,
            coords.get("orientation_deg", 0),
            humidity, conditions
        )

        return {
            "venue_id": venue_id,
            "is_dome": False,
            "temp_f": temp_f,
            "wind_mph": wind_speed,
            "wind_dir_deg": wind_dir,
            "humidity_pct": humidity,
            "conditions": conditions,
            "under_score": under_score,
        }

    def _compute_weather_score(
        self,
        temp_f: float,
        wind_mph: float,
        wind_dir_deg: float,
        orientation_deg: float,
        humidity: float,
        conditions: str,
    ) -> float:
        """
        Threshold-gated weather scoring. Returns 5.0 (neutral) unless a condition
        is SIGNIFICANT enough to justify moving the needle. Refuses to fake influence
        on a calm 72°F day — the model should only earn weight when there's real signal.
        """
        score = 5.0
        signals = 0

        # Temperature — only extremes move the score
        if temp_f < 55:
            score += 2.0 if temp_f < 48 else 1.2   # genuine cold suppression
            signals += 1
        elif temp_f > 88:
            score -= 1.2 if temp_f > 93 else 0.8   # heat helps offense
            signals += 1
        # 55-88°F = neutral, no adjustment (don't fake influence)

        # Wind — only when speed > 8mph AND blowing clear in/out
        if wind_mph >= 8.0:
            angle_diff = abs((wind_dir_deg - orientation_deg + 360) % 360)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            if angle_diff > 140:        # blowing IN (toward plate) = HR suppressed
                score += min(wind_mph * 0.10, 2.2)
                signals += 1
            elif angle_diff < 40:       # blowing OUT to CF = HR-friendly
                score -= min(wind_mph * 0.10, 2.2)
                signals += 1
            # crosswinds 40-140° = no clear directional effect, skip

        # Humidity — only true extremes matter (ball carry physics)
        if humidity > 78:
            score += 0.6
            signals += 1
        elif humidity < 28:
            score -= 0.6
            signals += 1

        # Precipitation — always significant when present
        if conditions in ("Rain", "Drizzle", "Thunderstorm"):
            score += 1.2
            signals += 1

        # If no condition was significant, the weather has no edge to offer.
        # Lock to true neutral so we don't accidentally pile on micro-adjustments.
        if signals == 0:
            return 5.0

        return round(max(0.0, min(10.0, score)), 2)

    def _neutral_weather(self, venue_id: int) -> dict[str, Any]:
        return {
            "venue_id": venue_id,
            "is_dome": False,
            "temp_f": 72,
            "wind_mph": 5,
            "wind_dir_deg": 0,
            "humidity_pct": 50,
            "conditions": "Unknown",
            "under_score": 5.0,
        }
