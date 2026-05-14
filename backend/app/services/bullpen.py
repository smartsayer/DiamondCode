from typing import Any
from datetime import date, timedelta


class BullpenService:
    """
    Estimates bullpen fatigue from recent pitcher appearance data.
    Uses MLB Stats API roster/game-log data pre-fetched by mlb_api.py.
    """

    FATIGUE_DAYS = 3  # look back window

    def score_bullpen_fatigue(self, bullpen_data: dict[str, Any]) -> dict[str, Any]:
        """
        Input: raw bullpen_data dict from MLBStatsAPI.get_bullpen_usage()
        Returns: fatigue metrics + 0-10 under score.

        Higher fatigue = bullpen less effective = more runs allowed = LOWER under score.
        Rested bullpen = lower score (under-friendly) = HIGHER under score.
        """
        all_pitchers = bullpen_data.get("relievers", [])
        if not all_pitchers:
            return self._neutral_bullpen()

        # Filter out starting pitchers — any pitcher with a 4+ IP appearance
        # in the lookback window is clearly a starter, not a reliever.
        cutoff = date.today() - timedelta(days=self.FATIGUE_DAYS)
        relievers = [p for p in all_pitchers if not self._is_starter(p.get("stats", []), cutoff)]

        if not relievers:
            return self._neutral_bullpen()

        fatigued_count = 0
        total_recent_ip = 0.0

        for reliever in relievers:
            recent_ip = self._get_recent_ip(reliever.get("stats", []), cutoff)
            total_recent_ip += recent_ip
            if recent_ip >= 1.0:
                fatigued_count += 1

        pct_fatigued = fatigued_count / max(len(relievers), 1)

        # Rested bullpen → fewer runs allowed → under-friendly → high score
        # Tired bullpen → more runs allowed → over-friendly → low score
        base = 7.0
        fatigue_penalty = pct_fatigued * 4.0
        ip_penalty = min(total_recent_ip * 0.1, 2.0)
        under_score = round(max(0.0, min(10.0, base - fatigue_penalty - ip_penalty)), 2)

        return {
            "total_relievers": len(relievers),
            "fatigued_count": fatigued_count,
            "pct_fatigued": round(pct_fatigued, 3),
            "total_recent_ip": round(total_recent_ip, 1),
            "under_score": under_score,
        }

    def _is_starter(self, stats: list[dict], cutoff: date) -> bool:
        """A pitcher is a starter if any recent appearance had 4+ IP."""
        for stat_group in stats:
            if stat_group.get("type", {}).get("displayName") != "gameLog":
                continue
            for split in stat_group.get("splits", []):
                game_date_str = split.get("date", "")
                try:
                    game_date = date.fromisoformat(game_date_str)
                except ValueError:
                    continue
                if game_date < cutoff:
                    continue
                raw_ip = split.get("stat", {}).get("inningsPitched", "0.0")
                if self._parse_ip(str(raw_ip)) >= 4.0:
                    return True
        return False

    def _get_recent_ip(self, stats: list[dict], cutoff: date) -> float:
        ip = 0.0
        for stat_group in stats:
            if stat_group.get("type", {}).get("displayName") != "gameLog":
                continue
            for split in stat_group.get("splits", []):
                game_date_str = split.get("date", "")
                try:
                    game_date = date.fromisoformat(game_date_str)
                except ValueError:
                    continue
                if game_date >= cutoff:
                    raw_ip = split.get("stat", {}).get("inningsPitched", "0.0")
                    ip += self._parse_ip(str(raw_ip))
        return ip

    def _parse_ip(self, ip_str: str) -> float:
        """Convert MLB innings pitched notation (e.g. '2.1' = 2⅓ innings) to decimal."""
        try:
            parts = ip_str.split(".")
            full = int(parts[0])
            thirds = int(parts[1]) if len(parts) > 1 else 0
            return full + thirds / 3.0
        except (ValueError, IndexError):
            return 0.0

    def _neutral_bullpen(self) -> dict[str, Any]:
        return {
            "total_relievers": 0,
            "fatigued_count": 0,
            "pct_fatigued": 0.0,
            "total_recent_ip": 0.0,
            "under_score": 5.0,
        }
