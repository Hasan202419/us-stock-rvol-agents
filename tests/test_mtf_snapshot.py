"""MTF snapshot — strategiya pass + soxta market data."""

from __future__ import annotations

import pytest

from agents.mtf_snapshot import build_mtf_fields, maybe_attach_mtf_snapshot


def test_mtf_skipped_when_strategy_fails_and_pass_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTF_SNAPSHOT_ENABLED", "true")
    monkeypatch.setenv("MTF_SNAPSHOT_STRATEGY_PASS_ONLY", "true")
    monkeypatch.setenv("MTF_TIMEFRAMES", "5")

    class MD:
        def fetch_intraday_bars(self, *args: object, **kwargs: object) -> list:
            raise AssertionError("should not fetch when strategy_pass is false")

    out = build_mtf_fields(MD(), "AAPL", {"strategy_pass": False})
    assert out == {}


def test_mtf_attached_when_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTF_SNAPSHOT_ENABLED", "true")
    monkeypatch.setenv("MTF_SNAPSHOT_STRATEGY_PASS_ONLY", "true")
    monkeypatch.setenv("MTF_TIMEFRAMES", "5")

    bars = [
        {"t": 1_700_000_000_000 + i * 60_000, "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0 + i * 0.02, "v": 1000.0}
        for i in range(30)
    ]

    class MD:
        def fetch_intraday_bars(self, ticker: str, timeframe_minutes: int = 5, lookback_calendar_days=None):
            assert ticker == "AAA"
            return bars

    sig = maybe_attach_mtf_snapshot(MD(), "AAA", {"strategy_pass": True, "ticker": "AAA"})
    assert "mtf_summary_line" in sig
    assert "5m" in sig["mtf_summary_line"]
    assert sig.get("mtf_snapshot_by_tf")


def test_mtf_all_symbols_when_pass_only_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTF_SNAPSHOT_STRATEGY_PASS_ONLY", "false")
    monkeypatch.setenv("MTF_TIMEFRAMES", "5")
    called = 0

    class MD:
        def fetch_intraday_bars(self, *a, **k):
            nonlocal called
            called += 1
            return [{"t": 1, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 15

    out = build_mtf_fields(MD(), "X", {"strategy_pass": False})
    assert called == 1
    assert "mtf_summary_line" in out
