from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from typing import Any, Optional

from app.services.data_collector import DataCollector
from app.schemas.game import DailySlateResponse, GameScoreResponse

router = APIRouter(prefix="/games", tags=["games"])


def get_collector() -> DataCollector:
    return DataCollector()


@router.get("/slate", response_model=dict[str, Any])
async def get_daily_slate(
    game_date: Optional[date] = Query(None, description="YYYY-MM-DD, defaults to today"),
    collector: DataCollector = Depends(get_collector),
):
    """
    Return today's full game slate scored and ranked highest→lowest.
    Each game includes component scores and a Lock/Strong/Moderate/Skip verdict.
    """
    target = game_date or date.today()
    try:
        games = await collector.collect_and_score_slate(target)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data collection failed: {exc}")

    return {
        "date": target.isoformat(),
        "total_games": len(games),
        "scored_games": sum(1 for g in games if g.get("is_data_complete")),
        "games": games,
    }


@router.get("/slate/{game_pk}", response_model=dict[str, Any])
async def get_game_detail(
    game_pk: int,
    collector: DataCollector = Depends(get_collector),
):
    """Return full score breakdown for a single game including raw component data."""
    games = await collector.collect_and_score_slate()
    match = next((g for g in games if g.get("game_pk") == game_pk), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Game {game_pk} not found in today's slate")
    return match


@router.get("/ai-picks", response_model=dict[str, Any])
async def get_ai_picks(
    game_date: Optional[date] = Query(None, description="YYYY-MM-DD, defaults to today"),
    collector: DataCollector = Depends(get_collector),
):
    """Top under recs, way-under candidates, top dog plays, plus a 3-4 leg parlay."""
    target = game_date or date.today()
    try:
        return await collector.collect_with_ai(target)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI picks failed: {exc}")


@router.get("/schedule/raw")
async def get_raw_schedule(
    game_date: Optional[date] = Query(None),
    collector: DataCollector = Depends(get_collector),
):
    """Raw MLB Stats API schedule for debugging."""
    target = game_date or date.today()
    return await collector.mlb.get_schedule(target)
