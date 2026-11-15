from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

PIPELINE_VERSION = "pipeline-0.1.0"
ANALYTICS_VERSION = "analytics-0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://monitor:monitor@localhost:5433/monitor"
    jwt_secret: str = "change-me"
    jwt_ttl_minutes: int = 12 * 60
    earthdata_token: str = ""
    llm_provider: str = "none"          # none | openai_compatible
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    cors_origins: str = "http://localhost:5173"
    history_start: str = "2024-01-01"
    cycle_days: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def districts_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "districts.yaml").read_text(encoding="utf-8"))


@lru_cache
def thresholds() -> dict:
    return yaml.safe_load((CONFIG_DIR / "thresholds.yaml").read_text(encoding="utf-8"))
