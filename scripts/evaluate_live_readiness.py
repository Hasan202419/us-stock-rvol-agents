#!/usr/bin/env python3
"""Paper -> live readiness gate evaluator (CSV based)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean


def _parse_float(raw: str) -> float:
    try:
        return float((raw or "").strip())
    except (TypeError, ValueError):
        return 0.0


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak
            worst = max(worst, drawdown)
    return worst


def evaluate(trades_csv: Path) -> tuple[bool, dict[str, float | int]]:
    if not trades_csv.exists():
        raise FileNotFoundError(f"Trades log topilmadi: {trades_csv}")

    pnls: list[float] = []
    equity_curve: list[float] = [10_000.0]
    with trades_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pnl = _parse_float(row.get("realized_pnl", "")) or _parse_float(row.get("pnl", ""))
            if pnl == 0.0:
                continue
            pnls.append(pnl)
            equity_curve.append(equity_curve[-1] + pnl)

    closed_trades = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = (len(wins) / closed_trades * 100.0) if closed_trades else 0.0
    gross_profit = sum(wins)
    gross_loss_abs = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else (999.0 if gross_profit > 0 else 0.0)
    max_dd_pct = _max_drawdown(equity_curve) * 100.0

    metrics: dict[str, float | int] = {
        "closed_trades": closed_trades,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "avg_pnl": round(mean(pnls), 3) if pnls else 0.0,
    }

    ready = (
        closed_trades >= 30
        and win_rate >= 55.0
        and profit_factor >= 1.5
        and max_dd_pct < 8.0
    )
    return ready, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate paper-trading readiness for live mode.")
    parser.add_argument(
        "--trades-csv",
        default="logs/trades.csv",
        help="Path to closed trades CSV (default: logs/trades.csv)",
    )
    args = parser.parse_args()
    ready, metrics = evaluate(Path(args.trades_csv))

    print("=== Live Readiness Gate ===")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print(f"ready_for_live: {ready}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
