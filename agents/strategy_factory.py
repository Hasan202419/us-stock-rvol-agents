"""STRATEGY_MODE bo‘yicha deterministik strategiyani tanlash (dashboard uchun)."""

from __future__ import annotations

import os
from typing import Any, Dict

from agents.market_data_agent import MarketDataAgent
from agents.strategy_agent import StrategyAgent
from agents.strategy_volume_ignition import VolumeIgnitionStrategyAgent
from agents.strategy_vwap_breakout import VwapBreakoutStrategyAgent


def resolve_strategy_mode(raw: str | None = None) -> str:
    mode = (raw or os.getenv("STRATEGY_MODE", "rvol")).strip().lower()
    allowed = {"rvol", "vwap_breakout", "mtrade_high_volatility", "volume_ignition"}
    return mode if mode in allowed else "rvol"


def run_stage_one_strategy(
    strategy_mode: str,
    *,
    market_data: MarketDataAgent,
    rvol_snapshot: Dict[str, Any],
    rvol_thresholds: Dict[str, Any],
    rvol_strategy: StrategyAgent | None = None,
    vwap_strategy: VwapBreakoutStrategyAgent | None = None,
    ignition_strategy: VolumeIgnitionStrategyAgent | None = None,
) -> Dict[str, Any]:
    if strategy_mode in {"vwap_breakout", "mtrade_high_volatility"}:
        agent = vwap_strategy or VwapBreakoutStrategyAgent()
        tf = int(os.getenv("INTRADAY_TIMEFRAME_MINUTES", "5"))
        bars = market_data.fetch_intraday_bars(rvol_snapshot.get("ticker", ""), timeframe_minutes=tf)
        return agent.evaluate(rvol_snapshot, bars)

    if strategy_mode == "volume_ignition":
        agent = ignition_strategy or VolumeIgnitionStrategyAgent()
        return agent.evaluate(rvol_snapshot, rvol_thresholds)

    agent = rvol_strategy or StrategyAgent()
    return agent.evaluate(rvol_snapshot, rvol_thresholds)
