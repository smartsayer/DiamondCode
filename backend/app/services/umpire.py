import httpx
from typing import Any, Optional
from app.config import get_settings

settings = get_settings()


class UmpireService:
    """
    Pulls umpire strike-zone tendencies from UmpScorecards.
    Their public API returns season-aggregated data per umpire.
    Endpoint: https://umpscorecards.com/api/umpires/{name_or_id}
    """

    BASE = settings.ump_scorecards_base_url

    # Fallback cache: known HP umpire tendencies (season-level run impact).
    # Positive = ump calls more strikes → fewer walks → run suppression → under-friendly.
    # Source: umpscorecards.com — refresh each season.
    KNOWN_UMPIRES: dict[str, dict[str, Any]] = {
        # Format: "Full Name": {calls_per_game_above_avg, favor_pitchers (bool)}
    }

    async def get_umpire_score(self, umpire_name: Optional[str]) -> dict[str, Any]:
        if not umpire_name:
            return self._neutral_umpire()

        # Try live API first
        data = await self._fetch_from_api(umpire_name)
        if data:
            return data

        # Fallback to local cache
        cached = self.KNOWN_UMPIRES.get(umpire_name)
        if cached:
            return self._score_from_cached(umpire_name, cached)

        # Return neutral but preserve the umpire name for display
        result = self._neutral_umpire()
        result["umpire_name"] = umpire_name
        return result

    async def _fetch_from_api(self, umpire_name: str) -> Optional[dict[str, Any]]:
        """
        UmpScorecards public endpoint — returns season stats per umpire.
        Format: GET https://umpscorecards.com/api/umpire?name=<Full+Name>
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.BASE}/umpire",
                    params={"name": umpire_name},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
        except httpx.RequestError:
            return None

        if not data:
            return None

        # UmpScorecards returns run impact (positive = ump favors pitchers = suppresses runs)
        run_impact = data.get("run_impact", 0.0) or 0.0
        favor_pitcher = 1.0 if run_impact < 0 else -1.0 if run_impact > 0 else 0.0
        extra_calls = abs(run_impact)

        under_score = self._compute_umpire_score(favor_pitcher, extra_calls)
        return {
            "umpire_name": umpire_name,
            "favor_pitcher": favor_pitcher,
            "run_impact": run_impact,
            "source": "umpscorecards_api",
            "under_score": under_score,
        }

    def _score_from_cached(self, name: str, cached: dict[str, Any]) -> dict[str, Any]:
        score = self._compute_umpire_score(
            cached.get("calls_per_game_above_avg", 0),
            cached.get("calls_per_game_above_avg", 0),
        )
        return {
            "umpire_name": name,
            "favor_pitcher": cached.get("favor_pitchers", False),
            "extra_calls_per_game": cached.get("calls_per_game_above_avg", 0),
            "source": "local_cache",
            "under_score": score,
        }

    def _compute_umpire_score(self, favor_pitcher: float, extra_calls: float) -> float:
        """
        Umpires who expand the zone (more called strikes) suppress scoring.
        favor_pitcher > 0 means pitcher-friendly → higher under score.
        Scale to 0-10 using a ±3 range around neutral.
        """
        raw = 5.0 + (favor_pitcher * 1.5) + (extra_calls * 0.5)
        return round(max(0.0, min(10.0, raw)), 2)

    def _neutral_umpire(self) -> dict[str, Any]:
        return {
            "umpire_name": "Unknown",
            "favor_pitcher": 0.0,
            "extra_calls_per_game": 0.0,
            "source": "default",
            "under_score": 5.0,
        }
