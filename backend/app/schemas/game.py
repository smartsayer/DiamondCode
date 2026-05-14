from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import date, datetime


class ComponentScore(BaseModel):
    score: float = Field(ge=0, le=10)
    raw_data: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class GameScoreResponse(BaseModel):
    game_pk: int
    game_date: date
    away_team: str
    home_team: str
    venue: Optional[str]
    game_time_utc: Optional[datetime]

    # Component scores (0-10)
    park_factor_score: Optional[float]
    pitcher_score: Optional[float]
    weather_score: Optional[float]
    umpire_score: Optional[float]
    bullpen_score: Optional[float]

    # Composite (0-100)
    total_score: Optional[float]
    verdict: Optional[str]

    over_under_line: Optional[float]
    is_data_complete: bool

    class Config:
        from_attributes = True


class DailySlateResponse(BaseModel):
    date: date
    games: list[GameScoreResponse]
    total_games: int
    scored_games: int


class ScoreBreakdown(BaseModel):
    game_pk: int
    away_team: str
    home_team: str
    total_score: float
    verdict: str
    components: dict[str, ComponentScore]
