"""Streamlit dan mustaqil skan konveyeri — Telegram / boshqa ishlovchilar uchun."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agents.alpaca_paper_trading_agent import AlpacaPaperTradingAgent
from agents.chatgpt_analyst_agent import ChatGPTAnalystAgent
from agents.email_alerts_agent import EmailAlertsAgent
from agents.logger_agent import LoggerAgent
from agents.market_data_agent import MarketDataAgent
from agents.risk_manager_agent import RiskManagerAgent
from agents.rvol_agent import RVOLAgent
from agents.scan_presets import SCAN_PRESETS
from agents.strategy_agent import StrategyAgent
from agents.strategy_factory import resolve_strategy_mode, run_stage_one_strategy
from agents.strategy_volume_ignition import VolumeIgnitionStrategyAgent
from agents.strategy_vwap_breakout import VwapBreakoutStrategyAgent
from agents.telegram_alerts_agent import TelegramAlertsAgent
from agents.universe_agent import UniverseAgent


def _intraday_strategy_mode(mode: str) -> bool:
    return mode.strip().lower() in {"vwap_breakout", "mtrade_high_volatility"}


def _strategy_fallback_name(mode: str) -> str:
    m = mode.strip().lower()
    if m == "mtrade_high_volatility":
        return "mtrade_high_volatility"
    if _intraday_strategy_mode(m):
        return "vwap_breakout"
    if m == "volume_ignition":
        return "volume_ignition_scan"
    return "rvol_momentum"


__all__ = [
    "SidebarControls",
    "build_scan_agents",
    "telegram_default_controls",
    "fetch_universe_for_scan",
    "run_scan_market",
]


@dataclass
class SidebarControls:
    desk_label: str
    max_symbols: int
    preset_name: str
    rvol_thresholds: Dict[str, float]
    max_workers: int
    finviz_csv_universe: bool


def _env_int_bounded(name: str, default: int, lo: int, hi: int) -> int:
    """Butun son .env; noto‘g‘ri yoki bo‘sh bo‘lsa default."""

    raw = os.getenv(name, "")
    if not str(raw).strip():
        v = default
    else:
        try:
            v = int(str(raw).strip(), 10)
        except ValueError:
            v = default
    return max(lo, min(hi, v))


def _email_or_telegram_top_n_for_alerts() -> int:
    """Alert uchun TOP N: EMAIL_ALERT_TOP_N bo‘lsa u, yo‘q bo‘lsa TELEGRAM_ALERT_TOP_N."""

    raw = os.getenv("EMAIL_ALERT_TOP_N", "").strip()
    if raw:
        try:
            v = int(raw, 10)
        except ValueError:
            v = 3
        return max(1, min(50, v))
    return _env_int_bounded("TELEGRAM_ALERT_TOP_N", 3, 1, 50)


def build_scan_agents(repo_root: Path) -> Dict[str, Any]:
    logs = repo_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return {
        "universe": UniverseAgent(),
        "market_data": MarketDataAgent(),
        "rvol": RVOLAgent(),
        "strategy": StrategyAgent(),
        "analyst": ChatGPTAnalystAgent(),
        "risk": RiskManagerAgent(trades_log_path=str(logs / "trades.csv"), repo_root=repo_root),
        "trader": AlpacaPaperTradingAgent(),
        "logger": LoggerAgent(logs_dir=str(logs)),
    }


def run_scan_market(
    tickers: List[str],
    controls: SidebarControls,
    *,
    repo_root: Path,
    progress: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Streamlit progress obyektini `progress` bilan berishingiz mumkin (`.progress`, `.empty`); aks holda None."""

    agents = build_scan_agents(repo_root)
    signals: List[Dict[str, Any]] = []
    full_scan_logs: List[Dict[str, Any]] = []
    full_scan_views: List[Dict[str, Any]] = []

    scanned = len(tickers)
    strategy_mode = resolve_strategy_mode()

    rvol_strategy = StrategyAgent()
    vwap_strategy = VwapBreakoutStrategyAgent()
    ignition_strategy = VolumeIgnitionStrategyAgent()

    def stage_one(symbol: str) -> Tuple[str, Dict[str, Any]]:
        try:
            market_data = agents["market_data"].fetch_market_data(symbol)
            base_snapshot = agents["rvol"].calculate(market_data)
            signal = run_stage_one_strategy(
                strategy_mode,
                market_data=agents["market_data"],
                rvol_snapshot=base_snapshot,
                rvol_thresholds=controls.rvol_thresholds,
                rvol_strategy=rvol_strategy,
                vwap_strategy=vwap_strategy,
                ignition_strategy=ignition_strategy,
            )
            return symbol, signal
        except Exception:
            fallback = {
                "ticker": symbol,
                "strategy_pass": False,
                "failed_rules": ["fetch_error"],
                "score": 0,
                "price": 0.0,
                "change_percent": 0.0,
                "volume": 0,
                "avg_volume": 0,
                "rvol": 0.0,
                "data_delay": f"{agents['market_data'].data_delay_minutes}-minute delayed",
                "updated_time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "strategy_name": _strategy_fallback_name(strategy_mode),
            }
            return symbol, fallback

    def _prog(frac: float, text: str) -> None:
        if progress is not None:
            progress.progress(frac, text=text)

    _prog(0.0, "Stage 1 · fetching symbols…")
    results: Dict[str, Dict[str, Any]] = {}
    max_workers = max(2, int(controls.max_workers))
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(stage_one, symbol): symbol for symbol in tickers}
        for future in as_completed(futures):
            symbol, signal = future.result()
            results[symbol] = signal
            completed += 1
            _prog(completed / max(len(tickers), 1), f"Stage 1 · {completed}/{len(tickers)} tickers prepared")

    _prog(1.0, "Stage 2 · running ChatGPT on passes…")

    for symbol in tickers:
        signal = results[symbol]
        analyst_decision = ""
        analyst_reason = ""
        risk_level_value = ""
        chatgpt_allow = False

        if signal.get("strategy_pass"):
            analyst_view = agents["analyst"].analyze(signal)
            lineage = {
                "strategy_name": signal.get("strategy_name"),
                "daily_bar_ts": signal.get("daily_bar_timestamp_ms"),
                "daily_ema_9": signal.get("daily_ema_9"),
                "daily_rsi_14": signal.get("daily_rsi_14"),
                "daily_atr_14": signal.get("daily_atr_14"),
                "session_vwap": signal.get("session_vwap"),
                "rsi_14": signal.get("rsi_14"),
                "atr_14": signal.get("atr_14"),
                "ignition_trend_stage": signal.get("ignition_trend_stage"),
                "ignition_distance_to_resistance_pct": signal.get("ignition_distance_to_resistance_pct"),
                "volume_pattern_summary": signal.get("volume_pattern_summary"),
                "ignition_continuation_probability": signal.get("ignition_continuation_probability"),
            }
            signal.update(
                {
                    "chatgpt_decision": analyst_view["decision"],
                    "chatgpt_confidence": analyst_view["confidence"],
                    "chatgpt_reason": analyst_view["reason"],
                    "risk_level": analyst_view["risk_level"],
                    "chatgpt_allow_order": analyst_view["allow_order"],
                    "chatgpt_risk_flags_json": json.dumps(analyst_view.get("risk_flags") or []),
                    "chatgpt_risk_flags_hard_json": json.dumps(analyst_view.get("risk_flags_hard") or []),
                    "chatgpt_entry_condition": analyst_view.get("entry_condition", ""),
                    "paper_ready_blocked_field": analyst_view.get("paper_ready_blocked"),
                    "indicator_lineage_json": json.dumps(lineage, default=str),
                }
            )
            analyst_decision = analyst_view["decision"]
            risk_level_value = analyst_view["risk_level"]
            chatgpt_allow = bool(analyst_view["allow_order"])
            signals.append(signal)

        failed_rules = ",".join(signal.get("failed_rules") or [])

        full_scan_logs.append(
            {
                "ticker": signal.get("ticker"),
                "strategy_name": signal.get("strategy_name"),
                "price": signal.get("price"),
                "change_percent": signal.get("change_percent"),
                "volume": signal.get("volume"),
                "avg_volume": signal.get("avg_volume"),
                "rvol": signal.get("rvol"),
                "session_vwap": signal.get("session_vwap"),
                "rsi_14": signal.get("rsi_14"),
                "atr_14": signal.get("atr_14"),
                "vwap_cross": signal.get("vwap_cross"),
                "take_profit_suggestion": signal.get("take_profit_suggestion"),
                "stop_suggestion": signal.get("stop_suggestion"),
                "score": signal.get("score"),
                "strategy_pass": signal.get("strategy_pass"),
                "failed_rules": failed_rules,
                "chatgpt_decision": analyst_decision,
                "chatgpt_risk_flags": signal.get("chatgpt_risk_flags_json", "[]"),
                "chatgpt_flags_hard": signal.get("chatgpt_risk_flags_hard_json", "[]"),
                "chatgpt_entry_condition": signal.get("chatgpt_entry_condition", ""),
                "indicator_lineage_json": signal.get("indicator_lineage_json", ""),
                "risk_level": risk_level_value,
                "chatgpt_allow_order": chatgpt_allow,
                "data_delay": signal.get("data_delay"),
                "updated_time": signal.get("updated_time"),
            }
        )

        full_scan_views.append(
            {
                "Ticker": signal.get("ticker"),
                "Strategy": signal.get("strategy_name"),
                "Price": signal.get("price"),
                "Change %": signal.get("change_percent"),
                "Volume": signal.get("volume"),
                "Avg Volume": signal.get("avg_volume"),
                "RVOL": signal.get("rvol"),
                "VWAP": signal.get("session_vwap"),
                "RSI": signal.get("rsi_14"),
                "ATR": signal.get("atr_14"),
                "Latest cross": signal.get("vwap_cross"),
                "Strategy Pass": "Yes" if signal.get("strategy_pass") else "No",
                "Failed Rules": failed_rules if failed_rules else "—",
                "Score": signal.get("score"),
                "TP idea": signal.get("take_profit_suggestion"),
                "SL idea": signal.get("stop_suggestion"),
                "Ign Stage": signal.get("ignition_trend_stage"),
                "Ign R dist%": signal.get("ignition_distance_to_resistance_pct"),
                "ChatGPT Decision": analyst_decision or "—",
                "Risk Level": risk_level_value or "—",
                "Data Delay": signal.get("data_delay"),
                "Updated Time": signal.get("updated_time"),
            }
        )

    if progress is not None and hasattr(progress, "empty"):
        progress.empty()

    agents["logger"].save_signals(signals)
    agents["logger"].save_full_scan(full_scan_logs)
    ranked_signals = sorted(signals, key=lambda item: item.get("score", 0), reverse=True)

    if os.getenv("TELEGRAM_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}:
        tg = TelegramAlertsAgent()
        tg.notify_scan_summary(
            {
                "tickers_scanned": scanned,
                "eligible_signals": len(signals),
                "strategy_mode": strategy_mode,
            }
        )
        tg.notify_signals(ranked_signals, max_items=_env_int_bounded("TELEGRAM_ALERT_TOP_N", 3, 1, 50))

    mail_on = os.getenv("EMAIL_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
    mail_en = os.getenv("EMAIL_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    if mail_on or mail_en:
        em = EmailAlertsAgent()
        em.notify_scan_summary(
            {
                "tickers_scanned": scanned,
                "eligible_signals": len(signals),
                "strategy_mode": strategy_mode,
            }
        )
        em.notify_signals(ranked_signals, max_items=_email_or_telegram_top_n_for_alerts())

    summary = {
        "tickers_scanned": scanned,
        "eligible_signals": len(signals),
        "failed_signals": scanned - len(signals),
        "symbols_input": scanned,
        "strategy_mode": strategy_mode,
        "scan_preset": controls.preset_name,
        "parallel_workers": controls.max_workers,
        "rvol_thresholds": controls.rvol_thresholds,
        "desk_label": controls.desk_label,
    }
    return ranked_signals, full_scan_views, summary


def telegram_default_controls() -> SidebarControls:
    """Telegram `/scan` uchun .env asosidagi sukutlar."""

    preset = os.getenv("TELEGRAM_SCAN_PRESET", "Balanced").strip()
    if preset not in SCAN_PRESETS:
        preset = "Balanced"
    return SidebarControls(
        desk_label=os.getenv("TELEGRAM_DESK_LABEL", "TG scan").strip() or "TG scan",
        max_symbols=_env_int_bounded("TELEGRAM_MAX_SYMBOLS", 80, 10, 400),
        preset_name=preset,
        rvol_thresholds=dict(SCAN_PRESETS[preset]),
        max_workers=_env_int_bounded("SCAN_MAX_WORKERS", 10, 2, 20),
        finviz_csv_universe=os.getenv("TELEGRAM_USE_FINVIZ_CSV", "").strip().lower() in {"1", "true", "yes", "on"},
    )


def fetch_universe_for_scan(controls: SidebarControls) -> List[str]:
    use_finviz = controls.finviz_csv_universe or os.getenv("FETCH_UNIVERSE_FINVIZ_FIRST", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return list(UniverseAgent().fetch_symbols(limit=controls.max_symbols, use_finviz_elite=use_finviz))
