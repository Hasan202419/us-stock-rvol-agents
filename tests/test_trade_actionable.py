"""trade_actionable — KIRISH / KUTING / SKIP."""

from __future__ import annotations

import os

import pytest

from agents.trade_actionable import (
    TradeAction,
    action_badge,
    classify_trade_action,
    filter_actionable_entries,
    partition_by_action,
)


def _row(**kw):
    base = {
        "ticker": "AAPL",
        "price": 100.0,
        "market_regime": "RISK_ON",
        "trade_levels_ok": True,
        "trade_rr_tp1": 2.5,
        "strategy_pass": True,
        "mtf_alignment_count": 3,
        "mtf_alignment_total": 3,
    }
    base.update(kw)
    return base


def test_enter_amt_buy():
    act, reason = classify_trade_action(_row(amt_buy_signal=True, trade_entry_note="VAL↑"))
    assert act == TradeAction.ENTER
    assert "AMT BUY" in reason
    assert action_badge(_row(amt_buy_signal=True, trade_levels_ok=True, trade_rr_tp1=2.0)) == "✅ KIRISH"


def test_wait_no_levels():
    act, _ = classify_trade_action(_row(trade_levels_ok=False))
    assert act == TradeAction.WAIT


def test_skip_risk_off():
    act, reason = classify_trade_action(_row(market_regime="RISK_OFF"))
    assert act == TradeAction.SKIP
    assert "RISK_OFF" in reason


def test_wait_low_rr_on_amt():
    act, reason = classify_trade_action(_row(amt_buy_signal=True, trade_rr_tp1=0.5))
    assert act == TradeAction.WAIT
    assert "R:R" in reason


def test_partition_and_filter():
    rows = [
        _row(ticker="A", amt_buy_signal=True),
        _row(ticker="B", trade_levels_ok=False),
        _row(ticker="C", market_regime="RISK_OFF"),
    ]
    enter, wait, skip = partition_by_action(rows)
    assert len(enter) == 1
    assert len(wait) >= 1
    assert len(skip) >= 1
    filtered = filter_actionable_entries(rows)
    assert filtered[0]["ticker"] == "A"


def test_require_mtf_when_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRADE_ACTIONABLE_REQUIRE_MTF_FULL", "true")
    act, reason = classify_trade_action(
        _row(amt_buy_signal=True, mtf_alignment_count=1, mtf_alignment_total=3)
    )
    assert act == TradeAction.WAIT
    assert "MTF" in reason
