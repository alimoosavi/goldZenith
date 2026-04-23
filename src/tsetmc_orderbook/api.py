"""FastAPI service exposing per-second orderbook snapshots over HTTP."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .fetch import fetch_raw
from .snapshots import build_snapshots

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app = FastAPI(
    title="TSETMC Orderbook API",
    description="Reconstructed 5-depth orderbook snapshots for TSETMC instruments.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def load_ticker_snapshots(ticker_id: str, year: int, month: int, day: int) -> dict[str, Any]:
    """
    Fetch BestLimits history and reconstruct per-second 5-depth snapshots.
    Returns { ticker, date, count, snapshots } where date is Jalali YYYY-MM-DD.
    """
    date = f"{year:04d}-{month:02d}-{day:02d}"
    raw = fetch_raw(ticker_id, date)
    snapshots = build_snapshots(raw) if raw else []
    return {
        "ticker": ticker_id,
        "date": date,
        "count": len(snapshots),
        "snapshots": snapshots,
    }


@app.get("/api/orderbook/{ticker_id}")
def get_orderbook(ticker_id: str, year: int, month: int, day: int) -> dict[str, Any]:
    """
    Return the full per-second 5-depth orderbook timeline for one instrument
    on one trading day (Jalali calendar).

    Query params:
      year, month, day — Jalali date components (e.g. 1402, 3, 1).
    """
    try:
        return load_ticker_snapshots(ticker_id, year, month, day)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TSETMC fetch/build failed: {e}")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
