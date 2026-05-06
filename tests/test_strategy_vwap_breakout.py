"""Smoke tests for session filters and the VWAP breakout strategy."""

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.session_calendar import (
    bar_end_in_regular_session,
    bar_end_in_trade_window,
    bar_start_in_trade_window,
)
from agents.strategy_vwap_breakout import VwapBreakoutStrategyAgent


def ny_timestamp_ms(year: int, month: int, day: int, hour: int, minute: int) -> int:
    eastern = ZoneInfo("America/New_York")
    stamp = datetime(year, month, day, hour, minute, tzinfo=eastern)
    return int(stamp.timestamp() * 1000)


def test_pine_trade_window_bar_open_aligned() -> None:
    eligible_open = ny_timestamp_ms(2024, 1, 9, 9, 33)
    assert bar_start_in_trade_window(eligible_open, open_plus_minutes=3, close_minus_minutes=27) is True

    early_open = ny_timestamp_ms(2024, 1, 9, 9, 29)
    assert bar_start_in_trade_window(early_open, open_plus_minutes=3, close_minus_minutes=27) is False

def test_trade_window_respects_open_buffer() -> None:
    first_eligible = ny_timestamp_ms(2024, 1, 9, 9, 33)  # Tuesday, first 3m after the open for a 1m bar
    assert bar_end_in_regular_session(first_eligible, timeframe_minutes=1) is True
    assert bar_end_in_trade_window(first_eligible, timeframe_minutes=1, open_plus_minutes=3, close_minus_minutes=27) is True

    too_early = ny_timestamp_ms(2024, 1, 9, 9, 29)
    assert bar_end_in_trade_window(too_early, timeframe_minutes=1, open_plus_minutes=3, close_minus_minutes=27) is False


def test_vwap_strategy_requires_intraday_bars(monkeypatch) -> None:
    monkeypatch.setenv("MIN_PRICE", "1")
    monkeypatch.setenv("INTRADAY_TIMEFRAME_MINUTES", "5")

    agent = VwapBreakoutStrategyAgent()
    payload = {
        "ticker": "TEST",
        "price": 10.0,
        "change_percent": 1.0,
        "volume": 1_000_000,
        "avg_volume": 500_000,
        "rvol": 2.5,
        "data_delay": "15-minute delayed",
        "updated_time": "now",
    }

    result = agent.evaluate(payload, [])

    assert result["strategy_pass"] is False
    assert "intraday_bars" in result["failed_rules"]


def test_vwap_strategy_detects_crossover(monkeypatch) -> None:
    monkeypatch.setenv("MIN_PRICE", "1")
    monkeypatch.setenv("INTRADAY_TIMEFRAME_MINUTES", "5")
    monkeypatch.setenv("SESSION_OPEN_PLUS_MINUTES", "0")

    anchor = ny_timestamp_ms(2024, 1, 9, 9, 30)
    spacing = 5 * 60 * 1000
    bars = [
        {"t": anchor + 0 * spacing, "o": 100.0, "h": 100.0, "l": 90.0, "c": 92.0, "v": 1_000_000.0},
        {"t": anchor + 1 * spacing, "o": 92.0, "h": 110.0, "l": 92.0, "c": 105.0, "v": 3_000_000.0},
    ]

    agent = VwapBreakoutStrategyAgent()
    payload = {
        "ticker": "TEST",
        "price": float(bars[-1]["c"]),
        "change_percent": 1.0,
        "volume": 4_000_000,
        "avg_volume": 750_000,
        "rvol": 3.5,
        "data_delay": "15-minute delayed",
        "updated_time": "now",
    }

    result = agent.evaluate(payload, bars)

    assert result["strategy_pass"] is True
    assert "vwap_crossover" not in result["failed_rules"]
    bars_out = result.get("chart_session_bars") or []
    assert len(bars_out) == 2
    assert result["mtrade_chart_markers"]
    assert result["mtrade_chart_markers"][0]["event"] == "BUY"
