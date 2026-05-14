import asyncio
import httpx
from typing import Any, Optional
from datetime import date

MLB_BASE = "https://statsapi.mlb.com/api/v1"
CURRENT_SEASON = date.today().year


class PlatoonSplitsService:
    """
    Pulls pitcher splits vs LHB and RHB from the MLB Stats API.
    Estimates lineup handedness from team roster.
    """

    async def get_pitcher_matchup_score(
        self,
        pitcher_id: Optional[int],
        opponent_team_id: Optional[int],
        base_pitcher_score: float = 5.0,
    ) -> dict[str, Any]:
        if not pitcher_id or not opponent_team_id:
            return {"under_score": base_pitcher_score, "adjustment": 0.0, "notes": "No split data"}

        splits, lineup_pct = await asyncio.gather(
            self._get_pitcher_splits(pitcher_id),
            self._estimate_lineup_handedness(opponent_team_id),
        )

        if not splits:
            return {"under_score": base_pitcher_score, "adjustment": 0.0, "notes": "No split data"}

        same_hand_pct = lineup_pct.get("same_pct", 0.4)
        opp_hand_pct = lineup_pct.get("opp_pct", 0.6)

        same_era = splits.get("vs_same_hand", {}).get("era", 3.50)
        opp_era = splits.get("vs_opp_hand", {}).get("era", 4.50)

        weighted_era = (same_era * same_hand_pct) + (opp_era * opp_hand_pct)
        adjusted_score = max(0.0, min(10.0, (6.5 - weighted_era) * (10.0 / 5.0)))
        adjustment = round(adjusted_score - base_pitcher_score, 2)

        return {
            "under_score": round(adjusted_score, 2),
            "adjustment": adjustment,
            "weighted_era": round(weighted_era, 2),
            "vs_same_hand_era": round(same_era, 2),
            "vs_opp_hand_era": round(opp_era, 2),
            "lineup_opp_pct": round(opp_hand_pct * 100, 1),
            "notes": f"Lineup {round(opp_hand_pct*100)}% opposite-hand batters",
        }

    async def _get_pitcher_splits(self, pitcher_id: int) -> Optional[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{MLB_BASE}/people/{pitcher_id}/stats",
                    params={
                        "stats": "statSplits",
                        "group": "pitching",
                        "season": CURRENT_SEASON,
                        "sitCodes": "vl,vr",
                    },
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
        except httpx.RequestError:
            return None

        def _sf(v, default: float) -> float:
            try:
                return float(v) if v not in (None, "", "-.--", "-") else default
            except (TypeError, ValueError):
                return default

        result = {}
        for stat_group in data.get("stats", []):
            for split in stat_group.get("splits", []):
                code = split.get("split", {}).get("code", "")
                stat = split.get("stat", {})
                era = _sf(stat.get("era"), 4.50)
                whip = _sf(stat.get("whip"), 1.30)
                if code == "vl":
                    result["vs_left"] = {"era": era, "whip": whip}
                elif code == "vr":
                    result["vs_right"] = {"era": era, "whip": whip}

        if not result:
            return None

        return {
            "vs_same_hand": result.get("vs_right", {"era": 3.50}),
            "vs_opp_hand": result.get("vs_left", {"era": 4.50}),
        }

    async def _estimate_lineup_handedness(self, team_id: int) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{MLB_BASE}/teams/{team_id}/roster",
                    params={"rosterType": "active", "hydrate": "person(batSide)"},
                )
                if resp.status_code != 200:
                    return {"same_pct": 0.4, "opp_pct": 0.6}
                data = resp.json()
        except httpx.RequestError:
            return {"same_pct": 0.4, "opp_pct": 0.6}

        lefties = righties = 0
        for player in data.get("roster", []):
            if player.get("position", {}).get("type") in ("Pitcher", "Two-Way Player"):
                continue
            side = player.get("person", {}).get("batSide", {}).get("code", "R")
            if side in ("L", "S"):
                lefties += 1
            else:
                righties += 1

        total = lefties + righties or 1
        return {
            "lefties": lefties,
            "righties": righties,
            "left_pct": round(lefties / total, 3),
            "right_pct": round(righties / total, 3),
            "same_pct": round(righties / total, 3),
            "opp_pct": round(lefties / total, 3),
        }
