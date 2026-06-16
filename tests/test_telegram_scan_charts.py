"""telegram_command_bot: skan grafiklarini biriktirish selektori."""

from __future__ import annotations

from typing import Any, Dict, List

import scripts.telegram_command_bot as bot


def _candles(n: int = 5) -> List[Dict[str, Any]]:
    return [{"t": i, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for i in range(n)]


def test_top_n_zero_returns_empty() -> None:
    rows = [{"ticker": "A", "strategy_pass": True, "score": 9, "candles": _candles()}]
    assert bot._chartable_top_signals(rows, 0) == []


def test_selects_pass_rows_with_candles_by_score() -> None:
    rows = [
        {"ticker": "A", "strategy_pass": True, "score": 10, "candles": _candles()},
        {"ticker": "B", "strategy_pass": True, "score": 80, "candles": _candles()},
        {"ticker": "C", "strategy_pass": True, "score": 99, "candles": []},          # candles yo'q
        {"ticker": "D", "watchlist_only": True, "score": 95, "candles": _candles()},  # kuzatuv
        {"ticker": "E", "strategy_pass": False, "score": 90, "candles": _candles()},  # pass emas
    ]
    got = bot._chartable_top_signals(rows, 3)
    assert [r["ticker"] for r in got] == ["B", "A"]  # C/D/E chiqib ketadi, skor bo'yicha


def test_paper_ready_counts_as_chartable() -> None:
    rows = [{"ticker": "P", "paper_trade_ready": True, "score": 50, "candles": _candles()}]
    got = bot._chartable_top_signals(rows, 5)
    assert [r["ticker"] for r in got] == ["P"]


def test_respects_top_n_cap() -> None:
    rows = [
        {"ticker": t, "strategy_pass": True, "score": s, "candles": _candles()}
        for t, s in [("A", 10), ("B", 20), ("C", 30)]
    ]
    got = bot._chartable_top_signals(rows, 2)
    assert [r["ticker"] for r in got] == ["C", "B"]
