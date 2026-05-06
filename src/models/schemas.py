from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Bar(BaseModel):
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    source: Literal["alpaca", "polygon", "yahoo", "finnhub"] = "alpaca"


Decision = Literal["NO_SIGNAL", "WATCHLIST", "PAPER_READY", "LIVE_PENDING_APPROVAL"]
SetupType = Literal["volume_ignition_breakout", "pullback_continuation", "none"]


class SignalCandidate(BaseModel):
    """AI / rule engine chiqishi mumkin bo‘lgan signal (MASTER_PLAN bilan mos)."""

    symbol: str
    side: Literal["buy", "sell", "hold"] = "buy"
    setup: SetupType = "none"
    score: float = Field(default=0.0, ge=0, le=100)
    entry: float
    stop: float
    tp1: float
    tp2: float
    rr: float
    probability: float = Field(default=0.0, ge=0, le=100)
    decision: Decision = "NO_SIGNAL"
    catalyst: str = ""
    technical_summary: str = ""
    rejection_reason: Optional[str] = None
    human_confirmation_required: bool = True
    reasons: list[str] = Field(default_factory=list)


class OrderIntent(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    qty: int
    order_type: Literal["market", "limit", "bracket"] = "bracket"
    limit_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    time_in_force: str = "day"


class HalalReport(BaseModel):
    symbol: str
    status: Literal["compliant", "non_compliant", "questionable", "unknown"]
    source: Literal["zoya", "cache", "manual", "fallback"] = "fallback"
    detail: str = ""
    debt_ratio: Optional[float] = None
    impure_revenue_pct: Optional[float] = None
