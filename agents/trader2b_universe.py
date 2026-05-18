"""trader2B (Toro) savdo ro‘yxati — qisqa muddat skan uchun universe."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from agents.symbol_filter import filter_scannable_symbols, is_scannable_us_equity

# Foydalanuvchi talab qilgan va tez-tez skan qilinadigan taniqli tickerlar (doim ro‘yxatda).
CORE_LIQUID_SYMBOLS: tuple[str, ...] = (
    "AAPL",
    "TSLA",
    "PLTR",
    "ORCL",
    "NVDA",
    "AMD",
    "META",
    "AMZN",
    "MSFT",
    "GOOGL",
    "NFLX",
    "SMCI",
    "COIN",
    "HOOD",
    "SOFI",
    "MU",
    "AVGO",
    "QCOM",
    "INTC",
    "UBER",
)

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "trader2b_toro250.txt"


def _parse_symbol_line(line: str) -> str | None:
    raw = line.strip().upper()
    if not raw or raw.startswith("#"):
        return None
    sym = raw.split(",", maxsplit=1)[0].strip()
    if sym and _SYMBOL_RE.match(sym):
        return sym
    return None


def load_trader2b_symbols_file(path: Path | None = None) -> List[str]:
    fp = path or Path(os.getenv("TRADER2B_SYMBOLS_FILE", str(_DEFAULT_FILE)).strip() or str(_DEFAULT_FILE))
    if not fp.is_file():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
        sym = _parse_symbol_line(line)
        if sym and is_scannable_us_equity(sym) and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _extra_from_env() -> List[str]:
    raw = os.getenv("TRADER2B_EXTRA_SYMBOLS", "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\s,;]+", raw):
        sym = _parse_symbol_line(chunk)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def build_trader2b_universe(*, limit: int = 0) -> List[str]:
    """Toro ro‘yxati + core tickerlar + TRADER2B_EXTRA_SYMBOLS."""

    seen: set[str] = set()
    ordered: list[str] = []

    def add_many(symbols: List[str]) -> None:
        for s in symbols:
            if s not in seen:
                seen.add(s)
                ordered.append(s)

    add_many(list(CORE_LIQUID_SYMBOLS))
    add_many(_extra_from_env())
    add_many(load_trader2b_symbols_file())

    filtered = filter_scannable_symbols(ordered)
    if limit > 0:
        return filtered[:limit]
    return filtered


def trader2b_universe_size() -> int:
    return len(build_trader2b_universe(limit=0))
