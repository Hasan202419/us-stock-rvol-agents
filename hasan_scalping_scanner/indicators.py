"""indicators.py — sof matematik funksiyalar (tarmoqsiz, testlanadigan).

Bu yerda HECH qanday tarmoq/order yo'q. Faqat narx/hajm ustida hisob-kitob:
VWAP, EMA, RVOL, dollar volume, spread, volume spike ratio va h.k.

Sham (candle) formati: dict {"t","o","h","l","c","v"} — Unix ms + OHLCV.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _f(value: Any, default: float = 0.0) -> float:
    """Xavfsiz float — None/NaN/xato bo'lsa default."""
    try:
        if value is None:
            return default
        v = float(value)
        return default if v != v else v  # NaN tekshiruvi
    except (TypeError, ValueError):
        return default


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Eksponensial o'rtacha (EMA). Har bar uchun qiymat (yetarli bar bo'lmasa None)."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    # Boshlang'ich SMA
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    prev = sma
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def session_vwap(candles: List[Dict[str, Any]]) -> List[Optional[float]]:
    """Sessiya VWAP — har bar uchun kumulyativ (typical_price × hajm) / kumulyativ hajm."""
    out: List[Optional[float]] = []
    cum_pv = 0.0
    cum_v = 0.0
    for c in candles:
        h, low, close, v = _f(c.get("h")), _f(c.get("l")), _f(c.get("c")), _f(c.get("v"))
        typical = (h + low + close) / 3.0 if (h or low or close) else close
        cum_pv += typical * v
        cum_v += v
        out.append(round(cum_pv / cum_v, 6) if cum_v > 0 else None)
    return out


def rvol(current_volume: float, avg_volume: float) -> float:
    """RVOL = joriy hajm / o'rtacha hajm."""
    cur, avg = _f(current_volume), _f(avg_volume)
    return round(cur / avg, 2) if avg > 0 else 0.0


def dollar_volume(price: float, volume: float) -> float:
    """Dollar volume = narx × hajm."""
    return round(_f(price) * _f(volume), 2)


def spread_pct(bid: Optional[float], ask: Optional[float], last: float) -> Optional[float]:
    """Spread % = (ask - bid) / last × 100. Bid/ask yo'q bo'lsa None (UNKNOWN)."""
    b, a, lp = _f(bid, -1), _f(ask, -1), _f(last)
    if b <= 0 or a <= 0 or lp <= 0 or a < b:
        return None
    return round((a - b) / lp * 100.0, 3)


def pct_change(price: float, prev_close: Optional[float]) -> Optional[float]:
    """% o'zgarish oldingi yopilishdan."""
    p, pc = _f(price), _f(prev_close, -1)
    if pc <= 0:
        return None
    return round((p - pc) / pc * 100.0, 2)


def volume_spike_ratio(candles_5m: List[Dict[str, Any]], lookback: int = 20) -> Optional[float]:
    """5-min hajm portlashi = oxirgi 5-min sham hajmi / oldingi `lookback` shamning o'rtachasi."""
    if len(candles_5m) < 2:
        return None
    last_vol = _f(candles_5m[-1].get("v"))
    window = candles_5m[-(lookback + 1):-1]
    if not window:
        return None
    vols = [_f(c.get("v")) for c in window]
    avg = sum(vols) / len(vols) if vols else 0.0
    if avg <= 0:
        return None
    return round(last_vol / avg, 2)


def classify_volume_spike(ratio: Optional[float]) -> str:
    """Koeffitsiyentni nomga aylantirish: normal / strong / ignition / unknown."""
    if ratio is None:
        return "UNKNOWN"
    if ratio >= 3.0:
        return "IGNITION"
    if ratio >= 1.5:
        return "STRONG"
    if ratio >= 1.0:
        return "NORMAL"
    return "WEAK"


def vwap_extension_pct(price: float, vwap: Optional[float]) -> Optional[float]:
    """Narx VWAP'dan necha % uzoqlashgan (chased ekanini bilish uchun)."""
    p, w = _f(price), _f(vwap, -1)
    if w <= 0:
        return None
    return round((p - w) / w * 100.0, 2)


def avg_volume_from_daily(daily_candles: List[Dict[str, Any]], window: int = 20) -> float:
    """Kunlik shamlardan oxirgi `window` kun o'rtacha hajmi (bugungi kun chiqarib tashlanadi)."""
    if not daily_candles:
        return 0.0
    vols = [_f(c.get("v")) for c in daily_candles[-(window + 1):-1]] or [_f(c.get("v")) for c in daily_candles[-window:]]
    return round(sum(vols) / len(vols), 2) if vols else 0.0


def compute_indicators(
    *,
    price: float,
    prev_close: Optional[float],
    current_volume: float,
    avg_20d_volume: float,
    bid: Optional[float],
    ask: Optional[float],
    candles_5m: List[Dict[str, Any]],
    day_high: Optional[float] = None,
    day_low: Optional[float] = None,
) -> Dict[str, Any]:
    """Bitta ticker uchun barcha indikatorlarni hisoblaydi va dict qaytaradi."""
    closes_5m = [_f(c.get("c")) for c in candles_5m]
    vwap_series = session_vwap(candles_5m)
    vwap_now = vwap_series[-1] if vwap_series else None
    ema9_series = ema(closes_5m, 9)
    ema20_series = ema(closes_5m, 20)
    ema9 = ema9_series[-1] if ema9_series else None
    ema20 = ema20_series[-1] if ema20_series else None
    ema9_prev = ema9_series[-2] if len(ema9_series) >= 2 else None

    spike = volume_spike_ratio(candles_5m)

    return {
        "price": round(_f(price), 4),
        "prev_close": prev_close,
        "current_volume": int(_f(current_volume)),
        "avg_20d_volume": int(_f(avg_20d_volume)),
        "rvol": rvol(current_volume, avg_20d_volume),
        "dollar_volume": dollar_volume(price, current_volume),
        "vwap": vwap_now,
        "vwap_series": vwap_series,
        "ema9": round(ema9, 4) if ema9 is not None else None,
        "ema20": round(ema20, 4) if ema20 is not None else None,
        "ema9_rising": (ema9 is not None and ema9_prev is not None and ema9 > ema9_prev),
        "candle_5m_close": round(closes_5m[-1], 4) if closes_5m else None,
        "vol_spike_ratio": spike,
        "vol_spike_class": classify_volume_spike(spike),
        "spread_pct": spread_pct(bid, ask, price),
        "change_pct": pct_change(price, prev_close),
        "day_high": round(_f(day_high), 4) if day_high else None,
        "day_low": round(_f(day_low), 4) if day_low else None,
        "vwap_extension_pct": vwap_extension_pct(price, vwap_now),
    }
