"""TSETMC BestLimits history fetching."""

import requests
import jdatetime

from settings import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/39.0.2171.95 Safari/537.36"
    )
}


def jalali_to_gregorian_int(jalali_date: str) -> int:
    y, m, d = jalali_date.split("-")
    g = jdatetime.date(int(y), int(m), int(d)).togregorian()
    return int(f"{g.year:04}{g.month:02}{g.day:02}")


def fetch_raw(ticker_no: str, jalali_date: str) -> list:
    deven = jalali_to_gregorian_int(jalali_date)
    url = config.best_limits_url.format(ticker=ticker_no, deven=deven)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("bestLimitsHistory", [])
