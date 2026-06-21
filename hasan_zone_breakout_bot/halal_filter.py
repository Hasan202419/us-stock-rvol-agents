"""halal_filter.py — manual halal watchlist (CSV) asosida HALAL_STATUS.

halal_watchlist.csv format: `ticker,status` (status: COMPLIANT / NOT_COMPLIANT).
Ro'yxatda bo'lmasa -> UNKNOWN (va "Halal status not verified" ogohlantirishi).
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict

from . import config

_CACHE: Dict[str, str] = {}
_LOADED_FROM: str = ""


def _csv_path() -> str:
    p = config.HALAL_WATCHLIST_CSV
    if os.path.isabs(p):
        return p
    return str(Path(__file__).resolve().parent / p)


def load_halal_watchlist(force: bool = False) -> Dict[str, str]:
    """halal_watchlist.csv ni o'qiydi (keshlaydi). {TICKER: STATUS}."""
    global _LOADED_FROM
    path = _csv_path()
    if _CACHE and not force and _LOADED_FROM == path:
        return _CACHE
    _CACHE.clear()
    _LOADED_FROM = path
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                ticker = row[0].strip().upper()
                status = row[1].strip().upper()
                if ticker in {"TICKER", ""} or not status:
                    continue
                if status in {"COMPLIANT", "NOT_COMPLIANT"}:
                    _CACHE[ticker] = status
    except FileNotFoundError:
        pass
    return _CACHE


def halal_status(ticker: str) -> str:
    """COMPLIANT / NOT_COMPLIANT / UNKNOWN."""
    wl = load_halal_watchlist()
    return wl.get((ticker or "").strip().upper(), "UNKNOWN")


def halal_warning(status: str) -> str:
    """UNKNOWN bo'lsa ogohlantirish matni."""
    if status == "UNKNOWN":
        return "Halal status not verified."
    if status == "NOT_COMPLIANT":
        return "Halal: NOT_COMPLIANT — ehtiyot bo'ling."
    return ""
