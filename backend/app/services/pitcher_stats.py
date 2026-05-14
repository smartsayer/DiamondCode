import httpx
from datetime import date
from typing import Any, Optional

CURRENT_SEASON = date.today().year


def _sf(v, default: float) -> float:
    """Safe float — handles MLB's '-.--' placeholder and None."""
    try:
        return float(v) if v not in (None, "", "-.--", "-") else default
    except (TypeError, ValueError):
        return default


class PitcherStatsService:
    """
    Pulls pitcher ERA, WHIP, K%, and GB% from two sources in priority order:
    1. FanGraphs JSON API (most reliable, includes GB%)
    2. MLB Stats API (fallback, no GB% but has ERA/WHIP)
    """

    MLB_BASE = "https://statsapi.mlb.com/api/v1"
    FG_BASE = "https://www.fangraphs.com/api/leaders/major-league/data"

    # FanGraphs player ID map for common pitchers (MLB ID → FG ID).
    # FanGraphs uses different IDs than MLB Stats API.
    # We match by name from the FanGraphs leaderboard instead.
    _fg_cache: dict[int, dict[str, Any]] = {}
    _fg_loaded: bool = False

    async def get_pitcher_score(self, pitcher_id: Optional[int], pitcher_name: Optional[str]) -> dict[str, Any]:
        if not pitcher_id and not pitcher_name:
            return self._default()

        # Try FanGraphs first (has GB%)
        fg = await self._from_fangraphs(pitcher_name)
        if fg:
            return fg

        # Fallback to MLB Stats API
        if pitcher_id:
            mlb = await self._from_mlb_api(pitcher_id, pitcher_name)
            if mlb:
                return mlb

        result = self._default()
        result["name"] = pitcher_name or "TBD"
        return result

    async def _from_fangraphs(self, pitcher_name: Optional[str]) -> Optional[dict[str, Any]]:
        if not pitcher_name:
            return None

        await self._load_fg_leaderboard()
        key = pitcher_name.strip().lower()
        data = self._fg_cache.get(key)
        if not data:
            return None

        era = data.get("ERA", 4.50) or 4.50
        whip = data.get("WHIP", 1.30) or 1.30
        k_pct = data.get("K%", 0.22) or 0.22
        gb_pct = data.get("GB%", 0.45) or 0.45

        if isinstance(k_pct, str) and "%" in k_pct:
            k_pct = float(k_pct.strip("%")) / 100
        if isinstance(gb_pct, str) and "%" in gb_pct:
            gb_pct = float(gb_pct.strip("%")) / 100

        under_score = self._compute_score(era, whip, float(k_pct), float(gb_pct))
        return {
            "name": pitcher_name,
            "era": round(float(era), 2),
            "whip": round(float(whip), 2),
            "k_pct": round(float(k_pct) * 100, 1),
            "gb_pct": round(float(gb_pct) * 100, 1),
            "source": "fangraphs",
            "under_score": under_score,
        }

    async def _load_fg_leaderboard(self) -> None:
        if self._fg_loaded:
            return
        params = {
            "age": "0",
            "pos": "all",
            "stats": "pit",
            "lg": "all",
            "qual": "0",
            "season": CURRENT_SEASON,
            "season1": CURRENT_SEASON,
            "ind": "0",
            "team": "0",
            "pageitems": "2000",
            "pagenum": "1",
            "type": "8",  # standard pitching stats
            "sortstat": "IP",
            "sortorder": "desc",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.FG_BASE, params=params)
                if resp.status_code != 200:
                    return
                payload = resp.json()
                rows = payload.get("data", [])
                for row in rows:
                    name = (row.get("PlayerName") or row.get("Name") or "").strip().lower()
                    if name:
                        self.__class__._fg_cache[name] = row
                self.__class__._fg_loaded = True
        except (httpx.RequestError, ValueError, KeyError):
            pass

    async def _from_mlb_api(self, pitcher_id: int, pitcher_name: Optional[str]) -> Optional[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{self.MLB_BASE}/people/{pitcher_id}/stats",
                    params={"stats": "season", "group": "pitching", "season": CURRENT_SEASON},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
        except httpx.RequestError:
            return None

        stats_list = data.get("stats", [])
        splits = stats_list[0].get("splits", []) if stats_list else []
        if not splits:
            return None

        stat = splits[0].get("stat", {})
        era = _sf(stat.get("era"), 4.50)
        whip = _sf(stat.get("whip"), 1.30)
        k9 = _sf(stat.get("strikeoutsPer9Inn"), 8.0)
        k_pct = k9 / 27.0  # approximate

        under_score = self._compute_score(era, whip, k_pct, 0.45)
        return {
            "name": pitcher_name or str(pitcher_id),
            "era": round(era, 2),
            "whip": round(whip, 2),
            "k_pct": round(k_pct * 100, 1),
            "gb_pct": None,
            "source": "mlb_api",
            "under_score": under_score,
        }

    def _compute_score(self, era: float, whip: float, k_pct: float, gb_pct: float) -> float:
        # ERA component (0–4): lower ERA → higher score
        era_score = max(0.0, min(4.0, (6.5 - era) * (4.0 / 4.0)))
        # WHIP component (0–2): lower WHIP → higher score
        whip_score = max(0.0, min(2.0, (1.7 - whip) * (2.0 / 0.7)))
        # K% component (0–2): higher K% → fewer balls in play → under-friendly
        k_score = max(0.0, min(2.0, (k_pct - 0.15) * (2.0 / 0.15)))
        # GB% component (0–2): more groundballs → less power → under-friendly
        gb_score = max(0.0, min(2.0, (gb_pct - 0.35) * (2.0 / 0.20)))
        return round(era_score + whip_score + k_score + gb_score, 2)

    async def get_pitcher_recent_form(self, pitcher_id: Optional[int]) -> dict[str, Any]:
        """Last 3 starts ERA — flags rolling hot vs. struggling trend."""
        neutral = {"recent_era": None, "recent_starts": 0, "trend": "neutral", "under_score_adj": 0.0}
        if not pitcher_id:
            return neutral

        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{self.MLB_BASE}/people/{pitcher_id}/stats",
                    params={"stats": "gameLog", "group": "pitching", "season": CURRENT_SEASON},
                )
                if resp.status_code != 200:
                    return neutral
                data = resp.json()
        except httpx.RequestError:
            return neutral

        splits = []
        for stat_group in data.get("stats", []):
            splits = stat_group.get("splits", [])
            if splits:
                break

        # Filter to actual starts (1+ IP)
        starts = [
            s for s in splits
            if _sf(s.get("stat", {}).get("inningsPitched"), 0.0) >= 1.0
        ]
        recent = starts[-3:] if len(starts) >= 3 else starts
        if not recent:
            return neutral

        total_er = sum(_sf(s.get("stat", {}).get("earnedRuns"), 0.0) for s in recent)
        total_ip = sum(_sf(s.get("stat", {}).get("inningsPitched"), 0.0) for s in recent)
        if total_ip < 1.0:
            return neutral

        recent_era = round((total_er / total_ip) * 9.0, 2)

        if recent_era <= 2.00:
            trend, adj = "dominant", 1.5
        elif recent_era <= 3.25:
            trend, adj = "hot", 0.75
        elif recent_era <= 4.50:
            trend, adj = "neutral", 0.0
        elif recent_era <= 6.00:
            trend, adj = "struggling", -0.75
        else:
            trend, adj = "cold", -1.5

        return {
            "recent_era": recent_era,
            "recent_starts": len(recent),
            "trend": trend,
            "under_score_adj": adj,
        }

    def _default(self) -> dict[str, Any]:
        return {
            "name": "TBD",
            "era": 4.50,
            "whip": 1.30,
            "k_pct": 22.0,
            "gb_pct": 45.0,
            "source": "default",
            "under_score": 5.0,
        }
