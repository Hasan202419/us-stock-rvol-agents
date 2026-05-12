from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agents.risk_manager_agent import RiskManagerAgent


def _base_signal() -> dict:
    return {
        "price": 100.0,
        "stop_suggestion": 95.0,
        "take_profit_suggestion": 112.0,
    }


def _base_analyst() -> dict:
    return {
        "allow_order": True,
        "decision": "WATCH",
        "reason": "ok",
        "risk_flags_hard": [],
        "paper_ready_blocked": None,
    }


def _base_order() -> dict:
    return {"quantity": 5, "stop_loss": 95.0, "take_profit": 112.0}


def test_reject_when_rr_too_low(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_EQUITY_USD", "10000")
    monkeypatch.setenv("MIN_RISK_REWARD_RATIO", "2.0")
    rm = RiskManagerAgent(trades_log_path=str(tmp_path / "trades.csv"), repo_root=tmp_path)

    sig = _base_signal()
    order = _base_order()
    order["take_profit"] = 104.0  # reward=4, risk=5 => 0.8R
    ok, reason = rm.approve_order(sig, _base_analyst(), order)
    assert ok is False
    assert "Risk:reward too low" in reason


def test_reject_when_max_trades_per_day_reached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_EQUITY_USD", "10000")
    monkeypatch.setenv("MAX_TRADES_PER_DAY", "2")
    monkeypatch.setenv("MAX_POSITION_SIZE_USD", "100000")
    trades_csv = tmp_path / "trades.csv"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    trades_csv.write_text(
        "submitted_at,realized_pnl\n"
        f"{today}T09:35:00Z,10\n"
        f"{today}T10:20:00Z,-5\n",
        encoding="utf-8",
    )
    rm = RiskManagerAgent(trades_log_path=str(trades_csv), repo_root=tmp_path)

    ok, reason = rm.approve_order(_base_signal(), _base_analyst(), _base_order())
    assert ok is False
    assert reason == "Maximum trades per day reached."


def test_reject_when_daily_loss_limit_hit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_EQUITY_USD", "10000")
    monkeypatch.setenv("MAX_TRADES_PER_DAY", "10")
    monkeypatch.setenv("MAX_DAILY_LOSS_USD", "50")
    monkeypatch.setenv("MAX_POSITION_SIZE_USD", "100000")
    trades_csv = tmp_path / "trades.csv"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    trades_csv.write_text(
        "submitted_at,realized_pnl\n"
        f"{today}T09:35:00Z,-30\n"
        f"{today}T10:20:00Z,-25\n",
        encoding="utf-8",
    )
    rm = RiskManagerAgent(trades_log_path=str(trades_csv), repo_root=tmp_path)

    ok, reason = rm.approve_order(_base_signal(), _base_analyst(), _base_order())
    assert ok is False
    assert reason == "Maximum daily loss reached."


def test_reject_when_quantity_exceeds_risk_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_EQUITY_USD", "10000")
    monkeypatch.setenv("MAX_RISK_PCT_OF_EQUITY", "1.0")
    rm = RiskManagerAgent(trades_log_path=str(tmp_path / "trades.csv"), repo_root=tmp_path)
    order = _base_order()
    order["quantity"] = 25  # risk/share=5, risk amount=100 => max qty 20

    ok, reason = rm.approve_order(_base_signal(), _base_analyst(), order)
    assert ok is False
    assert "exceeds risk budget qty" in reason

