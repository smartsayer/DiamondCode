from sqlalchemy import Column, Integer, String, Float, DateTime, Date, JSON, Boolean
from sqlalchemy.sql import func
from app.database import Base


class GameScore(Base):
    __tablename__ = "game_scores"

    id = Column(Integer, primary_key=True, index=True)
    game_pk = Column(Integer, unique=True, index=True, nullable=False)
    game_date = Column(Date, index=True, nullable=False)

    # Teams
    away_team = Column(String(50), nullable=False)
    home_team = Column(String(50), nullable=False)
    venue = Column(String(100))
    game_time_utc = Column(DateTime(timezone=True))

    # Raw scores per component (0-10)
    park_factor_score = Column(Float)
    pitcher_score = Column(Float)
    weather_score = Column(Float)
    umpire_score = Column(Float)
    bullpen_score = Column(Float)

    # Composite weighted score (0-100)
    total_score = Column(Float)
    verdict = Column(String(20))  # Lock, Strong, Moderate, Skip

    # Raw data snapshots for auditability
    park_factor_data = Column(JSON)
    pitcher_data = Column(JSON)
    weather_data = Column(JSON)
    umpire_data = Column(JSON)
    bullpen_data = Column(JSON)

    over_under_line = Column(Float)
    is_data_complete = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
