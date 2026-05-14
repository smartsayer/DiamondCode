from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "DiamondCode"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://diamondcode:password@localhost:5432/diamondcode"

    # External APIs
    openweather_api_key: str = ""
    odds_api_key: str = ""
    baseball_savant_base_url: str = "https://baseballsavant.mlb.com"
    mlb_stats_base_url: str = "https://statsapi.mlb.com/api/v1"
    ump_scorecards_base_url: str = "https://umpscorecards.com/api"

    # Scoring weights (must sum to 1.0)
    weight_park_factor: float = 0.30
    weight_pitcher: float = 0.30
    weight_weather: float = 0.20
    weight_umpire: float = 0.10
    weight_bullpen: float = 0.10

    # Cache TTL in seconds
    schedule_cache_ttl: int = 300
    weather_cache_ttl: int = 1800

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
