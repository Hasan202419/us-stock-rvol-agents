"""TA helpers for deterministic strategy rules (pure Python floats).

Keeps PineScript-era logic easy to unit test without heavyweight charting libs.
"""

from __future__ import annotations

from typing import Any, Dict, List


def typical_prices_from_bars(bars: List[Dict[str, Any]]) -> List[float]:
    highs = [float(b.get("h") or 0) for b in bars]
    lows = [float(b.get("l") or 0) for b in bars]
    closes = [float(b.get("c") or 0) for b in bars]
    return [(highs[idx] + lows[idx] + closes[idx]) / 3.0 for idx in range(len(bars))]


def cumulative_session_vwap(bars: List[Dict[str, Any]]) -> List[float | None]:
    """Session cumulative VWAP (sum(tp * volume) / sum(volume)), bar-aligned."""

    if not bars:
        return []

    cumulative_volume = 0.0
    cumulative_pv = 0.0
    vwaps: List[float | None] = []

    for bar in bars:
        typical_price = (float(bar.get("h") or 0) + float(bar.get("l") or 0) + float(bar.get("c") or 0)) / 3.0
        volume = float(bar.get("v") or 0)

        cumulative_volume += volume
        cumulative_pv += typical_price * volume

        vwaps.append(None if cumulative_volume <= 0 else cumulative_pv / cumulative_volume)

    return vwaps


def ema(series: List[float], period: int) -> List[float | None]:
    """Exponential moving average (seeded with a simple SMA on the warmup window)."""

    if period <= 0:
        raise ValueError("EMA period must be positive.")

    outputs: List[float | None] = [None] * len(series)

    if len(series) < period:
        return outputs

    smoothing = 2.0 / (period + 1.0)

    exponential_average = sum(series[:period]) / period
    outputs[period - 1] = exponential_average

    for idx in range(period, len(series)):
        exponential_average = series[idx] * smoothing + exponential_average * (1.0 - smoothing)
        outputs[idx] = exponential_average

    return outputs


def rsi(closes: List[float], period: int = 14) -> List[float | None]:
    """Wilder's RSI with warmup padding expressed as trailing None entries."""

    size = len(closes)
    results: List[float | None] = [None] * size

    if size < period + 1:
        return results

    gains: List[float] = []
    losses: List[float] = []

    for index in range(1, size):
        difference = closes[index] - closes[index - 1]
        gains.append(max(difference, 0.0))
        losses.append(max(-difference, 0.0))

    def rsi_from_average(avg_gain: float, avg_loss: float) -> float:
        if avg_gain == 0 and avg_loss == 0:
            return 50.0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    cursor_index = period
    results[cursor_index] = rsi_from_average(average_gain, average_loss)

    for delta_index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[delta_index]) / period
        average_loss = (average_loss * (period - 1) + losses[delta_index]) / period
        cursor_index = delta_index + 1
        results[cursor_index] = rsi_from_average(average_gain, average_loss)

    return results


def atr(bars: List[Dict[str, Any]], period: int = 14) -> List[float | None]:
    """Wilder-style ATR on highs/lows/closes."""

    size = len(bars)
    results: List[float | None] = [None] * size

    if size < period + 1:
        return results

    highs = [float(b.get("h") or 0) for b in bars]
    lows = [float(b.get("l") or 0) for b in bars]
    closes = [float(b.get("c") or 0) for b in bars]

    true_ranges: List[float] = [0.0] * size

    true_ranges[0] = highs[0] - lows[0]
    for index in range(1, size):
        high_low = highs[index] - lows[index]
        high_prev_close = abs(highs[index] - closes[index - 1])
        low_prev_close = abs(lows[index] - closes[index - 1])
        true_ranges[index] = max(high_low, high_prev_close, low_prev_close)

    average_true_range = sum(true_ranges[1 : period + 1]) / period
    cursor = period
    results[cursor] = average_true_range

    for index in range(period + 1, size):
        average_true_range = (average_true_range * (period - 1) + true_ranges[index]) / period
        cursor += 1
        results[cursor] = average_true_range

    return results


def candles_to_sorted_bars(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Polygon/Yahoo/usmon: `t` ms, OHLC kalitlari `o,h,l,c` yoki Polygon `vw`."""

    if not candles:
        return []

    def row_ts(row: Dict[str, Any]) -> int:
        return int(row.get("t") or 0)

    rows = sorted(candles, key=row_ts)
    out: List[Dict[str, Any]] = []
    for raw in rows:
        o = float(raw.get("o") or raw.get("open") or 0)
        h = float(raw.get("h") or raw.get("high") or 0)
        l = float(raw.get("l") or raw.get("low") or 0)
        c = float(raw.get("c") or raw.get("close") or 0)
        v = float(raw.get("v") or raw.get("volume") or 0)
        out.append({"t": row_ts(raw), "o": o, "h": h, "l": l, "c": c, "v": v})

    return out


def snapshot_from_daily_candles(
    candles: List[Dict[str, Any]],
    *,
    rsi_period: int = 14,
    ema_fast: int = 9,
    ema_slow: int = 20,
    atr_period: int = 14,
) -> Dict[str, Any]:
    """Kunlik shamlardan oxirgi EMA / RSI / ATR ni qaytaradi (MASTER_PLAN uchun)."""

    bars = candles_to_sorted_bars(candles)
    if not bars:
        return {
            "bar_timestamp_ms": None,
            "closes_series_len": 0,
            "ema_9": None,
            "ema_20": None,
            "rsi_14": None,
            "atr_14": None,
        }

    closes = [float(b.get("c") or 0) for b in bars]
    rsi_s = rsi(closes, period=rsi_period)
    ema_fast_s = ema(closes, ema_fast)
    ema_slow_s = ema(closes, ema_slow)
    atr_s = atr(bars, period=atr_period)

    last_i = len(bars) - 1

    return {
        "bar_timestamp_ms": int(bars[last_i]["t"]),
        "closes_series_len": len(closes),
        "ema_9": None if ema_fast_s[last_i] is None else round(float(ema_fast_s[last_i]), 4),
        "ema_20": None if ema_slow_s[last_i] is None else round(float(ema_slow_s[last_i]), 4),
        "rsi_14": None if rsi_s[last_i] is None else round(float(rsi_s[last_i]), 2),
        "atr_14": None if atr_s[last_i] is None else round(float(atr_s[last_i]), 4),
    }
