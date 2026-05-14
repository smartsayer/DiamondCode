import httpx
import asyncio
from datetime import date, timedelta
from typing import Any, Optional

MLB_BASE = "https://statsapi.mlb.com/api/v1"
CURRENT_SEASON = date.today().year


def _sf(v, default: float) -> float:
    try:
        return float(v) if v not in (None, "", "-.--", "-") else default
    except (TypeError, ValueError):
        return default


class TeamOffenseService:
    """
    Team batting stats: season K%/OBP + actual runs scored last 10 games via schedule.
    Cold offense = under signal. Hot dog team = upset potential.
    """

    async def get_team_offense(self, team_id: Optional[int]) -> dict[str, Any]:
        if not team_id:
            return self._neutral()

        season_stats, recent_runs = await asyncio.gather(
            self._get_season_stats(team_id),
            self._get_recent_runs(team_id),
        )

        if not recent_runs and not season_stats:
            return self._neutral()

        runs_per_game = round(sum(recent_runs) / len(recent_runs), 2) if recent_runs else 4.5
        k_pct = season_stats.get("k_pct", 0.22)
        obp = season_stats.get("obp", 0.320)

        # Under score: fewer runs + high K% = under-friendly
        # 2.0 rpg → 9.0,  4.5 rpg → 5.0,  7.5+ rpg → 1.0
        rpg_score = max(1.0, min(9.0, 9.0 - ((runs_per_game - 2.0) / 1.375)))
        k_bonus = max(-1.0, min(1.5, (k_pct - 0.22) * 7.0))
        under_score = round(min(10.0, max(0.0, rpg_score + k_bonus)), 2)

        if runs_per_game >= 5.5:
            streak = "hot"
        elif runs_per_game <= 3.2:
            streak = "cold"
        else:
            streak = "neutral"

        return {
            "team_id": team_id,
            "games_sampled": len(recent_runs),
            "runs_per_game_10d": runs_per_game,
            "recent_game_runs": recent_runs,
            "k_pct_season": round(k_pct * 100, 1),
            "obp_season": round(obp, 3),
            "under_score": under_score,
            "streak": streak,
        }

    async def _get_season_stats(self, team_id: int) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{MLB_BASE}/teams/{team_id}/stats",
                    params={"stats": "season", "group": "hitting", "season": CURRENT_SEASON},
                )
                if resp.status_code != 200:
                    return {}
                data = resp.json()
        except httpx.RequestError:
            return {}

        for stat_group in data.get("stats", []):
            splits = stat_group.get("splits", [])
            if splits:
                s = splits[0].get("stat", {})
                at_bats = int(s.get("atBats", 0) or 0)
                ks = int(s.get("strikeOuts", 0) or 0)
                obp = _sf(s.get("obp"), 0.320)
                k_pct = ks / max(at_bats, 1)
                return {"k_pct": k_pct, "obp": obp}
        return {}

    async def _get_recent_runs(self, team_id: int) -> list[int]:
        today = date.today()
        start = today - timedelta(days=18)  # enough window to get 10 completed games
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{MLB_BASE}/schedule",
                    params={
                        "teamId": team_id,
                        "sportId": 1,
                        "startDate": start.strftime("%Y-%m-%d"),
                        "endDate": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
                        "hydrate": "linescore",
                    },
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except httpx.RequestError:
            return []

        runs = []
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                ls = g.get("linescore", {})
                teams = g.get("teams", {})
                is_home = teams.get("home", {}).get("team", {}).get("id") == team_id
                if is_home:
                    r = ls.get("teams", {}).get("home", {}).get("runs")
                else:
                    r = ls.get("teams", {}).get("away", {}).get("runs")
                if r is not None:
                    runs.append(int(r))

        return runs[-10:] if len(runs) >= 10 else runs

    def _neutral(self) -> dict[str, Any]:
        return {
            "team_id": None,
            "games_sampled": 0,
            "runs_per_game_10d": 4.5,
            "recent_game_runs": [],
            "k_pct_season": 22.0,
            "obp_season": 0.320,
            "under_score": 5.0,
            "streak": "neutral",
        }
