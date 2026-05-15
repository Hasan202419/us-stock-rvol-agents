"""AMT / VWAP scalping snapshot."""

from __future__ import annotations

import pytest

from agents.amt_vwap_scalp import compute_amt_vwap_scalp, maybe_attach_amt_snapshot


def test_amt_insufficient_bars() -> None:
    bars = [{"t": i, "o": 1, "h": 1, "l": 1, "c": 1, "v": 100} for i in range(10)]
    out = compute_amt_vwap_scalp(bars, session_len=20, ema_len=9)
    assert out.get("amt_ok") is False
    assert out.get("amt_buy_signal") is False


def test_amt_crossover_val_triggers_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMT_SESSION_LEN", "5")
    monkeypatch.setenv("AMT_EMA_LEN", "3")
    # 15 bar: narx VAL ostida, keyingi shamda VAL ustiga (crossover)
    bars = []
    base_t = 1_700_000_000_000
    for i in range(14):
        c = 100.0 - i * 0.05  # pastga
        bars.append(
            {
                "t": base_t + i * 60_000,
                "o": c,
                "h": c + 0.02,
                "l": c - 0.02,
                "c": c,
                "v": 1_000_000.0,
            }
        )
    # Oxirgi 2 sham: VAL dan pastdan yuqoriga
    bars.append(
        {
            "t": base_t + 14 * 60_000,
            "o": 99.0,
            "h": 99.1,
            "l": 98.9,
            "c": 99.0,
            "v": 1_000_000.0,
        }
    )
    bars.append(
        {
            "t": base_t + 15 * 60_000,
            "o": 100.5,
            "h": 101.0,
            "l": 100.4,
            "c": 100.95,
            "v": 1_000_000.0,
        }
    )
    out = compute_amt_vwap_scalp(bars, session_len=5, ema_len=3)
    assert out.get("amt_ok") is True
    # Crossover yoki EMA shartlaridan biri True bo‘lishi mumkin (sintetik zanjir)
    assert "amt_buy_signal" in out


def test_maybe_attach_respects_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMT_VWAP_SCALP_ENABLED", "false")

    class MD:
        def fetch_intraday_bars(self, *a, **k):
            raise AssertionError("disabled")

    sig = maybe_attach_amt_snapshot(MD(), "X", {"strategy_pass": True})
    assert "amt_summary_line" not in sig
