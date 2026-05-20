"""telegram_paper_trade: signal tanlash va order parametrlari."""

from __future__ import annotations

from agents.telegram_paper_trade import (
    analyst_view_from_signal,
    default_stop_take_profit,
    pick_paper_signal,
)


def test_pick_paper_signal_prefers_highest_score() -> None:
    rows = [
        {"ticker": "AAA", "paper_trade_ready": True, "score": 10},
        {"ticker": "BBB", "paper_trade_ready": True, "score": 50},
        {"ticker": "CCC", "paper_trade_ready": False, "score": 99},
    ]
    got = pick_paper_signal(rows)
    assert got is not None
    assert got["ticker"] == "BBB"


def test_pick_paper_signal_by_ticker() -> None:
    rows = [
        {"ticker": "AAA", "paper_trade_ready": True, "score": 10},
        {"ticker": "BBB", "paper_trade_ready": True, "score": 50},
    ]
    got = pick_paper_signal(rows, ticker="aaa")
    assert got is not None
    assert got["ticker"] == "AAA"


def test_default_stop_take_profit_from_signal() -> None:
    stop, tp = default_stop_take_profit({"price": 100.0, "stop_suggestion": 95.0, "take_profit_suggestion": 110.0})
    assert stop == 95.0
    assert tp == 110.0


def test_analyst_view_from_signal_maps_allow_order() -> None:
    view = analyst_view_from_signal(
        {
            "chatgpt_decision": "WATCH",
            "chatgpt_allow_order": True,
            "chatgpt_risk_flags_hard_json": "[]",
        }
    )
    assert view["allow_order"] is True
    assert view["decision"] == "WATCH"
