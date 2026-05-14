from typing import Any, Optional
from app.config import get_settings

settings = get_settings()

VERDICT_THRESHOLDS = [
    (80, "Lock"),
    (65, "Strong"),
    (50, "Moderate"),
    (0,  "Skip"),
]

"""
Weight breakdown (sums to 1.0):
  Park Factor       18%
  Pitcher Quality   22%  (includes platoon adjustment + recent form trend)
  Weather           11%
  Umpire Tendency    6%
  Bullpen Fatigue    6%
  Team Fatigue       7%
  Line Movement     10%
  Team Offense      20%  (10% each team — runs/game last 10, K% slump/streak)
"""


class ScoringEngine:

    def score_game(
        self,
        park_factor_data: dict[str, Any],
        away_pitcher_data: dict[str, Any],
        home_pitcher_data: dict[str, Any],
        weather_data: dict[str, Any],
        umpire_data: dict[str, Any],
        away_bullpen_data: dict[str, Any],
        home_bullpen_data: dict[str, Any],
        away_offense_data: Optional[dict[str, Any]] = None,
        home_offense_data: Optional[dict[str, Any]] = None,
        line_movement_data: Optional[dict[str, Any]] = None,
        fatigue_score: float = 5.0,
    ) -> dict[str, Any]:

        park_score    = self._get(park_factor_data)
        pitcher_score = min(10.0, (self._get(away_pitcher_data) + self._get(home_pitcher_data)) / 2.0)
        weather_score = self._get(weather_data)
        umpire_score  = self._get(umpire_data)
        bullpen_score = (self._get(away_bullpen_data) + self._get(home_bullpen_data)) / 2.0
        line_score    = self._get(line_movement_data) if line_movement_data else 5.0
        away_off      = self._get(away_offense_data) if away_offense_data else 5.0
        home_off      = self._get(home_offense_data) if home_offense_data else 5.0
        offense_score = (away_off + home_off) / 2.0

        total = (
            park_score    * 0.18 +
            pitcher_score * 0.22 +
            weather_score * 0.11 +
            umpire_score  * 0.06 +
            bullpen_score * 0.06 +
            fatigue_score * 0.07 +
            line_score    * 0.10 +
            offense_score * 0.20
        ) * 10.0

        total = round(max(0.0, min(100.0, total)), 1)

        return {
            "park_factor_score":   round(park_score, 2),
            "pitcher_score":       round(pitcher_score, 2),
            "weather_score":       round(weather_score, 2),
            "umpire_score":        round(umpire_score, 2),
            "bullpen_score":       round(bullpen_score, 2),
            "fatigue_score":       round(fatigue_score, 2),
            "line_movement_score": round(line_score, 2),
            "away_offense_score":  round(away_off, 2),
            "home_offense_score":  round(home_off, 2),
            "total_score":         total,
            "verdict":             self._verdict(total),
        }

    def _get(self, data: dict[str, Any]) -> float:
        return float((data or {}).get("under_score", 5.0))

    def _verdict(self, score: float) -> str:
        for threshold, label in VERDICT_THRESHOLDS:
            if score >= threshold:
                return label
        return "Skip"
