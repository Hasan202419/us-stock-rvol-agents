"""Finviz Elite CSV export (`requests` bilan).

Qo‘lda ssilka dizayni: `https://elite.finviz.com/export?{FILTER_QUERY}&auth=TOKEN`
Bu yerda TOKEN — `.env` dagi `FINVIZ_ELITE_AUTH`, FILTER_QUERY — `FINVIZ_ELITE_EXPORT_QUERY`.

Finviz sahifadan “Export” uchun `export`/`export.ashx` asosiy URL farq bo‘lsa,
`FINVIZ_ELITE_EXPORT_BASE` bilan o‘zgartirasiz (sukut: `https://elite.finviz.com/export`).
"""

from __future__ import annotations

import csv
import io
import os
import re
from typing import Callable

import requests


def _sanitize_query_segment(query: str) -> str:
    q = query.strip().lstrip("?").strip()
    parts: list[str] = []
    for seg in q.split("&"):
        seg_st = seg.strip()
        if not seg_st:
            continue
        if seg_st.lower().startswith("auth="):
            continue
        parts.append(seg_st)
    return "&".join(parts)


def build_export_url(
    *,
    auth: str,
    export_query: str,
    base: str | None = None,
) -> str:
    if not auth.strip():
        raise ValueError("FINVIZ_ELITE_AUTH bo‘sh")
    q = _sanitize_query_segment(export_query)
    if not q:
        raise ValueError("FINVIZ_ELITE_EXPORT_QUERY bo‘sh (Finviz eksport parametrlari kerak)")
    root = (base or os.getenv("FINVIZ_ELITE_EXPORT_BASE", "https://elite.finviz.com/export")).strip().rstrip("?/")
    sep = "&" if "?" in root else "?"
    return f"{root}{sep}{q}&auth={auth.strip()}"


def fetch_export_csv_bytes(
    *,
    auth: str | None = None,
    export_query: str | None = None,
    base: str | None = None,
    timeout_sec: float = 60.0,
    session: requests.Session | None = None,
) -> tuple[bytes, str]:
    """(content, resolved_url) — mahfiy kalit chiqarilmaydi."""

    au = (auth or os.getenv("FINVIZ_ELITE_AUTH", "")).strip()
    eq = (export_query or os.getenv("FINVIZ_ELITE_EXPORT_QUERY", "")).strip()
    url = build_export_url(auth=au, export_query=eq, base=base)
    getter: Callable[..., requests.Response] = (session or requests).get
    r = getter(
        url,
        timeout=timeout_sec,
        headers={"User-Agent": "us-stock-rvol-agents/1.0 (Finviz Elite CSV)"},
    )
    r.raise_for_status()
    return r.content, url


_TICKER_ALIASES = frozenset(
    {
        "ticker",
        "symbol",
        "symbols",
    }
)


def symbols_from_finviz_csv(
    content: bytes,
    *,
    limit: int = 400,
    encoding: str = "utf-8",
) -> list[str]:
    """CSV dan birinchi mos ustun bo‘yicha ticker ro‘yxati (No.,Ticker,...)."""

    text = content.decode(encoding, errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        return []

    fields_lower = [f.strip().lower() for f in reader.fieldnames if f]
    col: str | None = None
    for fn in reader.fieldnames:
        if fn and fn.strip().lower() in _TICKER_ALIASES:
            col = fn
            break
    if col is None:
        for raw, low in zip(reader.fieldnames, fields_lower):
            if raw and ("ticker" in low or low == "sym"):
                col = raw
                break

    symbols: list[str] = []
    seen: set[str] = set()
    if col:
        for row in reader:
            cell = row.get(col, "").strip().strip('"').strip("'")
            if not cell:
                continue
            sym = re.split(r"[,\s;]+", cell)[0].upper()
            sym = "".join(ch for ch in sym if ch.isalnum() or ch in {".", "-"})
            if len(sym) <= 12 and sym.isascii() and sym not in seen:
                seen.add(sym)
                symbols.append(sym)
                if len(symbols) >= limit:
                    break

    return symbols[:limit]
