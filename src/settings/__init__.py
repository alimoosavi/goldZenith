"""Centralized configuration, populated from environment variables and .env.

Import the shared `config` singleton:

    from settings import config
    print(config.market_open, config.tsetmc_cdn_base_url)

Environment variables (case-insensitive; also read from <repo>/.env):
  MARKET_OPEN             — TSE hEven-encoded open time (default: 84500 / 08:45:00)
  MARKET_CLOSE            — TSE hEven-encoded close time (default: 153000 / 15:30:00)
  TSETMC_CDN_BASE_URL     — base URL of the TSETMC CDN (default: http://cdn.tsetmc.com)
  PARSIAN_SIGNALR_URL     — Parsian broker SignalR hub WebSocket URL
  PASARGAD_SIGNALR_URL    — Pasargad broker SignalR hub WebSocket URL
  PASARGAD_API_BASE_URL   — Pasargad REST API base (e.g. https://pasargad-signal.tsetab.ir)
  PASARGAD_AUTH_TOKEN     — Pasargad bearer token (used in WS query + REST headers)
  PASARGAD_COOKIE         — Pasargad cookie value sent on REST subscribe calls
  DATA_DIR                — Local directory for runtime artefacts / logs.
                            Relative paths resolve against the repo root.
  ORDERBOOKS_DIR          — Directory holding `{ticker}_{jalali}.parquet`
                            per-day orderbook snapshots (default: data/orderbooks).
  TRADES_DIR              — Directory holding `{ticker}_{jalali}.parquet`
                            per-day trade ticks (default: data/trades).
  REDIS_URI               — Redis host / connection URI (default: localhost).
  REDIS_PORT              — Redis port (default: 6379).
  INSTRUMENTS_FILE        — YAML registry mapping isin ↔ ins_code ↔ symbol
                            (default: data/instruments.yaml). Relative paths
                            resolve against the repo root.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


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

    parsian_signalr_url: str = "wss://signal.parsianbroker.com/SignalHub"
    pasargad_signalr_url: str = "wss://pasargad-signal.tsetab.ir/SignalHub"
    pasargad_api_base_url: str = "https://pasargad-signal.tsetab.ir"

    pasargad_auth_token: str = ""
    pasargad_cookie: str = ""

    data_dir: Path = Path("data")
    orderbooks_dir: Path = Path("data/orderbooks")
    trades_dir: Path = Path("data/trades")

    redis_uri: str = "localhost"
    redis_port: int = 6379

    instruments_file: Path = Path("data/instruments.yaml")

    @field_validator("tsetmc_cdn_base_url", "pasargad_api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("data_dir", "orderbooks_dir", "trades_dir", "instruments_file")
    @classmethod
    def _resolve_path(cls, v: Path | str) -> Path:
        p = Path(v)
        return p if p.is_absolute() else _PROJECT_ROOT / p


config = Config()


__all__ = ["Config", "config"]
