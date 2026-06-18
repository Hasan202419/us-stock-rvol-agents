"""Order Flow signal — CLC qoidasi (Context · Location · Confirmation).

"The Order Flow Playbook" (Fabio Valentini / Carmine Rosato) asosida: uchala ustun
mos kelmaguncha BUY berilmaydi. Haqiqiy DOM/footprint ma'lumoti yo'q — shuning uchun
mavjud OHLCV + hajm + VAL/VAH/POC proksilaridan **deterministik** baholanadi.

Asosiy tushunchalar:
- Context (Kontekst): bozor "Qafas" (Balance/konsolidatsiya) yoki "Siqilish" (Squeeze/breakout) rejimidami.
- Location (Joylashuv): narx muhim darajada (qafas chekkasi / value chekkasi)mi yoki o'rtada (savdo qilma)mi.
- Confirmation (Tasdiq): Speed of Tape proksi (RVOL portlashi) + Initiative Candle (tashabbuskor sham) + Absorption yo'qligi.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _candle_ohlcv(c: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    return _f(c.get("o")), _f(c.get("h")), _f(c.get("l")), _f(c.get("c")), _f(c.get("v"))


def _consolidation_box(candles: List[Dict[str, Any]], lookback: int) -> Optional[Tuple[float, float]]:
    """Oxirgi sham(lar)dan oldingi `lookback` shamdan Qafas (Cage) yuqori/quyi chegarasi."""
    if len(candles) < lookback + 1:
        return None
    window = candles[-(lookback + 1):-1]  # oxirgi shamni chiqarib tashlaymiz (u breakout shami)
    highs = [_f(c.get("h")) for c in window]
    lows = [_f(c.get("l")) for c in window]
    if not highs or not lows:
        return None
    return (min(lows), max(highs))


def evaluate_order_flow(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Signalga CLC asosidagi Order Flow bahosini qo'shadi.

    Qaytadi: dict — clc_context/location/confirmation (bool), reasons, of_score,
    of_verdict (BUY/WATCH/AVOID), of_icon, va savdo izohi.
    """
    candles_raw = signal.get("candles")
    candles: List[Dict[str, Any]] = candles_raw if isinstance(candles_raw, list) else []
    price = _f(signal.get("price"))
    rvol = _f(signal.get("rvol"))

    lookback = int(_env_float("ORDERFLOW_CAGE_LOOKBACK", 10))
    min_rvol = _env_float("ORDERFLOW_MIN_RVOL", 1.8)
    min_body_frac = _env_float("ORDERFLOW_MIN_BODY_FRAC", 0.5)
    min_close_pos = _env_float("ORDERFLOW_MIN_CLOSE_POS", 0.6)

    reasons: List[str] = []

    # --- CONTEXT: Qafas (Cage) vs Siqilish (Squeeze) ---
    context_ok = False
    cage = _consolidation_box(candles, lookback) if candles else None
    last = candles[-1] if candles else None
    cage_high = cage[1] if cage else None
    cage_low = cage[0] if cage else None
    if last is not None and cage is not None:
        _o, _h, _l, c_close, _v = _candle_ohlcv(last)
        # Squeeze (BUY): narx qafas yuqorisidan tashqarida qabul qilingan (breakout up)
        if c_close > cage_high > 0:
            context_ok = True
            reasons.append("Siqilish: narx qafas tepasidan chiqdi (breakout)")
        elif cage_low <= c_close <= cage_high:
            reasons.append("Qafas o'rtasi — savdo qilmang (Balance)")
        else:
            reasons.append("Narx qafas ostida — long uchun mos emas")
    else:
        reasons.append("Kontekst aniqlanmadi (shamlar yetarli emas)")

    # --- LOCATION: muhim darajada (chekka)mi yoki o'rtadami ---
    location_ok = False
    val = signal.get("amt_val")
    vah = signal.get("amt_vah")
    poc = signal.get("amt_poc_proxy")
    if val is not None and vah is not None and price > 0:
        val_f, vah_f = _f(val), _f(vah)
        poc_f = _f(poc) if poc is not None else (val_f + vah_f) / 2
        # POC (o'rta) atrofida bo'lsa — yangi kirish emas
        band = abs(vah_f - val_f) or (price * 0.005)
        near_poc = abs(price - poc_f) <= band * 0.2
        if near_poc:
            reasons.append("POC (value o'rtasi) yaqinida — yangi BUY emas")
        elif price >= vah_f or (cage_high and price >= cage_high):
            location_ok = True
            reasons.append("VAH/qafas chekkasi ustida — breakout joylashuvi")
        elif price <= val_f * 1.01:
            location_ok = True
            reasons.append("VAL chekkasida — mean-reversion joylashuvi")
        else:
            reasons.append("Value o'rtasida — joylashuv kuchsiz")
    elif cage_high is not None and price > 0:
        # VAL/VAH yo'q — qafas chekkasiga tayanamiz
        if price >= cage_high:
            location_ok = True
            reasons.append("Qafas tepa chekkasida — breakout joylashuvi")
        else:
            reasons.append("Qafas o'rtasi/ostida — joylashuv kuchsiz")
    else:
        reasons.append("Joylashuv aniqlanmadi")

    # --- CONFIRMATION: Speed of Tape (RVOL) + Initiative Candle + Absorption yo'q ---
    confirmation_ok = False
    tape_ok = rvol >= min_rvol
    initiative_ok = False
    absorption_warn = False
    if last is not None:
        o, h, lo, c_close, v = _candle_ohlcv(last)
        rng = h - lo
        body = abs(c_close - o)
        if rng > 0:
            body_frac = body / rng
            close_pos = (c_close - lo) / rng  # 1 = tepada yopildi (kuchli buy)
            initiative_ok = c_close > o and body_frac >= min_body_frac and close_pos >= min_close_pos
            # Absorption: katta hajm (RVOL yuqori) lekin natija kichik (body kichik) + tepadan qaytgan
            if rvol >= min_rvol and body_frac < 0.3 and close_pos < 0.5:
                absorption_warn = True
    if tape_ok and initiative_ok and not absorption_warn:
        confirmation_ok = True
        reasons.append(f"Tasdiq: RVOL {rvol:.1f}× (tape) + Initiative Candle")
    else:
        if not tape_ok:
            reasons.append(f"Tape sust: RVOL {rvol:.1f}× < {min_rvol:.1f}")
        if not initiative_ok:
            reasons.append("Initiative Candle yo'q (kuchli yopilish emas)")
        if absorption_warn:
            reasons.append("⚠️ Absorption: katta hajm, kichik natija — reversal xavfi")

    pillars = [context_ok, location_ok, confirmation_ok]
    n_ok = sum(1 for p in pillars if p)
    of_score = int(round(n_ok / 3 * 100))

    if absorption_warn:
        verdict, icon = "AVOID", "⛔"
    elif n_ok == 3:
        verdict, icon = "BUY", "🟢"
    elif n_ok == 2:
        verdict, icon = "WATCH", "🟡"
    else:
        verdict, icon = "AVOID", "⛔"

    return {
        "clc_context": context_ok,
        "clc_location": location_ok,
        "clc_confirmation": confirmation_ok,
        "of_absorption_warn": absorption_warn,
        "of_pillars_ok": n_ok,
        "of_score": of_score,
        "of_verdict": verdict,
        "of_icon": icon,
        "of_reasons": reasons,
        "of_cage_low": cage_low,
        "of_cage_high": cage_high,
    }


def order_flow_badge(result: Dict[str, Any]) -> str:
    """Bir so'zli ikon+matn."""
    v = result.get("of_verdict", "AVOID")
    icon = result.get("of_icon", "⛔")
    label = {"BUY": "KIRISH", "WATCH": "KUTING", "AVOID": "O'TKAZ"}.get(v, "O'TKAZ")
    return f"{icon} {label}"


def format_order_flow_html(signal: Dict[str, Any], result: Dict[str, Any], *, ticker: str = "") -> str:
    """Order Flow CLC hisobotini HTML (Telegram)."""
    t = (ticker or signal.get("ticker") or "?").upper()
    badge = order_flow_badge(result)
    n_ok = result.get("of_pillars_ok", 0)
    score = result.get("of_score", 0)

    def _mark(ok: bool) -> str:
        return "✅" if ok else "❌"

    ctx = _mark(result.get("clc_context"))
    loc = _mark(result.get("clc_location"))
    con = _mark(result.get("clc_confirmation"))
    reasons = "\n".join(f"• {r}" for r in result.get("of_reasons", []))

    return (
        f"<b>Order Flow · {t}</b> — <b>{badge}</b> ({n_ok}/3 ustun, {score}%)\n"
        f"<b>CLC qoidasi:</b>\n"
        f"{ctx} <b>Context</b> — Qafas/Siqilish rejimi\n"
        f"{loc} <b>Location</b> — muhim daraja (chekka), o'rtada emas\n"
        f"{con} <b>Confirmation</b> — RVOL (tape) + Initiative Candle\n"
        f"<b>Tahlil:</b>\n{reasons}\n"
        f"<i>Qoida: uchala ustun ✅ bo'lmaguncha BUY bosmang. O'tmish — kafolat emas.</i>"
    )
