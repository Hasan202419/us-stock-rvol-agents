#!/usr/bin/env python3
"""Minimal kunlik SMA backtest MVP (yahoo orqanda yfinance)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("PROJECT_ROOT", str(PROJECT_DIR))

from agents.simple_backtest_mvp import (  # noqa: E402
    daily_closes_yfinance,
    sma_crossover_long_only_backtest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="SMA crossover backtest MVP (yahoo daily).")
    parser.add_argument("symbol", nargs="?", default="SPY", help="Ticker, masalan SPY")
    parser.add_argument("--days", type=int, default=400, help="Yahoo tarix chuqurligi (~kun)")
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    ns = parser.parse_args()

    closes = daily_closes_yfinance(ns.symbol.upper(), ns.days)
    if not closes:
        raise SystemExit("Tarix chiqmadi — tarmoq yoki simvolni tekshiring; yfinance o‘rnating.")
    result = sma_crossover_long_only_backtest(closes, fast=ns.fast, slow=ns.slow)
    payload = {"symbol": ns.symbol.upper(), "closes": len(closes), **result}
    print(json.dumps(payload, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
