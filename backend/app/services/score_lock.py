from typing import Any, Optional


class ScoreLockCache:
    """
    Locks pre-game scores once a game goes Live.

    Closing scores never change after first pitch — that's the whole point.
    Live scores are computed fresh from the locked closing scores + current
    game state.
    """

    _closing: dict[int, dict[str, Any]] = {}

    def get_or_lock(
        self,
        game_pk: Optional[int],
        current_state: str,
        scores: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Preview state → keep updating cache with the latest scores.
        Live/Final → return the locked closing scores (or current if never seen).
        """
        if game_pk is None:
            return scores
        if current_state == "Preview":
            self._closing[game_pk] = scores
            return scores
        return self._closing.get(game_pk, scores)

    def get_closing(self, game_pk: Optional[int]) -> Optional[dict[str, Any]]:
        if game_pk is None:
            return None
        return self._closing.get(game_pk)
