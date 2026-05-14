from typing import Any, Optional


class LiveScoreAdjuster:
    """
    Computes live under/dog scores from locked closing scores + current game state.
    Closing scores remain fixed; these are reactive scores that move with the game.
    """

    def adjust_under(
        self,
        closing_under_score: float,
        live_data: dict[str, Any],
        closing_total: Optional[float],
    ) -> dict[str, Any]:
        """
        Live under tracks how the game is pacing vs. the closing total.
        Behind pace → score climbs. Ahead of pace → score collapses.
        Past the total → 0.
        """
        away = live_data.get("away_runs") or 0
        home = live_data.get("home_runs") or 0
        inning = live_data.get("inning") or 0
        total_runs = away + home

        # Game already over the total — under is dead
        if closing_total and total_runs >= closing_total:
            return {
                "live_under_score": 0.0,
                "delta": -closing_under_score,
                "pace_note": f"Total exceeded ({total_runs} ≥ {closing_total})",
            }

        if inning < 1 or not closing_total:
            return {
                "live_under_score": round(closing_under_score, 1),
                "delta": 0.0,
                "pace_note": "Awaiting first pitch",
            }

        # Expected pace at this point in the game
        innings_played = max(0.5, inning - 0.5)  # mid-inning average
        expected = (closing_total / 9.0) * innings_played
        delta_runs = expected - total_runs  # positive = behind pace

        # Each run under pace = +6 score; each run over = -8 score (asymmetric)
        adjustment = delta_runs * (6.0 if delta_runs > 0 else 8.0)

        # Late-game compression: if past inning 6 and well behind pace, big bump
        if inning >= 6 and delta_runs >= 1.5:
            adjustment += 12

        # If past inning 7 and within 1 run of total, danger
        if inning >= 7 and closing_total and (closing_total - total_runs) <= 1:
            adjustment -= 15

        live = max(0.0, min(100.0, closing_under_score + adjustment))
        runs_left = (closing_total - total_runs) if closing_total else None

        if delta_runs > 1.5:
            note = f"On pace for under by {delta_runs:.1f} runs"
        elif delta_runs < -1.5:
            note = f"Pacing OVER by {abs(delta_runs):.1f}"
        else:
            note = f"Tracking near total ({runs_left} runs left)"

        return {
            "live_under_score": round(live, 1),
            "delta": round(live - closing_under_score, 1),
            "pace_note": note,
        }

    def adjust_dog(
        self,
        closing_dog_score: float,
        live_data: dict[str, Any],
        dog_side: Optional[str],
    ) -> dict[str, Any]:
        """
        Live dog reflects whether the underdog is in the game.
        Leading → big bump. Tied late → bump. Losing badly late → 0.
        """
        if not dog_side:
            return {"live_dog_score": round(closing_dog_score, 1), "delta": 0.0, "pace_note": "No dog side"}

        away = live_data.get("away_runs") or 0
        home = live_data.get("home_runs") or 0
        inning = live_data.get("inning") or 0

        dog_runs = away if dog_side == "away" else home
        fav_runs = home if dog_side == "away" else away
        diff = dog_runs - fav_runs

        if inning < 1:
            return {
                "live_dog_score": round(closing_dog_score, 1),
                "delta": 0.0,
                "pace_note": "Awaiting first pitch",
            }

        if diff > 0:
            # Dog winning — score climbs sharply, more so as innings progress
            adjustment = 18 + (diff * 6) + max(0, (inning - 4) * 4)
            note = f"Dog leading by {diff}"
        elif diff == 0:
            adjustment = 6 + (inning * 1.5)
            note = f"Tied through {inning}"
        else:
            adjustment = (diff * 9) - max(0, (inning - 5) * 6)
            note = f"Dog down {abs(diff)} in {inning}"
            # Buried — past inning 7 and down 4+
            if inning >= 7 and diff <= -4:
                return {"live_dog_score": 0.0, "delta": -closing_dog_score, "pace_note": f"Dog buried ({abs(diff)} down in {inning})"}

        live = max(0.0, min(100.0, closing_dog_score + adjustment))
        return {
            "live_dog_score": round(live, 1),
            "delta": round(live - closing_dog_score, 1),
            "pace_note": note,
        }
