"""Regression: sma_crossover_long_only_backtest."""

from agents.simple_backtest_mvp import sma_crossover_long_only_backtest


def test_sma_crossover_insufficient_returns_error_dict() -> None:
    closes = [100.0] * 5
    result = sma_crossover_long_only_backtest(closes, fast=10, slow=30)
    assert result.get("ok") is False


def test_sma_crossover_deterministic_up_trend_more_long_than_flat() -> None:
    closes = list(range(1, 200))
    steep = sma_crossover_long_only_backtest(closes, fast=5, slow=15)
    flat = sma_crossover_long_only_backtest([100.0] * 200, fast=5, slow=15)
    assert steep.get("ok") is True
    assert flat.get("ok") is True
    assert (steep.get("bars_in_long") or 0) > (flat.get("bars_in_long") or 0)
