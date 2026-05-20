"""Savdoga kirish uchun aniq signal — KIRISH / KUTING / O‘TKAZISH."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Tuple


class TradeAction(str, Enum):
    ENTER = "ENTER"
    WAIT = "WAIT"
    SKIP = "SKIP"


def _f(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def _min_rr() -> float:
    try:
        return max(1.0, float(os.getenv("MIN_RISK_REWARD_RATIO", "2.0")))
    except ValueError:
        return 2.0


def _truthy(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def classify_trade_action(row: Dict[str, Any]) -> Tuple[TradeAction, str]:
    """Bitta ticker uchun savdo qarori va qisqa sabab (o‘zbekcha)."""

    if row.get("watchlist_only"):
        return TradeAction.SKIP, "Strategiya filtridan o‘tmagan — kuzatuv emas savdo"

    regime = str(row.get("market_regime") or "").upper()
    if regime == "NEWS_LOCK":
        return TradeAction.SKIP, "Yangiliklar qulfi — yangi long ochmang"
    if regime == "RISK_OFF":
        return TradeAction.SKIP, "Bozor RISK_OFF — long tavsiya etilmaydi"

    block = str(row.get("market_shield_block_reason") or row.get("paper_trade_block_reason") or "").strip()
    if block and "shield" in block.lower():
        return TradeAction.SKIP, block[:120]

    price = _f(row, "price")
    if price <= 0:
        return TradeAction.SKIP, "Narx yo‘q — ma’lumot xato"

    if not bool(row.get("trade_levels_ok")):
        return TradeAction.WAIT, "KIRISH/SL/CHIQISH hisoblanmadi — hali tayyor emas"

    style = str(row.get("trade_setup_style") or "")
    if style == "scalp_amt_manage" or bool(row.get("amt_tp_zone")):
        return TradeAction.WAIT, "POC/VAH zonasi — yangi kirish emas, chiqish/trim"

    rr = row.get("trade_rr_tp1")
    rr_f: float | None
    try:
        rr_f = float(rr) if rr is not None else None
    except (TypeError, ValueError):
        rr_f = None

    min_rr = _min_rr()
    # Scalp uchun biroz yumshoq (lekin kamida 1.2R)
    scalp_min = max(1.2, min_rr * 0.85)

    aligned = int(row.get("mtf_alignment_count") or 0)
    total = int(row.get("mtf_alignment_total") or 0)
    mtf_full = total >= 2 and aligned == total
    require_mtf = _truthy("TRADE_ACTIONABLE_REQUIRE_MTF_FULL", default=False)

    dec = str(row.get("chatgpt_decision") or "").upper()
    if dec in {"SELL", "AVOID", "PASS"}:
        return TradeAction.SKIP, f"AI: {dec} — long kirish mos emas"

    if bool(row.get("amt_buy_signal")):
        if rr_f is not None and rr_f < scalp_min:
            return TradeAction.WAIT, f"AMT BUY bor, lekin R:R past ({rr_f:.1f} < {scalp_min:.1f})"
        if require_mtf and not mtf_full:
            return TradeAction.WAIT, f"AMT BUY — MTF to‘liq emas ({aligned}/{total})"
        note = str(row.get("trade_entry_note") or "VAL↑ / EMA9")
        return TradeAction.ENTER, f"AMT BUY · {note}"

    if bool(row.get("strategy_pass")) and rr_f is not None and rr_f >= min_rr:
        if require_mtf and total > 0 and not mtf_full:
            return TradeAction.WAIT, f"Signal bor — MTF kuting ({aligned}/{total})"
        return TradeAction.ENTER, "Strategiya pass + R:R maqbul"

    if mtf_full and rr_f is not None and rr_f >= scalp_min:
        return TradeAction.WAIT, "MTF mos — AMT BUY yoki pass kuting"

    if bool(row.get("strategy_pass")):
        return TradeAction.WAIT, "Pass bor, lekin R:R yoki darajalar yetarli emas"

    return TradeAction.SKIP, "Aniq kirish sharti bajarilmagan"


def action_badge(row: Dict[str, Any]) -> str:
    act, _ = classify_trade_action(row)
    if act == TradeAction.ENTER:
        return "✅ KIRISH"
    if act == TradeAction.WAIT:
        return "⏳ KUTING"
    return "⛔ O‘TKAZ"


def partition_by_action(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    enter: list[Dict[str, Any]] = []
    wait: list[Dict[str, Any]] = []
    skip: list[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        act, _ = classify_trade_action(r)
        if act == TradeAction.ENTER:
            enter.append(r)
        elif act == TradeAction.WAIT:
            wait.append(r)
        else:
            skip.append(r)
    return enter, wait, skip


def filter_actionable_entries(rows: List[Dict[str, Any]], *, max_wait: int = 5) -> List[Dict[str, Any]]:
    """Telegram ro‘yxati: avval KIRISH, keyin cheklangan KUTING."""

    enter, wait, _skip = partition_by_action(rows)
    if enter:
        return enter + wait[: max(0, max_wait)]
    if wait:
        return wait[: max(8, max_wait)]
    return rows[:8]
