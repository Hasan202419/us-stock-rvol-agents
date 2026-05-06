"""Alpha Vantage kunlik tarix (ixtiyoriy; bepul rejada so‘rov cheklovi kichik).

https://www.alphavantage.co/documentation/
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

import requests

AV_URL = "https://www.alphavantage.co/query"


def fetch_daily_adjusted(
    symbol: str,
    api_key: str,
    *,
    outputsize: str = "compact",
    timeout: int = 20,
) -> List[Dict[str, Any]]:
    """TIME_SERIES_DAILY_ADJUSTED — `t` Unix ms, `o,h,l,c,v` (`indicators.candles_to_sorted_bars` bilan mos).

    `outputsize`: ``compact`` (~100 ta oxirgi kun) yoki ``full``.
    """

    key = (api_key or "").strip()
    if not key:
        return []

    try:
        response = requests.get(
            AV_URL,
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol.upper(),
                "outputsize": outputsize,
                "apikey": key,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    if payload.get("Note") or payload.get("Information"):
        # Rate limit / premium eslatmasi
        return []

    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict):
        return []

    rows: List[Dict[str, Any]] = []
    for day, parts in series.items():
        if not isinstance(parts, dict):
            continue
        try:
            day_dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        t_ms = int(day_dt.timestamp() * 1000)
        o = float(parts.get("1. open") or 0)
        h = float(parts.get("2. high") or 0)
        low_px = float(parts.get("3. low") or 0)
        c = float(parts.get("4. close") or 0)
        v = float(parts.get("6. volume") or 0)
        rows.append({"t": t_ms, "o": o, "h": h, "l": low_px, "c": c, "v": v})

    rows.sort(key=lambda r: int(r["t"]), reverse=True)
    return rows
