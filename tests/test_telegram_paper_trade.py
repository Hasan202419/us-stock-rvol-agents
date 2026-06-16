"""telegram_paper_trade: signal tanlash va order parametrlari."""

from __future__ import annotations

from pathlib import Path

import agents.telegram_paper_trade as paper_mod
from agents.telegram_paper_trade import (
    analyst_view_from_signal,
    default_stop_take_profit,
    execute_paper_trade,
    format_paper_result_html,
    pick_paper_signal,
)


class _FakeRisk:
    def __init__(self, approve: bool = True) -> None:
        self._approve = approve

    def suggest_quantity(self, signal: dict) -> tuple[int, str]:
        return 10, "fake sizing"

    def approve_order(self, signal: dict, view: dict, order: dict) -> tuple[bool, str]:
        return self._approve, "ok" if self._approve else "risk blok"


class _FakeTrader:
    def __init__(self) -> None:
        self.submitted = False

    def submit_order(self, *args, **kwargs) -> dict:
        self.submitted = True
        return {"submitted": True, "status": "accepted", "order_id": "X1"}

    def fetch_order(self, order_id: str) -> dict:
        return {}


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


class _FakeLogger:
    def save_trade(self, row: dict) -> None:
        return None


def _patch_agents(monkeypatch, risk: _FakeRisk, trader: _FakeTrader) -> None:
    monkeypatch.setattr(
        paper_mod,
        "build_scan_agents",
        lambda repo_root: {"risk": risk, "trader": trader, "logger": _FakeLogger()},
    )


def test_dry_run_does_not_submit_order(monkeypatch) -> None:
    trader = _FakeTrader()
    _patch_agents(monkeypatch, _FakeRisk(approve=True), trader)
    signal = {
        "ticker": "nvda",
        "price": 100.0,
        "stop_suggestion": 95.0,
        "take_profit_suggestion": 110.0,
        "paper_trade_ready": True,
    }
    result = execute_paper_trade(signal, repo_root=Path("."), dry_run=True)

    assert trader.submitted is False
    assert result["status"] == "DRY_RUN"
    assert result["submitted"] is False
    assert result["dry_run"] is True
    assert result["ticker"] == "NVDA"
    # R:R = (110-100)/(100-95) = 2.0; risk = 5*10 = 50 USD
    assert result["rr_ratio"] == 2.0
    assert result["est_risk_usd"] == 50.0
    assert result["notional"] == 1000.0


def test_dry_run_blocked_when_risk_rejects(monkeypatch) -> None:
    trader = _FakeTrader()
    _patch_agents(monkeypatch, _FakeRisk(approve=False), trader)
    signal = {"ticker": "AAA", "price": 50.0, "paper_trade_ready": True}
    result = execute_paper_trade(signal, repo_root=Path("."), dry_run=True)

    assert trader.submitted is False
    assert result["status"] == "BLOCKED"


def test_live_run_submits_order(monkeypatch) -> None:
    trader = _FakeTrader()
    _patch_agents(monkeypatch, _FakeRisk(approve=True), trader)
    signal = {
        "ticker": "TSLA",
        "price": 200.0,
        "stop_suggestion": 190.0,
        "take_profit_suggestion": 230.0,
        "paper_trade_ready": True,
    }
    result = execute_paper_trade(signal, repo_root=Path("."), dry_run=False)

    assert trader.submitted is True
    assert result.get("submitted") is True


def test_format_dry_run_html_marks_preview() -> None:
    html = format_paper_result_html(
        {
            "ticker": "NVDA",
            "status": "DRY_RUN",
            "submitted": False,
            "dry_run": True,
            "quantity": 10,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "notional": 1000.0,
            "est_risk_usd": 50.0,
            "est_reward_usd": 100.0,
            "rr_ratio": 2.0,
        }
    )
    assert "dry-run" in html.lower()
    assert "R:R" in html
