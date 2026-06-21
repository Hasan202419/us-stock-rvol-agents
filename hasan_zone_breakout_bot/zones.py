"""zones.py — demand/supply zona aniqlash + consolidation + breakout (sof mantiq).

Oddiy, beginner-friendly yondashuv (faqat OHLCV):
- Swing low/high (mahalliy ekstremumlar) topiladi.
- Yaqin darajalar klasterlanib zona qilinadi; zona kengligi ATR'ga asoslanadi.
- Demand zona = takroriy pastliklar (narx sakragan); Supply zona = takroriy yuqoriliklar.
- Consolidation, false breakdown (liquidity sweep), zone breakout aniqlanadi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config
from .indicators import _f, atr, volume_contracting, volume_spike_ratio


def _swing_lows(candles: List[Dict[str, Any]], k: int) -> List[float]:
    """Mahalliy minimumlar: chap/o'ng `k` shamdan past low."""
    lows: List[float] = []
    n = len(candles)
    for i in range(k, n - k):
        low_i = _f(candles[i].get("l"))
        if low_i <= 0:
            continue
        left = all(low_i <= _f(candles[i - j].get("l")) for j in range(1, k + 1))
        right = all(low_i <= _f(candles[i + j].get("l")) for j in range(1, k + 1))
        if left and right:
            lows.append(low_i)
    return lows


def _swing_highs(candles: List[Dict[str, Any]], k: int) -> List[float]:
    """Mahalliy maksimumlar: chap/o'ng `k` shamdan baland high."""
    highs: List[float] = []
    n = len(candles)
    for i in range(k, n - k):
        high_i = _f(candles[i].get("h"))
        if high_i <= 0:
            continue
        left = all(high_i >= _f(candles[i - j].get("h")) for j in range(1, k + 1))
        right = all(high_i >= _f(candles[i + j].get("h")) for j in range(1, k + 1))
        if left and right:
            highs.append(high_i)
    return highs


def _cluster_levels(levels: List[float], width: float) -> List[float]:
    """Yaqin darajalarni (width ichida) klasterlab o'rtacha qiymat qaytaradi."""
    if not levels:
        return []
    ordered = sorted(levels)
    clusters: List[List[float]] = [[ordered[0]]]
    for lv in ordered[1:]:
        if abs(lv - clusters[-1][-1]) <= width:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    return [round(sum(c) / len(c), 4) for c in clusters]


def detect_zones(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Demand va supply zonalarni aniqlaydi (1H yoki 5M shamlardan).

    Qaytadi: {"demand": [(low, high), ...], "supply": [...], "atr": float}.
    Zona kengligi = ATR × ZONE_ATR_WIDTH_MULT.
    """
    if len(candles) < (2 * config.ZONE_SWING_LOOKBACK + 2):
        return {"demand": [], "supply": [], "atr": None}
    a = atr(candles) or 0.0
    width = max(a * config.ZONE_ATR_WIDTH_MULT, 1e-6)
    k = config.ZONE_SWING_LOOKBACK

    demand_centers = _cluster_levels(_swing_lows(candles, k), width)
    supply_centers = _cluster_levels(_swing_highs(candles, k), width)

    demand = [(round(c - width / 2, 4), round(c + width / 2, 4)) for c in demand_centers]
    supply = [(round(c - width / 2, 4), round(c + width / 2, 4)) for c in supply_centers]
    return {"demand": demand, "supply": supply, "atr": round(a, 6)}


def price_in_zone(price: float, zone: tuple) -> bool:
    """Narx zona [low, high] ichidami (kichik tolerantlik bilan)."""
    if not zone:
        return False
    low, high = zone
    pad = (high - low) * 0.05
    return (low - pad) <= price <= (high + pad)


def nearest_demand_zone(price: float, zones: Dict[str, Any]) -> Optional[tuple]:
    """Narxga eng yaqin (ichida yoki ostidagi) demand zona."""
    demand = zones.get("demand") or []
    in_zone = [z for z in demand if price_in_zone(price, z)]
    if in_zone:
        return in_zone[0]
    below = [z for z in demand if z[1] <= price]
    if below:
        return max(below, key=lambda z: z[1])  # eng yuqori (yaqin) demand
    return None


def detect_consolidation(candles: List[Dict[str, Any]], zone: tuple) -> Dict[str, Any]:
    """Zona ichida konsolidatsiya (spec).

    ZONE_CONSOLIDATION = True agar:
      - oxirgi 6..12 sham asosan zona ichida (≥70% close)
      - range oldingi rangega nisbatan tor
      - hajm pasaymoqda/barqaror
      - zona ostida kuchli yopilish yo'q
    """
    out = {"consolidation": False, "inside_frac": 0.0, "volume_contraction": False, "tight": False}
    if not zone or len(candles) < config.ZONE_CONSOLIDATION_MIN_BARS + 1:
        return out
    low, high = zone
    n = min(config.ZONE_CONSOLIDATION_MAX_BARS, len(candles))
    window = candles[-n:]

    closes_inside = sum(1 for c in window if low <= _f(c.get("c")) <= high)
    inside_frac = closes_inside / len(window)
    out["inside_frac"] = round(inside_frac, 2)

    # Range torligi: oxirgi oyna diapazoni < oldingi oyna diapazoni
    recent_range = max(_f(c.get("h")) for c in window) - min(_f(c.get("l")) for c in window)
    prior = candles[-(2 * n):-n] if len(candles) >= 2 * n else window
    prior_range = max(_f(c.get("h")) for c in prior) - min(_f(c.get("l")) for c in prior)
    tight = recent_range <= prior_range * 1.0 if prior_range > 0 else False
    out["tight"] = tight

    vol_contract = volume_contracting(candles, lookback=max(3, n // 2))
    out["volume_contraction"] = vol_contract

    # Zona ostida kuchli yopilish bo'lmasligi kerak
    strong_close_below = any(_f(c.get("c")) < low * 0.99 for c in window)

    out["consolidation"] = (
        inside_frac >= config.ZONE_CONSOLIDATION_INSIDE_FRAC
        and tight
        and not strong_close_below
    )
    return out


def detect_false_breakdown(candles: List[Dict[str, Any]], zone: tuple, lookback: int = 6) -> bool:
    """Liquidity sweep: narx zona ostiga qisqa tushib, keyin ichiga/ustiga qaytib yopiladi."""
    if not zone or len(candles) < 3:
        return False
    low, high = zone
    window = candles[-lookback:] if len(candles) >= lookback else candles
    swept = any(_f(c.get("l")) < low for c in window)
    last_close = _f(candles[-1].get("c"))
    reclaimed = last_close >= low
    return swept and reclaimed


def detect_zone_breakout(candles: List[Dict[str, Any]], zone: tuple, consolidation_ok: bool) -> Dict[str, Any]:
    """Zona breakout (spec).

    ZONE_BREAKOUT = True agar:
      - consolidation True
      - sham zona high ustida yopiladi
      - breakout shamida volume spike ≥ 1.5x
      - sham o'z diapazonining yuqori 40% ida yopiladi
    """
    out = {"breakout": False, "spike": None, "close_upper": False}
    if not zone or not consolidation_ok or len(candles) < 2:
        return out
    _low, high = zone
    last = candles[-1]
    h, lo, c = _f(last.get("h")), _f(last.get("l")), _f(last.get("c"))
    rng = h - lo
    close_pos = (c - lo) / rng if rng > 0 else 0.0
    out["close_upper"] = close_pos >= config.ZONE_BREAKOUT_CLOSE_UPPER_FRAC

    spike = volume_spike_ratio(candles)
    out["spike"] = spike

    out["breakout"] = (
        c > high
        and spike is not None
        and spike >= config.VOL_SPIKE_STRONG
        and out["close_upper"]
    )
    return out
