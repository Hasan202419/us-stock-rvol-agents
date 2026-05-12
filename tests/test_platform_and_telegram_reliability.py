from __future__ import annotations

import importlib.util
from pathlib import Path

from agents.chatgpt_analyst_agent import ChatGPTAnalystAgent
from agents.market_data_agent import MarketDataAgent
from agents.scan_pipeline import SidebarControls
from agents.scan_presets import SCAN_PRESETS
from agents.telegram_alerts_agent import TelegramAlertsAgent


def test_allow_order_infers_true_when_missing_and_watchworthy() -> None:
    agent = ChatGPTAnalystAgent(openai_api_key=None, finnhub_api_key=None)
    out = agent._normalize_response(  # type: ignore[attr-defined]
        {
            "decision": "WATCH",
            "confidence": 7,
            "reason": "Looks constructive.",
            "risk_level": "LOW",
            "risk_flags_hard": [],
            "paper_ready_blocked": None,
        }
    )
    assert out["allow_order"] is True
    assert out["paper_ready_explicit"] is True


def test_allow_order_infers_false_when_hard_flags_exist() -> None:
    agent = ChatGPTAnalystAgent(openai_api_key=None, finnhub_api_key=None)
    out = agent._normalize_response(  # type: ignore[attr-defined]
        {
            "decision": "WATCH",
            "confidence": 7,
            "reason": "Looks constructive.",
            "risk_level": "LOW",
            "risk_flags_hard": ["NO_LIQUIDITY"],
        }
    )
    assert out["allow_order"] is False
    assert out["paper_ready_explicit"] is False


def test_run_scan_market_adds_paper_trade_fields(monkeypatch, tmp_path: Path) -> None:
    import agents.scan_pipeline as sp

    class DummyMarketData:
        data_delay_minutes = 15

        def fetch_market_data(self, symbol: str) -> dict:
            return {"symbol": symbol}

    class DummyRVOL:
        def calculate(self, market_data: dict) -> dict:
            return market_data

    class DummyAnalyst:
        def analyze(self, signal: dict) -> dict:
            return {
                "decision": "WATCH",
                "confidence": 8,
                "reason": "Ready for paper.",
                "risk_level": "LOW",
                "allow_order": True,
                "risk_flags": [],
                "risk_flags_hard": [],
                "entry_condition": "Break high",
                "paper_ready_blocked": None,
                "paper_ready_explicit": True,
            }

    class DummyLogger:
        def save_signals(self, _signals) -> None:
            return None

        def save_full_scan(self, _rows) -> None:
            return None

    monkeypatch.setattr(sp, "StrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "VwapBreakoutStrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "VolumeIgnitionStrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "resolve_strategy_mode", lambda: "rvol")
    monkeypatch.setattr(
        sp,
        "build_scan_agents",
        lambda repo_root: {
            "market_data": DummyMarketData(),
            "rvol": DummyRVOL(),
            "analyst": DummyAnalyst(),
            "logger": DummyLogger(),
        },
    )
    monkeypatch.setattr(
        sp,
        "run_stage_one_strategy",
        lambda *args, **kwargs: {
            "ticker": "AAA",
            "strategy_pass": True,
            "failed_rules": [],
            "score": 90,
            "price": 10.0,
            "change_percent": 1.2,
            "volume": 100_000,
            "avg_volume": 50_000,
            "rvol": 2.0,
            "strategy_name": "rvol_momentum",
        },
    )

    controls = SidebarControls(
        desk_label="Desk",
        max_symbols=1,
        preset_name="Balanced",
        rvol_thresholds=dict(SCAN_PRESETS["Balanced"]),
        max_workers=2,
        finviz_csv_universe=False,
    )
    ranked, full_scan_views, summary = sp.run_scan_market(["AAA"], controls, repo_root=tmp_path, progress=None)
    assert ranked[0]["paper_trade_ready"] is True
    assert ranked[0]["paper_trade_block_reason"] == ""
    assert summary["paper_ready_signals"] == 1
    assert full_scan_views[0]["Paper Ready"] == "Yes"


def test_scan_ai_include_fails_calls_llm_on_strategy_fail(monkeypatch, tmp_path: Path) -> None:
    """SCAN_AI_INCLUDE_FAILS=true — Strategiya o'tmagan tickerlar ham LLM dan fikr oladi (jadvalda)."""

    import agents.scan_pipeline as sp

    class DummyMarketData:
        data_delay_minutes = 15

        def fetch_market_data(self, symbol: str) -> dict:
            return {"symbol": symbol}

    class DummyRVOL:
        def calculate(self, market_data: dict) -> dict:
            return market_data

    ai_calls: list[str] = []

    class DummyAnalyst:
        def analyze(self, signal: dict) -> dict:
            ai_calls.append(str(signal.get("ticker")))
            return {
                "decision": "AVOID",
                "confidence": 2,
                "reason": "Filtered out.",
                "risk_level": "HIGH",
                "allow_order": False,
                "risk_flags": [],
                "risk_flags_hard": [],
                "entry_condition": "",
                "paper_ready_blocked": None,
                "paper_ready_explicit": False,
            }

    class DummyLogger:
        def save_signals(self, _signals) -> None:
            return None

        def save_full_scan(self, _rows) -> None:
            return None

    monkeypatch.setenv("SCAN_AI_INCLUDE_FAILS", "true")
    monkeypatch.setattr(sp, "StrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "VwapBreakoutStrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "VolumeIgnitionStrategyAgent", lambda: object())
    monkeypatch.setattr(sp, "resolve_strategy_mode", lambda: "rvol")
    monkeypatch.setattr(
        sp,
        "build_scan_agents",
        lambda repo_root: {
            "market_data": DummyMarketData(),
            "rvol": DummyRVOL(),
            "analyst": DummyAnalyst(),
            "logger": DummyLogger(),
        },
    )
    monkeypatch.setattr(
        sp,
        "run_stage_one_strategy",
        lambda *args, **kwargs: {
            "ticker": "ZZZ",
            "strategy_pass": False,
            "failed_rules": ["rvol_low"],
            "score": 1,
            "price": 5.0,
            "change_percent": 0.0,
            "volume": 1000,
            "avg_volume": 2000,
            "rvol": 0.5,
            "strategy_name": "rvol_momentum",
        },
    )

    controls = SidebarControls(
        desk_label="Desk",
        max_symbols=1,
        preset_name="Balanced",
        rvol_thresholds=dict(SCAN_PRESETS["Balanced"]),
        max_workers=2,
        finviz_csv_universe=False,
    )
    ranked, full_scan_views, summary = sp.run_scan_market(["ZZZ"], controls, repo_root=tmp_path, progress=None)
    assert ai_calls == ["ZZZ"]
    assert ranked == []
    assert summary["eligible_signals"] == 0
    assert full_scan_views[0]["ChatGPT Decision"] == "AVOID"
    assert full_scan_views[0]["Strategy Pass"] == "No"


def test_telegram_alert_logs_non_2xx(monkeypatch, capsys) -> None:
    class DummyResponse:
        ok = False
        status_code = 403
        text = "forbidden"

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_ALERTS_ENABLED", "true")
    monkeypatch.setattr("agents.telegram_alerts_agent.requests.post", lambda *args, **kwargs: DummyResponse())

    TelegramAlertsAgent().notify_scan_summary({"tickers_scanned": 10, "eligible_signals": 2, "paper_ready_signals": 1})
    out = capsys.readouterr().out
    assert "sendMessage error" in out


def test_backtest_symbol_uses_remainder() -> None:
    bot_path = Path(__file__).resolve().parents[1] / "scripts" / "telegram_command_bot.py"
    spec = importlib.util.spec_from_file_location("_telegram_bot_backtest_test", bot_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._backtest_symbol_from_remainder("aapl") == "AAPL"


def test_market_data_provider_priority_accepts_massive_alias(monkeypatch) -> None:
    order: list[str] = []
    agent = MarketDataAgent()

    monkeypatch.setenv("MARKET_DATA_PROVIDER_PRIORITY", "massive,yahoo")
    monkeypatch.setattr(agent, "_fetch_polygon_snapshot", lambda ticker: order.append("polygon") or {})
    monkeypatch.setattr(agent, "_fetch_yahoo_daily_bundle", lambda ticker: order.append("yahoo") or {"candles": []})
    monkeypatch.setattr(agent, "_fetch_finnhub_quote", lambda ticker: order.append("finnhub") or {})
    monkeypatch.setattr(agent, "_fetch_alpaca_latest_bar", lambda ticker: order.append("alpaca") or {})
    monkeypatch.setattr(agent, "_fetch_polygon_daily_candles", lambda ticker: order.append("polygon_candles") or [])

    agent.fetch_market_data("AAPL")
    # Har bir prioritetda avval kotirovka, keyin (mavjud bo‘lsa) shamlar — Yahoo ikkalasida ham bir xil `_fetch_yahoo_daily_bundle`.
    assert order[:3] == ["polygon", "polygon_candles", "yahoo"]
    assert order[3] == "yahoo"
