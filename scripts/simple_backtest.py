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

from agents.backtest_engine import replay_strategy, summarize  # noqa: E402
from agents.ibkr_market_data import fetch_ibkr_daily_candles, ibkr_enabled  # noqa: E402
from agents.simple_backtest_mvp import (  # noqa: E402
    daily_candles_yfinance,
    daily_closes_yfinance,
    sma_crossover_long_only_backtest,
)


def _load_candles(symbol: str, days: int) -> list:
    """IBKR yoqilgan bo‘lsa undan, aks holda yfinance’dan kunlik OHLCV."""

    if ibkr_enabled():
        candles = fetch_ibkr_daily_candles(symbol, days=days)
        if candles:
            return candles
    return daily_candles_yfinance(symbol, days)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest (SMA MVP yoki jonli strategiya: rvol/ignition).")
    parser.add_argument("symbol", nargs="?", default="SPY", help="Ticker, masalan SPY")
    parser.add_argument("--days", type=int, default=400, help="Tarix chuqurligi (~kun)")
    parser.add_argument(
        "--strategy",
        choices=["sma", "rvol", "volume_ignition"],
        default="sma",
        help="sma=eski MVP; rvol/volume_ignition=jonli strategiya backtesti",
    )
    parser.add_argument("--horizon", type=int, default=10, help="Kirishdan keyin necha bar kuzatiladi")
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    ns = parser.parse_args()
    symbol = ns.symbol.upper()

    if ns.strategy == "sma":
        closes = daily_closes_yfinance(symbol, ns.days)
        if not closes:
            raise SystemExit("Tarix chiqmadi — tarmoq yoki simvolni tekshiring; yfinance o‘rnating.")
        result = sma_crossover_long_only_backtest(closes, fast=ns.fast, slow=ns.slow)
        payload = {"symbol": symbol, "strategy": "sma", "closes": len(closes), **result}
        print(json.dumps(payload, indent=2))
        return 0 if result.get("ok") else 1

    candles = _load_candles(symbol, ns.days)
    if not candles:
        raise SystemExit("Tarix chiqmadi — IBKR Gateway yoki yfinance’ni tekshiring.")
    trades = replay_strategy(candles, ns.strategy, horizon=ns.horizon, ticker=symbol)
    summary = summarize(trades)
    payload = {"symbol": symbol, "strategy": ns.strategy, "bars": len(candles), "horizon": ns.horizon, **summary}
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
