"""Centralized configuration, populated from environment variables and .env.

Import the shared `config` singleton:

    from settings import config
    print(config.tsetmc_cdn_base_url)

Environment variables (case-insensitive; also read from <repo>/.env):
  TSETMC_CDN_BASE_URL     — base URL of the TSETMC CDN (default: http://cdn.tsetmc.com)
  PARSIAN_SIGNALR_URL     — Parsian broker SignalR hub WebSocket URL
  PASARGAD_SIGNALR_URL    — Pasargad broker SignalR hub WebSocket URL
  PASARGAD_API_BASE_URL   — Pasargad REST API base (e.g. https://pasargad-signal.tsetab.ir)
  PASARGAD_AUTH_TOKEN     — Pasargad bearer token (used in WS query + REST headers)
  PASARGAD_COOKIE         — Pasargad cookie value sent on REST subscribe calls
  NIBI_SIGNALR_URL        — Nibi broker SignalR hub WebSocket URL
  NIBI_API_BASE_URL       — Nibi REST API base (host of SubscribeInstrument)
  NIBI_AUTH_TOKEN         — Nibi bearer token (used in WS query + REST headers)
  NIBI_COOKIE             — Nibi cookie value sent on REST subscribe calls
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

import logging
import sys
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

    tsetmc_cdn_base_url: str = "http://cdn.tsetmc.com"

    parsian_signalr_url: str = "wss://signal.parsianbroker.com/SignalHub"
    pasargad_signalr_url: str = "wss://pasargad-signal.tsetab.ir/SignalHub"
    pasargad_api_base_url: str = "https://pasargad-signal.tsetab.ir"

    pasargad_auth_token: str = ""
    pasargad_cookie: str = ""

    nibi_hub_url: str = ""
    nibi_subscribe_url: str = ""
    nibi_auth_token: str = ""
    nibi_cookie: str = ""

    # Max ISINs that one SignalR hub connection can subscribe to via a
    # single `SubscribeInstrument` call. Each broker has its own server-
    # side cap on the list length; tune per-broker to maximize multiplex
    # density while staying under the limit.
    nibi_instruments_per_connection: int = 5
    pasargad_instruments_per_connection: int = 5

    data_dir: Path = Path("data")
    orderbooks_dir: Path = Path("data/orderbooks")
    trades_dir: Path = Path("data/trades")

    redis_uri: str = "localhost"
    redis_port: int = 6379

    instruments_file: Path = Path("data/instruments.yaml")

    @field_validator("tsetmc_cdn_base_url", "pasargad_api_base_url", "nibi_subscribe_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("data_dir", "orderbooks_dir", "trades_dir", "instruments_file")
    @classmethod
    def _resolve_path(cls, v: Path | str) -> Path:
        p = Path(v)
        return p if p.is_absolute() else _PROJECT_ROOT / p


config = Config()


def setup_logging(level: str | int = "INFO") -> None:
    """Configure the root logger once with a standard project-wide format.

    Idempotent — repeat calls are no-ops, so every script can call it at
    the top without worrying about double-configuration. Emits to stderr:

        2026-05-12 10:30:15 INFO    broker.nibi.streamer [IRTKMOFD0001+4] subscribe instruments: HTTP 200 for 5 isin(s)

    Override per-logger after this call via
    `logging.getLogger(name).setLevel(...)`.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.setLevel(level)
    root.addHandler(handler)


__all__ = ["Config", "config", "setup_logging"]
