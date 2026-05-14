from typing import Any, Optional

"""
Dog Score Engine — rates each game's upset/moneyline underdog potential (0-100).

Weights:
  Home dog bonus        25%  — home underdogs cover at historic rates
  Pitcher advantage     25%  — dog's starter vs. favorite's starter
  Favorite fatigue      20%  — tired favorite = vulnerable
  Recent form           15%  — dog's last-10 W/L momentum
  Bullpen advantage     15%  — dog has fresher pen
"""

VERDICT_THRESHOLDS = [
    (80, "Strong Dog"),
    (65, "Lean Dog"),
    (50, "Watch"),
    (0,  "Fade"),
]


class DogScoreEngine:

    def score(
        self,
        game: dict[str, Any],
        away_fatigue: dict[str, Any],
        home_fatigue: dict[str, Any],
        away_pitcher: dict[str, Any],
        home_pitcher: dict[str, Any],
        away_bullpen: dict[str, Any],
        home_bullpen: dict[str, Any],
        moneyline: Optional[Any] = None,
        away_offense: Optional[Any] = None,
        home_offense: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Score the actual underdog side using real moneyline odds when available."""
        away_pitcher_score = away_pitcher.get("under_score", 5.0)
        home_pitcher_score = home_pitcher.get("under_score", 5.0)
        away_bullpen_score = away_bullpen.get("under_score", 5.0)
        home_bullpen_score = home_bullpen.get("under_score", 5.0)
        away_fatigue_score = away_fatigue.get("fatigue_score", 5.0)
        home_fatigue_score = home_fatigue.get("fatigue_score", 5.0)

        away_ml = (moneyline or {}).get("away_ml")
        home_ml = (moneyline or {}).get("home_ml")
        odds_dog_side = (moneyline or {}).get("dog_side")  # "away", "home", or None

        # Infer dog side from pitcher gap only when odds unavailable
        if odds_dog_side:
            inferred_dog_side = odds_dog_side
        else:
            inferred_dog_side = "away" if away_pitcher_score < home_pitcher_score else "home"

        away_dog = self._score_as_dog(
            is_home=False,
            team_pitcher_score=away_pitcher_score,
            opp_pitcher_score=home_pitcher_score,
            team_fatigue=away_fatigue_score,
            opp_fatigue=home_fatigue_score,
            team_bullpen=away_bullpen_score,
            opp_bullpen=home_bullpen_score,
            recent_form=away_offense,
            ml_odds=away_ml,
            is_actual_dog=(inferred_dog_side == "away"),
        )

        home_dog = self._score_as_dog(
            is_home=True,
            team_pitcher_score=home_pitcher_score,
            opp_pitcher_score=away_pitcher_score,
            team_fatigue=home_fatigue_score,
            opp_fatigue=away_fatigue_score,
            team_bullpen=home_bullpen_score,
            opp_bullpen=away_bullpen_score,
            recent_form=home_offense,
            ml_odds=home_ml,
            is_actual_dog=(inferred_dog_side == "home"),
        )

        return {
            "away_dog_score": away_dog["score"],
            "away_dog_verdict": away_dog["verdict"],
            "home_dog_score": home_dog["score"],
            "home_dog_verdict": home_dog["verdict"],
            "away_dog_detail": away_dog,
            "home_dog_detail": home_dog,
            "actual_dog_side": inferred_dog_side,
            "away_ml": away_ml,
            "home_ml": home_ml,
            "odds_sourced": odds_dog_side is not None,
        }

    def _score_as_dog(
        self,
        is_home: bool,
        team_pitcher_score: float,
        opp_pitcher_score: float,
        team_fatigue: float,
        opp_fatigue: float,
        team_bullpen: float,
        opp_bullpen: float,
        recent_form: Optional[Any],
        ml_odds: Optional[float] = None,
        is_actual_dog: bool = True,
    ) -> dict[str, Any]:
        # If this team is the favorite, return zero — they are not the dog play
        if not is_actual_dog:
            return {
                "score": 0.0,
                "verdict": "Favorite",
                "components": {},
                "ml_odds": ml_odds,
                "is_actual_dog": False,
            }

        # 1. Home dog bonus (0-10) — home dog is biggest signal in MLB betting
        home_bonus = 7.5 if is_home else 3.0

        # 2. Pitcher advantage (0-10) — dog's starter quality vs opponent
        pitcher_gap = team_pitcher_score - opp_pitcher_score  # positive = dog has better arm
        pitcher_score = max(0.0, min(10.0, 5.0 + pitcher_gap))

        # 3. Opponent fatigue (0-10) — tired favorite is more beatable
        opp_fatigue_score = min(10.0, opp_fatigue)  # higher fatigue = better for dog

        # 4. Recent form (0-10)
        form_score = self._parse_form(recent_form)

        # 5. Bullpen advantage (0-10)
        bullpen_gap = team_bullpen - opp_bullpen
        bullpen_score = max(0.0, min(10.0, 5.0 + bullpen_gap))

        weighted = (
            home_bonus    * 0.25 +
            pitcher_score * 0.25 +
            opp_fatigue_score * 0.20 +
            form_score    * 0.15 +
            bullpen_score * 0.15
        ) * 10.0

        final = round(max(0.0, min(100.0, weighted)), 1)
        verdict = self._get_verdict(final)

        return {
            "score": final,
            "verdict": verdict,
            "ml_odds": ml_odds,
            "is_actual_dog": True,
            "components": {
                "home_bonus": round(home_bonus, 2),
                "pitcher_advantage": round(pitcher_score, 2),
                "opp_fatigue": round(opp_fatigue_score, 2),
                "recent_form": round(form_score, 2),
                "bullpen_advantage": round(bullpen_score, 2),
            },
        }

    def _parse_form(self, form_data: Any) -> float:
        """
        Score the dog team's offensive form over last 10 games.
        A hot-hitting dog is far more dangerous as an upset pick.
        Uses team_offense data: runs_per_game_10d and streak.
        """
        if not form_data:
            return 5.0
        rpg = form_data.get("runs_per_game_10d", 4.5)
        # 2.0 rpg → 2.0,  4.5 rpg → 5.5,  7.0+ rpg → 9.0
        score = max(2.0, min(9.0, 2.0 + (rpg - 2.0) * (7.0 / 5.0)))
        return round(score, 2)

    def _get_verdict(self, score: float) -> str:
        for threshold, label in VERDICT_THRESHOLDS:
            if score >= threshold:
                return label
        return "Fade"


