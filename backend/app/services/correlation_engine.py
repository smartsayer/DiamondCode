from typing import Any


class CorrelationEngine:
    """
    Flags games where the under score AND dog score align on the same ticket.
    This is DiamondCode's highest-confidence signal — two independent models
    pointing at the same game from different angles.
    """

    def analyze(
        self,
        under_score: float,
        home_dog_score: float,
        away_dog_score: float,
        line_movement: dict[str, Any],
        series_game_number: int = 1,
    ) -> dict[str, Any]:

        # Best dog side
        if home_dog_score >= away_dog_score:
            best_dog_score = home_dog_score
            best_dog_side = "home"
        else:
            best_dog_score = away_dog_score
            best_dog_side = "away"

        # Core correlation: strong under + strong dog on same game
        correlation_score = self._compute_correlation(
            under_score, best_dog_score, line_movement, series_game_number
        )

        alert = self._get_alert(under_score, best_dog_score, correlation_score, line_movement)

        return {
            "correlation_score": correlation_score,
            "best_dog_side": best_dog_side,
            "best_dog_score": best_dog_score,
            "alert": alert,
            "is_double_lock": under_score >= 75 and best_dog_score >= 65,
            "series_game": series_game_number,
            "line_signal": line_movement.get("signal", ""),
        }

    def _compute_correlation(
        self,
        under_score: float,
        dog_score: float,
        line_movement: dict[str, Any],
        series_game: int,
    ) -> float:
        base = (under_score * 0.5 + dog_score * 0.5)

        # Line movement bonus: sharp under money + dog play = rarest alignment
        line_movement_val = line_movement.get("movement", 0.0)
        if line_movement_val <= -1.0:
            base += 5.0
        elif line_movement_val <= -0.5:
            base += 2.5

        # Series game 1 bonus (ace typically starts, better quality game)
        if series_game == 1:
            base += 3.0
        elif series_game >= 3:
            base -= 2.0  # weaker starters, less predictable

        return round(max(0.0, min(100.0, base)), 1)

    def _get_alert(
        self,
        under_score: float,
        dog_score: float,
        correlation: float,
        line_movement: dict[str, Any],
    ) -> str:
        parts = []

        if under_score >= 80 and dog_score >= 80:
            parts.append("🔥 DOUBLE LOCK — Under + Dog both elite")
        elif under_score >= 75 and dog_score >= 65:
            parts.append("⚡ CORRELATION HIT — Under + Dog aligned")
        elif under_score >= 65 and dog_score >= 65:
            parts.append("✅ Both models agree on this game")

        movement = line_movement.get("movement", 0.0)
        if movement <= -1.0:
            parts.append("📉 Sharp under money confirmed by line drop")
        elif movement >= 1.0:
            parts.append("📈 Line rose — public on over, sharp on under?")

        if not parts:
            return ""
        return " · ".join(parts)
