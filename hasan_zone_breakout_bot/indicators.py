"""indicators.py — sof matematik funksiyalar (tarmoqsiz, testlanadigan).

VWAP, EMA9/20, ATR, RVOL, dollar volume, spread%, volume spike.
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
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    prev = sma
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def session_vwap(candles: List[Dict[str, Any]]) -> List[Optional[float]]:
    """Sessiya VWAP — kumulyativ (typical_price × hajm) / kumulyativ hajm."""
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


def atr(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    """O'rtacha haqiqiy diapazon (ATR) — oxirgi qiymat."""
    if len(candles) < 2:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        h = _f(candles[i].get("h"))
        low = _f(candles[i].get("l"))
        pc = _f(candles[i - 1].get("c"))
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    window = trs[-period:] if len(trs) >= period else trs
    return round(sum(window) / len(window), 6) if window else None


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


def volume_spike_ratio(candles: List[Dict[str, Any]], lookback: int = 20) -> Optional[float]:
    """Hajm portlashi = oxirgi sham hajmi / oldingi `lookback` shamning o'rtachasi."""
    if len(candles) < 2:
        return None
    last_vol = _f(candles[-1].get("v"))
    window = candles[-(lookback + 1):-1]
    if not window:
        return None
    vols = [_f(c.get("v")) for c in window]
    avg = sum(vols) / len(vols) if vols else 0.0
    if avg <= 0:
        return None
    return round(last_vol / avg, 2)


def classify_volume_spike(ratio: Optional[float]) -> str:
    """normal / strong / ignition / weak / unknown."""
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
    """Narx VWAP'dan necha % uzoqlashgan (chase ekanini bilish uchun)."""
    p, w = _f(price), _f(vwap, -1)
    if w <= 0:
        return None
    return round((p - w) / w * 100.0, 2)


def volume_contracting(candles: List[Dict[str, Any]], lookback: int = 6) -> bool:
    """Breakout oldidan hajm pasaymoqda/barqaror (consolidation belgisi)."""
    if len(candles) < lookback + 1:
        return False
    recent = [_f(c.get("v")) for c in candles[-lookback:]]
    prior = [_f(c.get("v")) for c in candles[-(2 * lookback):-lookback]]
    if not recent or not prior:
        return False
    return (sum(recent) / len(recent)) <= (sum(prior) / len(prior)) * 1.05


def avg_volume_from_daily(daily_candles: List[Dict[str, Any]], window: int = 20) -> float:
    """Kunlik shamlardan oxirgi `window` kun o'rtacha hajmi (bugun chiqarib tashlanadi)."""
    if not daily_candles:
        return 0.0
    tail = daily_candles[-(window + 1):-1] or daily_candles[-window:]
    vols = [_f(c.get("v")) for c in tail]
    return round(sum(vols) / len(vols), 2) if vols else 0.0
