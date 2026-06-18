"""strategy.py — Hasan Scalping setup: VWAP Reclaim + Volume-Time Confirmation.

Asosiy g'oya: "Hajm o'zi signal emas. Hajm oshganda NARX nima qiladi?"

Bu modul indikatorlardan QAT'IY qaror chiqaradi: NO_TRADE / WATCHLIST /
PAPER_READY / HIGH_QUALITY_PAPER_READY. Standart — qattiq: setup toza bo'lmasa
NO_TRADE. Yomon savdodan ko'ra savdoni o'tkazib yuborish yaxshiroq.

HECH qanday real order yo'q — faqat tahlil + paper-review.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def detect_vwap_reclaim(
    candles_5m: List[Dict[str, Any]],
    vwap_series: List[Optional[float]],
) -> Dict[str, Any]:
    """5-min shamlarda VWAP reclaim (qaytarib egallash)ni aniqlaydi.

    Reclaim = oldin VWAP ostida/yaqinida bo'lgan narx, VWAP ustida YOPILADI,
    keyingi sham VWAP ustida ushlaб turadi (yoki retest qilib sakraydi).
    """
    out = {
        "reclaimed": False,
        "reclaim_index": None,
        "reclaim_high": None,
        "reclaim_low": None,
        "holds_above": False,
        "closed_above_vwap": False,
    }
    n = len(candles_5m)
    if n < 3:
        return out

    # Oxirgi yopilgan sham VWAP ustidami?
    last_close = _f(candles_5m[-1].get("c"))
    last_vwap = vwap_series[-1] if vwap_series and vwap_series[-1] is not None else None
    if last_vwap is None:
        return out
    out["closed_above_vwap"] = last_close > last_vwap

    # Oxirgi 5 sham ichida reclaim nuqtasini izlaymiz
    search_from = max(1, n - 5)
    for i in range(search_from, n):
        vw = vwap_series[i]
        vw_prev = vwap_series[i - 1]
        if vw is None or vw_prev is None:
            continue
        c_now = _f(candles_5m[i].get("c"))
        c_prev = _f(candles_5m[i - 1].get("c"))
        # oldingi sham VWAP ostida/teng, joriy sham VWAP ustida yopildi = reclaim
        if c_prev <= vw_prev and c_now > vw:
            out["reclaimed"] = True
            out["reclaim_index"] = i
            out["reclaim_high"] = round(_f(candles_5m[i].get("h")), 4)
            out["reclaim_low"] = round(_f(candles_5m[i].get("l")), 4)
            # reclaim'dan keyingi sham(lar) VWAP ustida ushlanyaptimi
            if i < n - 1:
                later_ok = True
                for j in range(i + 1, n):
                    vwj = vwap_series[j]
                    if vwj is None:
                        continue
                    low_j = _f(candles_5m[j].get("l"))
                    close_j = _f(candles_5m[j].get("c"))
                    # retest bo'lsa ham, yopilish VWAP ustida bo'lishi kerak
                    if close_j < vwj and low_j < vwj * 0.997:
                        later_ok = False
                        break
                out["holds_above"] = later_ok
            else:
                out["holds_above"] = out["closed_above_vwap"]
            break
    return out


def _build_trade_levels(
    ind: Dict[str, Any],
    reclaim: Dict[str, Any],
) -> Dict[str, Any]:
    """Entry / Stop-loss / Target1 / Target2 / R:R — qat'iy qoidalar bilan."""
    vwap = _f(ind.get("vwap"), -1)
    day_high = _f(ind.get("day_high"), -1)
    reclaim_high = _f(reclaim.get("reclaim_high"), -1)
    reclaim_low = _f(reclaim.get("reclaim_low"), -1)

    levels: Dict[str, Any] = {
        "entry": None, "stop_loss": None, "target1": None,
        "target2": None, "risk_reward": None, "no_trade_reason": None,
    }

    # ENTRY: reclaim sham high ustida (chase qilmaymiz)
    if reclaim_high > 0:
        entry = round(reclaim_high + 0.01, 4)
    else:
        levels["no_trade_reason"] = "Reclaim sham yo'q — kirish nuqtasi aniq emas"
        return levels

    # STOP: VWAP ostida YOKI reclaim sham low ostida. Skalp uchun ENG TIGHT (entry'ga yaqin)
    # mantiqiy stop — ya'ni entry ostidagi eng YUQORI nomzod (kichik risk).
    stop_candidates = [s for s in (vwap, reclaim_low) if 0 < s < entry]
    if stop_candidates:
        stop = round(max(stop_candidates) - 0.01, 4)
    else:
        any_pos = [s for s in (vwap, reclaim_low) if s > 0]
        if not any_pos:
            levels["no_trade_reason"] = "Stop-loss aniq emas (VWAP/reclaim low yo'q)"
            return levels
        stop = round(min(any_pos) - 0.01, 4)
    if stop >= entry:
        levels["no_trade_reason"] = "Stop entry'dan yuqori — setup buzilgan"
        return levels

    risk = entry - stop
    if risk <= 0:
        levels["no_trade_reason"] = "Risk noldan kichik"
        return levels

    # TARGET1 = 1R (qisman chiqish). TARGET2 = 2R (asosiy maqsad) yoki day high (resistance).
    target1 = round(entry + risk, 4)
    target2_2r = entry + 2 * risk
    target2 = round(max(target2_2r, day_high), 4) if day_high > target2_2r else round(target2_2r, 4)

    # R:R — asosiy (2R) maqsadga nisbatan
    rr = round((target2 - entry) / risk, 2) if risk > 0 else 0.0

    levels.update({
        "entry": entry,
        "stop_loss": stop,
        "target1": target1,
        "target2": target2,
        "risk_reward": rr,
    })
    if rr < config.MIN_RISK_REWARD:
        levels["no_trade_reason"] = f"R:R {rr} < {config.MIN_RISK_REWARD} (1:2 dan past)"
    return levels


def passes_hard_filters(ind: Dict[str, Any]) -> List[str]:
    """Majburiy filtrlar. Buzilganlar ro'yxati (bo'sh = hammasi o'tdi)."""
    fails: List[str] = []
    price = _f(ind.get("price"))
    if not (config.PRICE_MIN <= price <= config.PRICE_MAX):
        fails.append("price_range")
    if _f(ind.get("current_volume")) < config.MIN_CURRENT_VOLUME:
        fails.append("current_volume")
    if _f(ind.get("avg_20d_volume")) < config.MIN_AVG_20D_VOLUME:
        fails.append("avg_volume")
    if _f(ind.get("rvol")) < config.MIN_RVOL:
        fails.append("rvol")
    if _f(ind.get("dollar_volume")) < config.MIN_DOLLAR_VOLUME:
        fails.append("dollar_volume")
    chg = ind.get("change_pct")
    if chg is None or not (config.MIN_CHANGE_PCT <= _f(chg) <= config.MAX_CHANGE_PCT):
        fails.append("change_pct")
    return fails


def score_signal(
    ind: Dict[str, Any],
    reclaim: Dict[str, Any],
    levels: Dict[str, Any],
    market_bullish: bool,
) -> int:
    """0..10 ball — spetsifikatsiya bo'yicha."""
    score = 0
    price = _f(ind.get("price"))
    if market_bullish:
        score += 1
    if config.PRICE_MIN <= price <= config.PRICE_MAX:
        score += 1
    if _f(ind.get("dollar_volume")) >= config.MIN_DOLLAR_VOLUME:
        score += 1
    if _f(ind.get("rvol")) >= config.MIN_RVOL:
        score += 1
    if _f(ind.get("rvol")) >= config.STRONG_RVOL:
        score += 1
    spread = ind.get("spread_pct")
    if spread is not None and _f(spread) <= config.MAX_SPREAD_PCT:
        score += 1
    if reclaim.get("reclaimed"):
        score += 2
    if reclaim.get("closed_above_vwap"):
        score += 1
    ema9, ema20 = ind.get("ema9"), ind.get("ema20")
    if (ema9 is not None and ema20 is not None and ema9 > ema20) or ind.get("ema9_rising"):
        score += 1
    rr = levels.get("risk_reward")
    if rr is not None and _f(rr) >= config.MIN_RISK_REWARD:
        score += 1
    return min(score, config.SCORE_MAX)


def score_to_decision(score: int) -> str:
    for decision, (lo, hi) in config.DECISION_THRESHOLDS.items():
        if lo <= score <= hi:
            return decision
    return "NO_TRADE"


def _mistake_warning(ind: Dict[str, Any], reclaim: Dict[str, Any], levels: Dict[str, Any]) -> str:
    """Xato ogohlantirishi — emotsional/chase savdolardan himoya."""
    warns: List[str] = []
    ext = ind.get("vwap_extension_pct")
    if ext is not None and _f(ext) > config.MAX_VWAP_EXTENSION_PCT:
        warns.append(f"VWAP'dan uzoq ({ext}%) — CHASE QILMA")
    if ind.get("spread_pct") is None:
        warns.append("Spread UNKNOWN — paper-ready emas")
    elif _f(ind.get("spread_pct")) > config.MAX_SPREAD_PCT:
        warns.append("Spread keng — slippage xavfi")
    spike = ind.get("vol_spike_ratio")
    if spike is None or _f(spike) < config.MIN_VOL_SPIKE_FOR_SIGNAL:
        warns.append("Hajm portlashi sust — kuchsiz tasdiq")
    if not reclaim.get("reclaimed"):
        warns.append("VWAP reclaim yo'q — setup to'liq emas")
    if levels.get("no_trade_reason"):
        warns.append(levels["no_trade_reason"])
    return " | ".join(warns) if warns else "Toza setup — lekin baribir manual review"


def evaluate(
    ind: Dict[str, Any],
    *,
    market_bullish: bool,
    market_choppy: bool = False,
    market_bearish: bool = False,
    data_complete: bool = True,
) -> Dict[str, Any]:
    """Bitta ticker uchun yakuniy signal: ball, qaror, darajalar, sabab, ogohlantirish."""
    vwap_series = ind.get("vwap_series") or []
    candles_5m = ind.get("_candles_5m") or []

    reclaim = detect_vwap_reclaim(candles_5m, vwap_series) if candles_5m else {
        "reclaimed": False, "closed_above_vwap": False, "holds_above": False,
        "reclaim_high": None, "reclaim_low": None, "reclaim_index": None,
    }
    levels = _build_trade_levels(ind, reclaim)

    hard_fails = passes_hard_filters(ind)
    score = score_signal(ind, reclaim, levels, market_bullish)
    decision = score_to_decision(score)

    # --- QAT'IY himoya qoidalari (override) ---
    reasons: List[str] = []

    # 1) Majburiy filtr buzilsa -> NO_TRADE
    if hard_fails:
        decision = "NO_TRADE"
        reasons.append("Filtr buzildi: " + ", ".join(hard_fails))

    # 2) Stop yo'q yoki R:R past -> NO_TRADE
    if levels.get("no_trade_reason"):
        decision = "NO_TRADE"
        reasons.append(levels["no_trade_reason"])

    # 3) VWAP reclaim yoki yopilish yo'q -> ko'pi bilan WATCHLIST
    if not (reclaim.get("reclaimed") and reclaim.get("closed_above_vwap")):
        if decision in {"PAPER_READY", "HIGH_QUALITY_PAPER_READY"}:
            decision = "WATCHLIST"
        reasons.append("VWAP reclaim tasdig'i to'liq emas")

    # 4) Volume spike sust -> paper-ready emas
    spike = ind.get("vol_spike_ratio")
    if (spike is None or _f(spike) < config.MIN_VOL_SPIKE_FOR_SIGNAL) and decision.endswith("PAPER_READY"):
        decision = "WATCHLIST"
        reasons.append("Hajm portlashi 1.5x dan past")

    # 5) Spread UNKNOWN -> paper-ready emas (faqat watchlist)
    if ind.get("spread_pct") is None and decision.endswith("PAPER_READY"):
        decision = "WATCHLIST"
        reasons.append("Spread UNKNOWN — paper-ready bloklandi")

    # 6) Ma'lumot to'liq emas/kechikkan -> ko'pi bilan WATCHLIST
    if not data_complete and decision.endswith("PAPER_READY"):
        decision = "WATCHLIST"
        reasons.append("Ma'lumot kechikkan/to'liq emas")

    # 7) Bozor rejimi
    if market_bearish and decision.endswith("PAPER_READY"):
        # faqat juda kuchli + toza reclaim bo'lsa qoldiramiz
        very_strong = _f(ind.get("rvol")) >= config.STRONG_RVOL and reclaim.get("holds_above")
        if not very_strong:
            decision = "WATCHLIST"
            reasons.append("Bozor bearish — paper-ready bloklandi")
    elif market_choppy and decision.endswith("PAPER_READY"):
        decision = "WATCHLIST"
        score = max(0, score - 1)
        reasons.append("Bozor choppy — ball kamaytirildi, watchlist")

    if not reasons:
        reasons.append("Toza VWAP reclaim + hajm tasdig'i")

    return {
        "ticker": ind.get("ticker"),
        "score": score,
        "decision": decision,
        "entry": levels.get("entry"),
        "stop_loss": levels.get("stop_loss"),
        "target1": levels.get("target1"),
        "target2": levels.get("target2"),
        "risk_reward": levels.get("risk_reward"),
        "vwap_status": _vwap_status(ind, reclaim),
        "ema_status": _ema_status(ind),
        "reason": "; ".join(reasons),
        "mistake_warning": _mistake_warning(ind, reclaim, levels),
        "_reclaim": reclaim,
        "_hard_fails": hard_fails,
    }


def _vwap_status(ind: Dict[str, Any], reclaim: Dict[str, Any]) -> str:
    price = _f(ind.get("price"))
    vwap = _f(ind.get("vwap"), -1)
    if vwap <= 0:
        return "VWAP yo'q"
    if reclaim.get("reclaimed") and reclaim.get("holds_above"):
        return "Reclaim + ushlab turibdi"
    if reclaim.get("reclaimed"):
        return "Reclaim (kuzating)"
    return "VWAP ustida" if price > vwap else "VWAP ostida"


def _ema_status(ind: Dict[str, Any]) -> str:
    ema9, ema20 = ind.get("ema9"), ind.get("ema20")
    if ema9 is None or ema20 is None:
        return "EMA yo'q"
    if ema9 > ema20:
        return "EMA9>EMA20 (bullish)"
    if ind.get("ema9_rising"):
        return "EMA9 ko'tarilmoqda"
    return "EMA bearish"
