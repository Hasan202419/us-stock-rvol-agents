"""risk_lock.py — prop himoya: emotsional/qasos/ortiqcha savdodan saqlaydi.

Savdoga RUXSAT bor-yo'qligini hal qiladi. STOP_TRADING bo'lsa yangi signal yuborilmaydi.
Hech qanday order yo'q.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from . import config


@dataclass
class RiskState:
    """Kun davomidagi savdo holati."""

    trades_today: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    feeling_tired: bool = False
    feeling_emotional: bool = False
    feeling_angry: bool = False
    feeling_confused: bool = False
    wants_to_recover_losses: bool = False
    extra_flags: List[str] = field(default_factory=list)


def evaluate_risk_lock(state: RiskState) -> Tuple[bool, str, List[str]]:
    """Savdoga ruxsatmi? -> (allowed, status, sabablar). status: OK / STOP_TRADING."""
    reasons: List[str] = []

    if state.daily_pnl <= config.DAILY_HARD_STOP:
        reasons.append(f"Qattiq stop: P&L {state.daily_pnl:.0f}$ <= {config.DAILY_HARD_STOP:.0f}$")
    if state.daily_pnl <= config.DAILY_SOFT_STOP:
        reasons.append(f"Yumshoq stop: P&L {state.daily_pnl:.0f}$ <= {config.DAILY_SOFT_STOP:.0f}$")
    if state.trades_today >= config.MAX_TRADES_PER_DAY:
        reasons.append(f"Kunlik limit: {state.trades_today}/{config.MAX_TRADES_PER_DAY}")
    if state.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
        reasons.append(f"Ketma-ket {state.consecutive_losses} zarar — to'xtang")

    if state.wants_to_recover_losses:
        reasons.append("Zararni qoplash istagi (revenge) — TO'XTANG")
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
    return True, "OK", ["Risk-lock toza (order EMAS, faqat signal)"]


def remaining_trades(state: RiskState) -> int:
    return max(0, config.MAX_TRADES_PER_DAY - state.trades_today)


def risk_budget_line(state: RiskState) -> str:
    return (
        f"Savdolar {state.trades_today}/{config.MAX_TRADES_PER_DAY} · "
        f"ketma-ket zarar {state.consecutive_losses}/{config.MAX_CONSECUTIVE_LOSSES} · "
        f"P&L {state.daily_pnl:.0f}$ (soft {config.DAILY_SOFT_STOP:.0f}/hard {config.DAILY_HARD_STOP:.0f})"
    )
