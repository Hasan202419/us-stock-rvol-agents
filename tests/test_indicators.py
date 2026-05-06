"""Unit tests focused on deterministic math utilities."""

from agents.indicators import cumulative_session_vwap, rsi


def build_bar(unix_seconds: float, typical_close: float, volume: float = 1000.0, spread: float = 0.2) -> dict:
    return {
        "t": int(unix_seconds * 1000),
        "o": typical_close - spread / 2,
        "h": typical_close + spread / 2,
        "l": typical_close - spread / 2,
        "c": typical_close,
        "v": volume,
    }


def test_cumulative_vwap_matches_manual_average() -> None:
    bars = [
        build_bar(1_700_000_000, 10.0),
        build_bar(1_700_000_300, 12.0),
        build_bar(1_700_000_600, 11.0),
    ]

    vwaps = cumulative_session_vwap(bars)

    assert vwaps[0] is not None
    assert abs(vwaps[0] - 10.0) < 1e-6
    assert vwaps[-1] is not None
    assert vwaps[-1] > vwaps[0]


def test_rsi_produces_valid_range_after_warmup() -> None:
    closes = [float(value) for value in range(1, 40)]
    series = rsi(closes, period=5)

    assert series[0] is None
    assert series[5] is not None
    assert 0 <= float(series[-1]) <= 100
