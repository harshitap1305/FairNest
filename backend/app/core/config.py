"""Application configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_ENV = _BACKEND_DIR.parent / ".env"


class Settings(BaseSettings):
    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017/?replicaSet=rs0"
    MONGO_DB: str = "fairnest"

    # JWT
    JWT_SECRET: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    JWT_ACCESS_MINUTES: int = 15
    REFRESH_DAYS: int = 7

    # Cookies / CORS
    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"

    # Freeze window
    FREEZE_HOURS_DEFAULT: int = 48

    # Logging
    LOG_LEVEL: str = "INFO"

    # Bootstrap
    BOOTSTRAP_SUPER_ADMIN_EMAIL: str = ""
    ALLOWED_EMAIL_DOMAINS: str = ""  # comma-separated; empty = allow all

    # Credits
    C_INIT: int = 3
    C_MIN: int = 0
    C_MAX: int = 10

    # Scheduling
    MIN_WINDOW_MINUTES: int = 60

    model_config = {
        "env_file": (str(_ROOT_ENV), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_email_domains_list(self) -> list[str]:
        return [d.strip().lower() for d in self.ALLOWED_EMAIL_DOMAINS.split(",") if d.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
