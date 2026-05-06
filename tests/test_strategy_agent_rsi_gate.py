"""RVOL StrategyAgent uchun ixtiyoriy kunlik RSI zanjiri."""

import pytest

from agents.strategy_agent import StrategyAgent


def build_candles_flat_rsi_about_50(count: int = 35) -> list[dict]:
    """Minimal flat-ish series — RSI ~ neutral."""
    candles = []
    px = 100.0
    for idx in range(count):
        t = 1_700_400_000_000 + idx * 86_400_000
        candles.append({"t": t, "o": px, "h": px + 0.2, "l": px - 0.2, "c": px, "v": 500_000.0})
    return candles


@pytest.fixture
def base_signal() -> dict:
    return {
        "ticker": "TST",
        "price": 10.5,
        "volume": 500_000,
        "avg_volume": 250_000,
        "rvol": 3.0,
        "change_percent": 2.0,
        "candles": build_candles_flat_rsi_about_50(),
        "data_delay": "delayed",
        "updated_time": "now",
    }


def test_daily_rsi_gate_off_passes(monkeypatch: pytest.MonkeyPatch, base_signal: dict) -> None:
    monkeypatch.setenv("DAILY_RSI_GATE_ENABLED", "false")
    agent = StrategyAgent()
    result = agent.evaluate(base_signal)
    assert result["strategy_pass"] is True
    assert "daily_rsi" not in (result.get("failed_rules") or [])


def test_daily_rsi_gate_on_flat_market(monkeypatch: pytest.MonkeyPatch, base_signal: dict) -> None:
    monkeypatch.setenv("DAILY_RSI_GATE_ENABLED", "true")
    monkeypatch.setenv("DAILY_RSI_MIN", "55")
    monkeypatch.setenv("DAILY_RSI_MAX", "70")
    agent = StrategyAgent()
    result = agent.evaluate(base_signal)

    rsi = result.get("daily_rsi_14")
    assert rsi is not None
    if float(rsi) < 55.0:
        assert result["strategy_pass"] is False
        assert "daily_rsi" in result["failed_rules"]
