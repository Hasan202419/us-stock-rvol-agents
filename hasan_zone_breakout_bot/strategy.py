"""strategy.py — Zone Breakout + VWAP Reclaim + Volume-Time scoring va qaror.

Spec bo'yicha 15-mezonli ballash, 0-5/6-8/9-11/12+ qaror bosqichlari va QAT'IY
override qoidalari (stop yo'q -> NO_TRADE, RR<1:2 -> NO_TRADE, choppy -> WATCHLIST,
bozor yopiq -> MARKET_CLOSED, kechikkan ma'lumot -> HIGH_QUALITY emas).

HECH qanday order yo'q — faqat tahlil + signal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config, zones
from .indicators import (
    _f,
    classify_volume_spike,
    dollar_volume,
    ema,
    pct_change,
    rvol,
    session_vwap,
    spread_pct,
    volume_spike_ratio,
    vwap_extension_pct,
)


def detect_vwap_reclaim(candles: List[Dict[str, Any]], vwap_series: List[Optional[float]]) -> Dict[str, Any]:
    """VWAP reclaim: oldin VWAP ostida/yaqinida, keyin ustida yopilib ushlab turadi."""
    out = {"reclaimed": False, "closed_above": False, "holds": False}
    n = len(candles)
    if n < 3 or not vwap_series or vwap_series[-1] is None:
        return out
    last_close = _f(candles[-1].get("c"))
    last_vwap = vwap_series[-1]
    out["closed_above"] = last_close > last_vwap
    for i in range(max(1, n - 5), n):
        vw, vw_prev = vwap_series[i], vwap_series[i - 1]
        if vw is None or vw_prev is None:
            continue
        if _f(candles[i - 1].get("c")) <= vw_prev and _f(candles[i].get("c")) > vw:
            out["reclaimed"] = True
            holds = True
            for j in range(i + 1, n):
                vwj = vwap_series[j]
                if vwj is not None and _f(candles[j].get("c")) < vwj * 0.997:
                    holds = False
                    break
            out["holds"] = holds if i < n - 1 else out["closed_above"]
            break
    return out


def _higher_low(candles: List[Dict[str, Any]], lookback: int = 6) -> bool:
    """Strukturali higher-low (3M tasdig'i uchun)."""
    if len(candles) < lookback + 2:
        return False
    lows = [_f(c.get("l")) for c in candles[-lookback:]]
    mid = len(lows) // 2
    return min(lows[mid:]) > min(lows[:mid])


def _build_trade_levels(
    *, breakout_high: float, zone: Optional[tuple], vwap: float, day_high: float,
    supply_zone: Optional[tuple],
) -> Dict[str, Any]:
    """Entry / Stop / Target1 / Target2 / R:R — qat'iy qoidalar."""
    out = {"entry": None, "stop_loss": None, "target1": None, "target2": None,
           "risk_reward": None, "no_trade_reason": None}
    if breakout_high <= 0:
        out["no_trade_reason"] = "Breakout sham yo'q — kirish aniq emas"
        return out
    entry = round(breakout_high + 0.01, 4)

    # Stop nomzodlari: zona low, VWAP — entry ostidagi eng yuqori (tight) tanlanadi
    candidates = []
    if zone:
        candidates.append(zone[0])
    if vwap > 0:
        candidates.append(vwap)
    below = [s for s in candidates if 0 < s < entry]
    if below:
        stop = round(max(below) - 0.01, 4)
    else:
        any_pos = [s for s in candidates if s > 0]
        if not any_pos:
            out["no_trade_reason"] = "Stop-loss aniq emas (zona/VWAP yo'q)"
            return out
        stop = round(min(any_pos) - 0.01, 4)
    if stop >= entry:
        out["no_trade_reason"] = "Stop entry'dan yuqori — setup buzilgan"
        return out

    risk = entry - stop
    if risk <= 0:
        out["no_trade_reason"] = "Risk noldan kichik"
        return out

    # Target1: VWAP (entry undan past bo'lsa) yoki day high yoki 1R
    t1_candidates = [entry + risk]
    if vwap > entry:
        t1_candidates.append(vwap)
    if day_high > entry:
        t1_candidates.append(day_high)
    target1 = round(min(t1_candidates), 4)

    # Target2: 2R yoki keyingi qarshilik (supply zona pasti)
    t2 = entry + 2 * risk
    if supply_zone and supply_zone[0] > t2:
        t2 = supply_zone[0]
    target2 = round(t2, 4)

    rr = round((target2 - entry) / risk, 2) if risk > 0 else 0.0
    out.update({"entry": entry, "stop_loss": stop, "target1": target1,
                "target2": target2, "risk_reward": rr})
    if rr < config.MIN_RISK_REWARD:
        out["no_trade_reason"] = f"R:R {rr} < {config.MIN_RISK_REWARD} (1:2 dan past)"
    return out


def score_to_decision(score: int) -> str:
    for decision, (lo, hi) in config.DECISION_THRESHOLDS.items():
        if lo <= score <= hi:
            return decision
    return "NO_TRADE"


def evaluate_setup(
    data: Dict[str, Any],
    *,
    mode: str,
    regime: Dict[str, Any],
    halal_status: str = "UNKNOWN",
    market_open: bool = True,
) -> Dict[str, Any]:
    """Bitta ticker uchun zona-breakout setup -> ball, qaror, darajalar, sabab."""
    ticker = str(data.get("ticker") or "?").upper()
    c5 = data.get("candles_5m") or []
    c3 = data.get("candles_3m") or []
    c1h = data.get("candles_1h") or []
    price = _f(data.get("price"))

    closes5 = [_f(c.get("c")) for c in c5]
    vwap_series = session_vwap(c5)
    vwap = vwap_series[-1] if vwap_series and vwap_series[-1] is not None else 0.0
    ema9 = ema(closes5, 9)[-1] if closes5 else None
    ema20 = ema(closes5, 20)[-1] if closes5 else None
    ema9_prev = ema(closes5, 9)[-2] if len(closes5) >= 2 else None
    ema_rising = ema9 is not None and ema9_prev is not None and ema9 > ema9_prev

    spike = volume_spike_ratio(c5)
    spread = spread_pct(data.get("bid"), data.get("ask"), price)
    rv = rvol(data.get("current_volume", 0), data.get("avg_20d_volume", 0))
    dvol = dollar_volume(price, data.get("current_volume", 0))
    chg = pct_change(price, data.get("prev_close"))

    # Zonalar: 1H (yoki 5M zaxira)
    zone_source = c1h if len(c1h) >= 8 else c5
    zinfo = zones.detect_zones(zone_source)
    demand_zone = zones.nearest_demand_zone(price, zinfo)
    supply_zones = zinfo.get("supply") or []
    supply_zone = min((z for z in supply_zones if z[0] > price), default=None, key=lambda z: z[0]) if supply_zones else None

    in_zone = demand_zone is not None and zones.price_in_zone(price, demand_zone)
    cons = zones.detect_consolidation(c5, demand_zone) if demand_zone else {"consolidation": False, "volume_contraction": False}
    false_bd = zones.detect_false_breakdown(c5, demand_zone) if demand_zone else False
    breakout5 = zones.detect_zone_breakout(c5, demand_zone, cons.get("consolidation", False)) if demand_zone else {"breakout": False}
    breakout3 = zones.detect_zone_breakout(c3, demand_zone, cons.get("consolidation", False)) if (demand_zone and c3) else {"breakout": False}
    confirm_3m = bool(breakout3.get("breakout")) or _higher_low(c3)

    reclaim = detect_vwap_reclaim(c5, vwap_series)

    # ---- SCORING (spec) ----
    w = config.SCORE_WEIGHTS
    flags: Dict[str, bool] = {}
    flags["in_zone"] = in_zone
    flags["consolidation"] = bool(cons.get("consolidation"))
    flags["volume_contraction"] = bool(cons.get("volume_contraction"))
    flags["false_breakdown"] = bool(false_bd)
    flags["zone_breakout"] = bool(breakout5.get("breakout"))
    flags["vwap_reclaim"] = bool(reclaim.get("reclaimed") and reclaim.get("closed_above"))
    flags["confirm_3m"] = bool(confirm_3m)
    flags["confirm_5m_vwap"] = bool(price > vwap) if vwap else False
    flags["spike_1_5x"] = spike is not None and spike >= config.VOL_SPIKE_STRONG
    flags["spike_3x"] = spike is not None and spike >= config.VOL_SPIKE_IGNITION
    flags["ema_bullish"] = (ema9 is not None and ema20 is not None and ema9 > ema20) or ema_rising
    flags["spread_ok"] = spread is not None and spread <= config.MAX_SPREAD_PCT
    flags["regime_bullish"] = bool(regime.get("bullish"))
    flags["halal_compliant"] = halal_status == "COMPLIANT"

    # Trade levels (rr_ok scoring uchun kerak)
    breakout_high = _f(c5[-1].get("h")) if c5 else 0.0
    if demand_zone:
        breakout_high = max(breakout_high, demand_zone[1])
    levels = _build_trade_levels(
        breakout_high=breakout_high, zone=demand_zone, vwap=vwap,
        day_high=_f(data.get("day_high")), supply_zone=supply_zone,
    )
    rr = levels.get("risk_reward")
    flags["rr_ok"] = rr is not None and rr >= config.MIN_RISK_REWARD

    score = sum(w[k] for k, v in flags.items() if v)
    decision = score_to_decision(score)

    # ---- QAT'IY OVERRIDE ----
    reasons: List[str] = []
    data_complete = bool(data.get("data_complete"))

    if not market_open:
        decision = "MARKET_CLOSED"
        reasons.append("Bozor yopiq — yangi signal yo'q")
    if levels.get("no_trade_reason"):
        decision = "NO_TRADE"
        reasons.append(levels["no_trade_reason"])
    if spread is None and decision in {"PAPER_READY", "HIGH_QUALITY_PAPER_READY"}:
        decision = "WATCHLIST"
        reasons.append("Spread UNKNOWN — paper-ready bloklandi")
    if not data_complete and decision == "HIGH_QUALITY_PAPER_READY":
        decision = "PAPER_READY"
        reasons.append("Ma'lumot kechikkan — HIGH_QUALITY emas")
    if regime.get("choppy") and decision in {"PAPER_READY", "HIGH_QUALITY_PAPER_READY"}:
        decision = "WATCHLIST"
        reasons.append("Bozor choppy — watchlist only")
    if regime.get("bearish") and decision in {"PAPER_READY", "HIGH_QUALITY_PAPER_READY"}:
        very_strong = rv >= config.PENNY_STRONG_RVOL and reclaim.get("holds")
        if not very_strong:
            decision = "WATCHLIST"
            reasons.append("Bozor bearish — kuchli RS+reclaim shart")

    if not reasons:
        reasons.append("Zona breakout + VWAP reclaim + hajm tasdig'i")

    vwap_status = "Reclaim+hold" if (reclaim.get("reclaimed") and reclaim.get("holds")) else (
        "VWAP ustida" if (vwap and price > vwap) else "VWAP ostida")
    zone_status = "Breakout" if flags["zone_breakout"] else ("Consolidation" if flags["consolidation"] else (
        "Zona ichida" if in_zone else "Zonadan tashqari"))

    return {
        "ticker": ticker,
        "mode": mode,
        "price": round(price, 4),
        "vwap": round(vwap, 4) if vwap else None,
        "ema9": round(ema9, 4) if ema9 is not None else None,
        "ema20": round(ema20, 4) if ema20 is not None else None,
        "rvol": rv,
        "dollar_volume": dvol,
        "spread_pct": spread,
        "change_pct": chg,
        "volume_spike": spike,
        "volume_spike_class": classify_volume_spike(spike),
        "vwap_extension_pct": vwap_extension_pct(price, vwap),
        "day_high": data.get("day_high"),
        "day_low": data.get("day_low"),
        "prev_close": data.get("prev_close"),
        "zone_low": demand_zone[0] if demand_zone else None,
        "zone_high": demand_zone[1] if demand_zone else None,
        "consolidation": flags["consolidation"],
        "breakout": flags["zone_breakout"],
        "false_breakdown": flags["false_breakdown"],
        "vwap_status": vwap_status,
        "zone_status": zone_status,
        "score": score,
        "decision": decision,
        "halal_status": halal_status,
        "entry": levels.get("entry"),
        "stop_loss": levels.get("stop_loss"),
        "target1": levels.get("target1"),
        "target2": levels.get("target2"),
        "risk_reward": rr,
        "reason": "; ".join(reasons),
        "regime_name": regime.get("regime", "UNKNOWN"),
        "data_complete": data_complete,
        "_flags": flags,
    }
