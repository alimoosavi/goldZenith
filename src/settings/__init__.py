"""Centralized configuration, populated from environment variables and .env.

Import the shared `config` singleton:

    from settings import config
    print(config.market_open, config.best_limits_url)

Environment variables (case-insensitive; also read from <repo>/.env):
  MARKET_OPEN          — TSE hEven-encoded open time (default: 84500 / 08:45:00)
  MARKET_CLOSE         — TSE hEven-encoded close time (default: 153000 / 15:30:00)
  TSETMC_CDN_BASE_URL  — base URL of the TSETMC CDN (default: http://cdn.tsetmc.com)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # hEven format: HHMMSS packed as an int (e.g. 84500 = 08:45:00).
    market_open: int = 84500     # stock pre-open start
    market_close: int = 153000   # widest: covers ETFs / funds past the 12:30 close

    tsetmc_cdn_base_url: str = "http://cdn.tsetmc.com"

    @field_validator("tsetmc_cdn_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @computed_field
    @property
    def best_limits_url(self) -> str:
        return f"{self.tsetmc_cdn_base_url}/api/BestLimits/{{ticker}}/{{deven}}"


config = Config()


__all__ = ["Config", "config"]
