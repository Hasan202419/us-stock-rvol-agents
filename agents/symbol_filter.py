"""US skan uchun ticker filtri — warrant/unit/preferred (.WS, .U, .PR…) chiqariladi."""

from __future__ import annotations

import re
from typing import Iterable, List

# BRK.B, BF.B kabi oddiy Class B
_CLASS_B_RE = re.compile(r"^[A-Z]{1,5}\.[A-Z]$")
_SYMBOL_CHARS_RE = re.compile(r"^[A-Z0-9.]+$")


def is_scannable_us_equity(symbol: str) -> bool:
    """Oddiy aksiya/ETF ticker (prop/trader2B skan uchun).

    Chiqariladi: BBBY.WS, BC.PRC, BCS.U, BEP.PRA va hokazo.
    Qoladi: AAPL, TSLA, BRK.B, SPY.
    """

    s = (symbol or "").strip().upper()
    if not s or len(s) > 12:
        return False
    if not _SYMBOL_CHARS_RE.match(s):
        return False
    if s.isdigit():
        return False
    if "." not in s:
        return True
    return bool(_CLASS_B_RE.match(s))


def filter_scannable_symbols(symbols: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if not is_scannable_us_equity(sym):
            continue
        seen.add(sym)
        out.append(sym)
    return out
