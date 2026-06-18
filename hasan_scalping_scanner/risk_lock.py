"""risk_lock.py — prop-uslub himoya: emotsional/qasos/ortiqcha savdodan saqlaydi.

Bu modul savdoga RUXSAT bor-yo'qligini hal qiladi. STOP_TRADING chiqsa — bugun
yangi setup ko'rsatilmaydi (faqat ogohlantirish). HECH qanday order yo'q.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from . import config


@dataclass
class RiskState:
    """Kun davomidagi savdo holati (foydalanuvchi yoki paper-log to'ldiradi)."""

    trades_today: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    # Emotsional holat bayroqlari (sidebar checkboxlaridan)
    feeling_tired: bool = False
    feeling_emotional: bool = False
    feeling_angry: bool = False
    feeling_confused: bool = False
    wants_to_recover_losses: bool = False
    extra_flags: List[str] = field(default_factory=list)


def evaluate_risk_lock(state: RiskState) -> Tuple[bool, str, List[str]]:
    """Savdoga ruxsatmi? -> (allowed, status, sabablar).

    status: "OK" yoki "STOP_TRADING". Bitta qattiq sabab ham bo'lsa — STOP.
    """
    reasons: List[str] = []

    # --- Qattiq to'xtash sabablari ---
    if state.daily_pnl <= config.DAILY_HARD_STOP:
        reasons.append(f"Qattiq stop: kunlik P&L {state.daily_pnl:.0f}$ <= {config.DAILY_HARD_STOP:.0f}$")
    if state.daily_pnl <= config.DAILY_SOFT_STOP:
        reasons.append(f"Yumshoq stop: kunlik P&L {state.daily_pnl:.0f}$ <= {config.DAILY_SOFT_STOP:.0f}$")
    if state.trades_today >= config.MAX_TRADES_PER_DAY:
        reasons.append(f"Kunlik limit: {state.trades_today}/{config.MAX_TRADES_PER_DAY} savdo bajarildi")
    if state.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
        reasons.append(f"Ketma-ket {state.consecutive_losses} zarar — to'xtang")

    # --- Emotsional/psixologik sabablar ---
    if state.wants_to_recover_losses:
        reasons.append("Zararni qoplash istagi (revenge trading) — TO'XTANG")
    if state.feeling_tired:
        reasons.append("Charchagansiz — to'xtang")
    if state.feeling_emotional:
        reasons.append("Emotsional holat — to'xtang")
    if state.feeling_angry:
        reasons.append("Jahl/asabiy — to'xtang")
    if state.feeling_confused:
        reasons.append("Chalkash/ishonchsiz — to'xtang")
    reasons.extend(state.extra_flags)

    if reasons:
        return False, "STOP_TRADING", reasons
    return True, "OK", ["Risk-lock toza — manual review uchun ruxsat (order EMAS)"]


def remaining_trades(state: RiskState) -> int:
    """Bugun yana nechta savdoga ruxsat (limit ichida)."""
    return max(0, config.MAX_TRADES_PER_DAY - state.trades_today)


def risk_budget_line(state: RiskState) -> str:
    """Sidebar/asosiy panel uchun qisqa risk holati qatori."""
    return (
        f"Savdolar: {state.trades_today}/{config.MAX_TRADES_PER_DAY} · "
        f"Ketma-ket zarar: {state.consecutive_losses}/{config.MAX_CONSECUTIVE_LOSSES} · "
        f"Kunlik P&L: {state.daily_pnl:.0f}$ "
        f"(soft {config.DAILY_SOFT_STOP:.0f}$ / hard {config.DAILY_HARD_STOP:.0f}$)"
    )


def build_alert_text(signal: dict) -> str:
    """PAPER_READY signal uchun ogohlantirish matni (Telegram uchun tayyor, hali yuborilmaydi)."""
    return (
        "🚨 HASAN SCALPING SIGNAL\n\n"
        f"Ticker: {signal.get('ticker', '?')}\n"
        f"Price: {signal.get('price', '—')}\n"
        f"Decision: {signal.get('decision', '—')}\n"
        f"Score: {signal.get('score', '—')}/10\n"
        f"Setup: VWAP Reclaim + Volume-Time Confirmation\n"
        f"Entry idea: {signal.get('entry', '—')}\n"
        f"Stop-loss: {signal.get('stop_loss', '—')}\n"
        f"Target 1: {signal.get('target1', '—')}\n"
        f"Target 2: {signal.get('target2', '—')}\n"
        f"Risk/Reward: {signal.get('risk_reward', '—')}\n"
        f"Reason: {signal.get('reason', '—')}\n"
        f"Warning: {signal.get('mistake_warning', '—')}\n\n"
        "⚠️ Bu AVTOMATIK BUY EMAS — faqat manual review (paper)."
    )


def send_telegram_alert_placeholder(signal: dict) -> bool:
    """Kelajak uchun joy: Telegram alert. HOZIR HECH NIMA YUBORMAYDI.

    Keyinroq bu yerga bot token + chat_id bilan haqiqiy yuborish qo'shiladi.
    Hozircha faqat matnni tayyorlaydi va False qaytaradi (yuborilmadi).
    """
    _ = build_alert_text(signal)  # matn tayyor
    return False  # ataylab: V1 da yuborilmaydi
