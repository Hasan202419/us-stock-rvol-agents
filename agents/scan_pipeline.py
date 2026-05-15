"""Streamlit dan mustaqil skan konveyeri — Telegram / boshqa ishlovchilar uchun."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
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
from agents.telegram_amt_buy import amt_buy_alert_enabled, collect_amt_buy_signals
from agents.universe_agent import FALLBACK_US_EQUITIES, UniverseAgent
from src.modules.halal_gate import apply_halal_gate, halal_report_to_dict
from src.providers.zoya_client import fetch_zoya_compliance

_log = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Rank/alert uchun: score 'abc' bo‘lsa ham skan yiqilmasin."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _noop_attach_mtf(market_data: Any, ticker: str, signal: Dict[str, Any]) -> Dict[str, Any]:
    return signal


def _noop_attach_amt(market_data: Any, ticker: str, signal: Dict[str, Any]) -> Dict[str, Any]:
    return signal


def _noop_attach_scalp(signal: Dict[str, Any]) -> Dict[str, Any]:
    return signal


try:
    from agents.mtf_snapshot import maybe_attach_mtf_snapshot as _maybe_attach_mtf_snapshot
except ImportError as exc:
    _log.warning("mtf_snapshot unavailable, MTF attach disabled: %s", exc)
    _maybe_attach_mtf_snapshot = _noop_attach_mtf  # type: ignore[assignment]

try:
    from agents.amt_vwap_scalp import maybe_attach_amt_snapshot as _maybe_attach_amt_snapshot
except ImportError as exc:
    _log.warning("amt_vwap_scalp unavailable, AMT attach disabled: %s", exc)
    _maybe_attach_amt_snapshot = _noop_attach_amt  # type: ignore[assignment]

try:
    from agents.scalp_daytrade_levels import maybe_attach_scalp_daytrade_levels as _maybe_attach_scalp_daytrade_levels
except ImportError as exc:
    _log.warning("scalp_daytrade_levels unavailable, scalp levels disabled: %s", exc)
    _maybe_attach_scalp_daytrade_levels = _noop_attach_scalp  # type: ignore[assignment]


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


def _env_truthy_scan(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_truthy_scan_default(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _apply_halal_filter_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Signalga Zoya/halal gate qo'llaydi; non-compliant bo'lsa strategy passni bloklaydi."""

    symbol = str(signal.get("ticker") or "").strip().upper()
    if not symbol:
        return signal

    try:
        zoya_report = fetch_zoya_compliance(symbol)
        halal_ok, halal_reasons = apply_halal_gate(zoya_report, ratios=None)
        signal["halal_report"] = halal_report_to_dict(zoya_report)
        signal["halal_ok"] = bool(halal_ok)
        signal["halal_reasons"] = list(halal_reasons or [])
        if not halal_ok:
            signal["strategy_pass"] = False
            failed_rules = list(signal.get("failed_rules") or [])
            if "halal_non_compliant" not in failed_rules:
                failed_rules.append("halal_non_compliant")
            signal["failed_rules"] = failed_rules
    except Exception as exc:  # noqa: BLE001
        failed_rules = list(signal.get("failed_rules") or [])
        if "halal_check_error" not in failed_rules:
            failed_rules.append("halal_check_error")
        signal["failed_rules"] = failed_rules
        signal["halal_ok"] = False
        signal["halal_reasons"] = [f"Halal check error: {type(exc).__name__}"]
    return signal


def _apply_analyst_fields(
    signal: Dict[str, Any],
    analyst_view: Dict[str, Any],
    *,
    strategy_passed: bool,
) -> Tuple[str, str, bool, bool, str]:
    """LLM javoblarini signalga yozadi; strategy o'tmagan qatorlarda paper trade doim blok."""

    hard_flags = [str(x) for x in (analyst_view.get("risk_flags_hard") or []) if str(x).strip()]
    paper_block = analyst_view.get("paper_ready_blocked")

    paper_trade_ready = False
    paper_trade_block_reason = ""

    if strategy_passed:
        paper_trade_ready = bool(
            analyst_view.get("allow_order")
            and analyst_view.get("decision") in {"WATCH", "STRONG_WATCH"}
            and not hard_flags
            and not paper_block
        )
        if not paper_trade_ready:
            if paper_block:
                paper_trade_block_reason = f"PAPER readiness blocked: {paper_block}"
            elif hard_flags:
                paper_trade_block_reason = f"Hard AI risk_flags: {'; '.join(hard_flags)}"
            elif analyst_view.get("decision") not in {"WATCH", "STRONG_WATCH"}:
                paper_trade_block_reason = f"AI decision: {analyst_view.get('decision')}"
            else:
                paper_trade_block_reason = "AI analyst did not allow this setup for consideration."
    else:
        paper_trade_block_reason = "Strategy Pass: Yo'q — LLM fikri faqat fon (paper trade yo'q)."

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
            "chatgpt_trade_plan_json": json.dumps(analyst_view.get("trade_plan") or {}),
            "analyst_trade_plan_text": str(analyst_view.get("analyst_trade_plan_text") or "").strip(),
            "paper_ready_blocked_field": analyst_view.get("paper_ready_blocked"),
            "paper_trade_ready": paper_trade_ready,
            "paper_trade_block_reason": paper_trade_block_reason,
            "indicator_lineage_json": json.dumps(lineage, default=str),
        }
    )
    return (
        str(analyst_view.get("decision") or ""),
        str(analyst_view.get("risk_level") or ""),
        bool(analyst_view.get("allow_order")),
        paper_trade_ready,
        paper_trade_block_reason,
    )


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
    """Streamlit progress obyektini `progress` bilan berishingiz mumkin (`.progress`, `.empty`); aks holda None.

    `SCAN_AI_INCLUDE_FAILS=true` bo'lsa, strategiya o'tmagan qatorlar uchun ham LLM chaqiriladi
    (faqat to'liq skan jadvali / log; asosiy `signals` ro'yxati hanuz faqat pass qatorlar).
    """

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
            signal = _apply_halal_filter_to_signal(signal)
            signal = _maybe_attach_mtf_snapshot(agents["market_data"], symbol, signal)
            signal = _maybe_attach_amt_snapshot(agents["market_data"], symbol, signal)
            signal = _maybe_attach_scalp_daytrade_levels(signal)
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

    relaxed_fallback_enabled = _env_truthy_scan_default("SCAN_RELAX_ON_EMPTY", True)
    relaxed_fallback_applied = False
    if (
        relaxed_fallback_enabled
        and results
        and hasattr(rvol_strategy, "evaluate")
        and not any(bool(item.get("strategy_pass")) for item in results.values())
    ):
        # Intraday/strict kunlarda bo'sh jadval chiqmasin: Explorer + yumshoq change bilan RVOL fallback.
        relaxed_thresholds = dict(SCAN_PRESETS.get("Explorer") or {})
        relaxed_thresholds["min_change_percent"] = min(float(relaxed_thresholds.get("min_change_percent", -3.0)), -5.0)
        for symbol in tickers:
            relaxed_signal = rvol_strategy.evaluate(results[symbol], relaxed_thresholds)
            if relaxed_signal.get("strategy_pass"):
                relaxed_signal["strategy_name"] = "rvol_relaxed_fallback"
                relaxed_signal["relaxed_fallback"] = True
                results[symbol] = relaxed_signal
                relaxed_fallback_applied = True

    include_ai_on_fails = _env_truthy_scan("SCAN_AI_INCLUDE_FAILS")
    stage2_label = (
        "Stage 2 · LLM (pass + strategy-fail)"
        if include_ai_on_fails
        else "Stage 2 · running ChatGPT on passes…"
    )
    _prog(1.0, stage2_label)

    for symbol in tickers:
        signal = results[symbol]
        analyst_decision = ""
        analyst_reason = ""
        risk_level_value = ""
        chatgpt_allow = False
        paper_trade_ready = False
        paper_trade_block_reason = ""

        passed = bool(signal.get("strategy_pass"))
        if passed:
            analyst_view = agents["analyst"].analyze(signal)
            analyst_decision, risk_level_value, chatgpt_allow, paper_trade_ready, paper_trade_block_reason = (
                _apply_analyst_fields(signal, analyst_view, strategy_passed=True)
            )
            signals.append(signal)
        elif include_ai_on_fails:
            analyst_view = agents["analyst"].analyze(signal)
            analyst_decision, risk_level_value, chatgpt_allow, paper_trade_ready, paper_trade_block_reason = (
                _apply_analyst_fields(signal, analyst_view, strategy_passed=False)
            )

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
                "chatgpt_trade_plan_json": signal.get("chatgpt_trade_plan_json", "{}"),
                "analyst_trade_plan_text": (str(signal.get("analyst_trade_plan_text") or "")[:4000]),
                "ignition_distance_to_resistance_pct": signal.get("ignition_distance_to_resistance_pct"),
                "mtf_summary_line": signal.get("mtf_summary_line"),
                "mtf_alignment_count": signal.get("mtf_alignment_count"),
                "mtf_snapshot_by_tf_json": json.dumps(signal.get("mtf_snapshot_by_tf") or {}, default=str),
                "amt_buy_signal": signal.get("amt_buy_signal"),
                "amt_summary_line": signal.get("amt_summary_line"),
                "trade_levels_line": signal.get("trade_levels_line"),
                "trade_setup_style": signal.get("trade_setup_style"),
                "indicator_lineage_json": signal.get("indicator_lineage_json", ""),
                "risk_level": risk_level_value,
                "chatgpt_allow_order": chatgpt_allow,
                "paper_trade_ready": paper_trade_ready,
                "paper_trade_block_reason": paper_trade_block_reason,
                "data_delay": signal.get("data_delay"),
                "updated_time": signal.get("updated_time"),
                "quote_source": signal.get("quote_source"),
                "candles_source": signal.get("candles_source"),
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
                "MTF": signal.get("mtf_summary_line") or "—",
                "AMT": signal.get("amt_summary_line") or "—",
                "Kirish/SL/TP": signal.get("trade_levels_line") or "—",
                "ChatGPT Decision": analyst_decision or "—",
                "Trade plan": (
                    (str(signal.get("analyst_trade_plan_text") or "").strip()[:200] + "…")
                    if len(str(signal.get("analyst_trade_plan_text") or "").strip()) > 200
                    else (str(signal.get("analyst_trade_plan_text") or "").strip() or "—")
                ),
                "Risk Level": risk_level_value or "—",
                "Paper Ready": "Yes" if paper_trade_ready else "No",
                "Paper Block": paper_trade_block_reason or "—",
                "Data Delay": signal.get("data_delay"),
                "Updated Time": signal.get("updated_time"),
            }
        )

    if progress is not None and hasattr(progress, "empty"):
        progress.empty()

    agents["logger"].save_signals(signals)
    agents["logger"].save_full_scan(full_scan_logs)
    if _env_truthy_scan_default("AMT_VWAP_SCALP_ENABLED", True) and _env_truthy_scan_default("AMT_RANK_BUY_FIRST", True):
        ranked_signals = sorted(
            signals,
            key=lambda item: (
                not bool(item.get("amt_buy_signal")),
                -_safe_float(item.get("score")),
            ),
        )
    else:
        ranked_signals = sorted(signals, key=lambda item: _safe_float(item.get("score")), reverse=True)
    # Fail + LLM holatida full_scan yetarli; watchlist ranked ga qo'shilsa Telegram "signal" bilan aralashadi.
    if (
        not ranked_signals
        and _env_truthy_scan_default("SCAN_SHOW_WATCHLIST_ON_EMPTY", True)
        and not include_ai_on_fails
    ):
        # Bozor sust paytda ham foydalanuvchi bo'sh jadval ko'rmasin:
        # eng yaqin kandidatlarni WATCHLIST sifatida qaytaramiz (paper-ready emas).
        candidate_pool = [results[s] for s in tickers if not bool(results[s].get("strategy_pass"))]
        candidate_pool = sorted(
            candidate_pool,
            key=lambda item: (
                _safe_float(item.get("score")),
                _safe_float(item.get("rvol")),
                _safe_float(item.get("change_percent")),
                _safe_float(item.get("volume")),
            ),
            reverse=True,
        )
        top_watch = _env_int_bounded("SCAN_EMPTY_WATCHLIST_TOP_N", 6, 3, 30)
        ranked_signals = []
        for item in candidate_pool[:top_watch]:
            cloned = dict(item)
            cloned["watchlist_only"] = True
            cloned["paper_trade_ready"] = False
            cloned["paper_trade_block_reason"] = "Watchlist only: strategy filtersdan to'liq o'tmagan."
            cloned["chatgpt_decision"] = cloned.get("chatgpt_decision") or "WATCHLIST"
            ranked_signals.append(cloned)
    watchlist_fallback_count = sum(1 for item in ranked_signals if item.get("watchlist_only"))
    paper_ready_count = sum(1 for item in signals if item.get("paper_trade_ready"))

    amt_buy_signals = collect_amt_buy_signals(results)
    amt_buy_count = len([1 for sig in results.values() if bool(sig.get("amt_buy_signal"))])

    if os.getenv("TELEGRAM_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}:
        tg = TelegramAlertsAgent()
        tg.notify_scan_summary(
            {
                "tickers_scanned": scanned,
                "eligible_signals": len(signals),
                "paper_ready_signals": paper_ready_count,
                "strategy_mode": strategy_mode,
            }
        )
        tg.notify_signals(ranked_signals, max_items=_env_int_bounded("TELEGRAM_ALERT_TOP_N", 3, 1, 50))
        if amt_buy_alert_enabled() and amt_buy_signals:
            tg.notify_amt_buy_signals(amt_buy_signals, summary={"tickers_scanned": scanned, "amt_buy_count": amt_buy_count})

    mail_on = os.getenv("EMAIL_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
    mail_en = os.getenv("EMAIL_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    if mail_on or mail_en:
        em = EmailAlertsAgent()
        em.notify_scan_summary(
            {
                "tickers_scanned": scanned,
                "eligible_signals": len(signals),
                "paper_ready_signals": paper_ready_count,
                "strategy_mode": strategy_mode,
            }
        )
        em.notify_signals(ranked_signals, max_items=_email_or_telegram_top_n_for_alerts())

    summary = {
        "tickers_scanned": scanned,
        "eligible_signals": len(signals),
        "watchlist_fallback_count": watchlist_fallback_count,
        "amt_buy_count": amt_buy_count,
        "amt_buy_signals": amt_buy_signals,
        "paper_ready_signals": paper_ready_count,
        "failed_signals": scanned - len(signals),
        "symbols_input": scanned,
        "strategy_mode": strategy_mode,
        "scan_preset": controls.preset_name,
        "parallel_workers": controls.max_workers,
        "rvol_thresholds": controls.rvol_thresholds,
        "desk_label": controls.desk_label,
        "relaxed_fallback_applied": relaxed_fallback_applied,
    }
    failed_counter: Counter[str] = Counter()
    quote_source_counter: Counter[str] = Counter()
    candles_source_counter: Counter[str] = Counter()
    for row in full_scan_logs:
        raw_failed = str(row.get("failed_rules") or "").strip()
        if raw_failed:
            for token in [x.strip() for x in raw_failed.split(",") if x.strip()]:
                failed_counter[token] += 1
        qsrc = str(row.get("quote_source") or "").strip()
        csrc = str(row.get("candles_source") or "").strip()
        if qsrc:
            quote_source_counter[qsrc] += 1
        if csrc:
            candles_source_counter[csrc] += 1

    summary["top_failed_rules"] = failed_counter.most_common(5)
    summary["provider_source_summary"] = {
        "quote": dict(quote_source_counter),
        "candles": dict(candles_source_counter),
    }
    return ranked_signals, full_scan_views, summary


def telegram_default_controls() -> SidebarControls:
    """Telegram `/scan` uchun .env asosidagi sukutlar."""

    preset = os.getenv("TELEGRAM_SCAN_PRESET", "Explorer").strip()
    force_explorer = _env_truthy_scan_default("TELEGRAM_FORCE_EXPLORER", True)
    if force_explorer and preset.lower() == "balanced":
        preset = "Explorer"
    if preset not in SCAN_PRESETS:
        preset = "Explorer"
    return SidebarControls(
        desk_label=os.getenv("TELEGRAM_DESK_LABEL", "TG scan").strip() or "TG scan",
        # 0 = cheklovsiz (Alpaca/Polygon qaytargan barcha US tradable gacha).
        max_symbols=_env_int_bounded("TELEGRAM_MAX_SYMBOLS", 0, 0, 9_999_999),
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
    out = list(UniverseAgent().fetch_symbols(limit=controls.max_symbols, use_finviz_elite=use_finviz))
    if not out:
        # Eski fork / noyob xato: bo‘sh universe → Telegram “Tickers: 0”; minimal likvid ro‘yxat.
        lim = controls.max_symbols
        fb = list(FALLBACK_US_EQUITIES)
        return fb if lim <= 0 else fb[: max(1, min(len(fb), lim))]
    return out
