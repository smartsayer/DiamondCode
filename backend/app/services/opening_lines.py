"""
Opening-line cache — snapshots the first total/ML we see for each (game_pk, date)
so the frontend can show OPENING → CURRENT movement (the sharp-money signal).

In-memory + JSON-on-disk for some persistence across container restarts.
Lost data is OK — we'll just snapshot whatever is current as the new "opening."
"""
import json
import os
from datetime import date as Date
from typing import Any, Optional

CACHE_PATH = "/tmp/diamondcode_opening_lines.json"


class OpeningLineCache:
    """First-seen line snapshot per (game_pk, date). Populated lazily on each fetch."""

    _cache: dict[str, dict[str, Any]] = {}
    _loaded = False

    @classmethod
    def _load(cls) -> None:
        if cls._loaded:
            return
        cls._loaded = True
        if not os.path.exists(CACHE_PATH):
            return
        try:
            with open(CACHE_PATH) as f:
                cls._cache = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            cls._cache = {}

    @classmethod
    def _save(cls) -> None:
        try:
            tmp = CACHE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(cls._cache, f)
            os.replace(tmp, CACHE_PATH)
        except OSError:
            pass

    @classmethod
    def _key(cls, game_pk: Optional[int], game_date: Optional[Date]) -> Optional[str]:
        if game_pk is None:
            return None
        d = (game_date or Date.today()).isoformat()
        return f"{d}:{game_pk}"

    @classmethod
    def snapshot_or_get(
        cls,
        game_pk: Optional[int],
        game_date: Optional[Date],
        current_total: Optional[float],
        current_away_ml: Optional[float],
        current_home_ml: Optional[float],
    ) -> dict[str, Any]:
        """
        Return the opening-line snapshot for this game/date.
        On first call (when no snapshot exists) AND we have at least one current
        value, store the current values as the opening snapshot.
        """
        cls._load()
        key = cls._key(game_pk, game_date)
        if key is None:
            return {"opening_total": None, "opening_away_ml": None, "opening_home_ml": None}

        existing = cls._cache.get(key)
        if existing is None:
            # Only snapshot once we actually have at least one real value
            if current_total is None and current_away_ml is None and current_home_ml is None:
                return {"opening_total": None, "opening_away_ml": None, "opening_home_ml": None}
            existing = {
                "opening_total": current_total,
                "opening_away_ml": current_away_ml,
                "opening_home_ml": current_home_ml,
            }
            cls._cache[key] = existing
            cls._save()
            return existing

        # Backfill any field that wasn't there at first snapshot but IS now
        changed = False
        if existing.get("opening_total") is None and current_total is not None:
            existing["opening_total"] = current_total
            changed = True
        if existing.get("opening_away_ml") is None and current_away_ml is not None:
            existing["opening_away_ml"] = current_away_ml
            changed = True
        if existing.get("opening_home_ml") is None and current_home_ml is not None:
            existing["opening_home_ml"] = current_home_ml
            changed = True
        if changed:
            cls._cache[key] = existing
            cls._save()

        return existing

    @classmethod
    def reset_date(cls, game_date: Date) -> None:
        """Wipe one date's cache — used by tests."""
        cls._load()
        prefix = f"{game_date.isoformat()}:"
        cls._cache = {k: v for k, v in cls._cache.items() if not k.startswith(prefix)}
        cls._save()
