"""Skalping / day-trade uchun yagona kirish · SL · chiqish (TP1/TP2) darajalari.

Har bir signal uchun `trade_*` maydonlari va `trade_levels_line` (Telegram uchun) — AMT/VWAP,
strategiya SL/TP yoki ignition zonasidan deterministik hisoblanadi.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple


def _truthy(raw: str | None, *, default: bool) -> bool:
    s = (raw or "").strip().lower()
    if not s:
        return default
    if s in {"0", "false", "no", "off"}:
        return False
    return s in {"1", "true", "yes", "on"}


def _f4(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        if v != v:  # NaN
            return None
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _rr(entry: float, sl: float, tp: float) -> Optional[float]:
    if entry <= sl or tp <= entry:
        return None
    risk = entry - sl
    if risk <= 0:
        return None
    return round((tp - entry) / risk, 2)


def _levels_from_amt(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not bool(signal.get("amt_ok")):
        return None
    val = _f4(signal.get("amt_val"))
    poc = _f4(signal.get("amt_poc_proxy"))
    vah = _f4(signal.get("amt_vah"))
    price = _f4(signal.get("price"))
    if price is None or val is None or poc is None:
        return None
    # Long skalp: kirish — joriy narx yoki VAL ustida tasdiq
    entry = price
    buf = max(0.0005 * entry, 0.01)
    stop = _f4(val - buf)
    if stop is None or stop >= entry:
        stop = _f4(val * 0.998)
    if stop is None or stop >= entry:
        return None
    tp1 = poc if poc > entry else _f4(entry + (entry - stop))
    tp2 = vah if (vah is not None and vah > (tp1 or entry)) else None
    if tp1 is None:
        return None
    style = "scalp_amt"
    if bool(signal.get("amt_buy_signal")):
        entry_note = "VAL↑ yoki EMA9 qayta egallash (AMT BUY)"
    elif bool(signal.get("amt_tp_zone")):
        entry_note = "POC zonasida — yangi BUY emas, chiqish/trim"
        style = "scalp_amt_manage"
    else:
        entry_note = "Kuzatuv: VAL ostida SL, POC/VAH maqsad"
    exit_rule = (
        "Chiqish1: POC (VWAP proksi) · Chiqish2: VAH · "
        "SL: VAL ostida · Kun oxirida ochiq pozitsiyani yopish (day trade)"
    )
    return {
        "trade_setup_style": style,
        "trade_entry_price": entry,
        "trade_stop_loss": stop,
        "trade_tp1": tp1,
        "trade_tp2": tp2,
        "trade_entry_note": entry_note,
        "trade_exit_rule": exit_rule,
        "trade_rr_tp1": _rr(entry, stop, tp1),
        "trade_rr_tp2": _rr(entry, stop, tp2) if tp2 else None,
    }


def _levels_from_strategy(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    entry = _f4(signal.get("price"))
    sl = _f4(signal.get("stop_suggestion"))
    tp = _f4(signal.get("take_profit_suggestion"))
    if entry is None or sl is None or tp is None:
        return None
    if sl >= entry or tp <= entry:
        return None
    strat = str(signal.get("strategy_name") or "").lower()
    if "vwap" in strat:
        style = "day_vwap"
        note = "VWAP breakout — strategiya SL/TP"
    elif "ignition" in strat or signal.get("ignition_trend_stage"):
        style = "day_ignition"
        note = "Volume ignition — qarshilik / ATR stop"
    else:
        style = "day_strategy"
        note = "Strategiya SL/TP"
    lo = _f4(signal.get("ignition_entry_zone_low"))
    hi = _f4(signal.get("ignition_entry_zone_high"))
    if lo is not None and hi is not None and lo < entry < hi:
        note = f"Ignition zona {lo}–{hi}"
    return {
        "trade_setup_style": style,
        "trade_entry_price": entry,
        "trade_stop_loss": sl,
        "trade_tp1": tp,
        "trade_tp2": None,
        "trade_entry_note": note,
        "trade_exit_rule": "Maqsad: TP1 · SL darhol · Kunlik pozitsiyani yopish",
        "trade_rr_tp1": _rr(entry, sl, tp),
        "trade_rr_tp2": None,
    }


def compute_scalp_daytrade_levels(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Signalga `trade_*` maydonlarini qo‘shadi (mavjud signal nusxasi)."""

    out = dict(signal)
    pack: Optional[Dict[str, Any]] = None
    if _truthy(os.getenv("SCALP_LEVELS_PREFER_AMT"), default=True):
        pack = _levels_from_amt(signal) or _levels_from_strategy(signal)
    else:
        pack = _levels_from_strategy(signal) or _levels_from_amt(signal)

    if not pack:
        out["trade_levels_ok"] = False
        out["trade_levels_line"] = ""
        return out

    out.update(pack)
    out["trade_levels_ok"] = True

    e, sl, tp1, tp2 = (
        pack["trade_entry_price"],
        pack["trade_stop_loss"],
        pack["trade_tp1"],
        pack["trade_tp2"],
    )
    rr1 = pack.get("trade_rr_tp1")
    rr1s = f" R:R1≈{rr1}" if rr1 is not None else ""
    tp2s = f" | CHIQISH2 {tp2}" if tp2 is not None else ""
    out["trade_levels_line"] = (
        f"KIRISH {e} | SL {sl} | CHIQISH1 {tp1}{tp2s}{rr1s}"
    )

    if _truthy(os.getenv("SCALP_FILL_MISSING_SL_TP"), default=True):
        if out.get("stop_suggestion") is None:
            out["stop_suggestion"] = sl
        if out.get("take_profit_suggestion") is None:
            out["take_profit_suggestion"] = tp1

    return out


def maybe_attach_scalp_daytrade_levels(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not _truthy(os.getenv("SCALP_DAYTRADE_LEVELS_ENABLED"), default=True):
        return signal
    return compute_scalp_daytrade_levels(signal)
