"""tradingview_data — tarmoqsiz unit testlar (TA_Handler mock)."""

from __future__ import annotations

import sys
import types
from typing import Any, Dict, Optional

from agents.tradingview_data import (
    fetch_tv_analysis,
    normalize_interval,
    tv_recommendation_badge,
    tv_signal_line,
)


# ---------------------------------------------------------------------------
# normalize_interval
# ---------------------------------------------------------------------------

def test_normalize_interval_known() -> None:
    assert normalize_interval("1m") == "1m"
    assert normalize_interval("5m") == "5m"
    assert normalize_interval("daily") == "1d"
    assert normalize_interval("1H".lower()) == "1h"


def test_normalize_interval_unknown_defaults_5m() -> None:
    assert normalize_interval("xyz") == "5m"
    assert normalize_interval("") == "5m"


# ---------------------------------------------------------------------------
# tv_recommendation_badge
# ---------------------------------------------------------------------------

def test_badge_known() -> None:
    assert "BUY" in tv_recommendation_badge("STRONG_BUY")
    assert "SELL" in tv_recommendation_badge("SELL")
    assert "NEYTRAL" in tv_recommendation_badge("NEUTRAL")


def test_badge_unknown_defaults_neutral() -> None:
    assert "NEYTRAL" in tv_recommendation_badge("???")
    assert "NEYTRAL" in tv_recommendation_badge(None)


# ---------------------------------------------------------------------------
# fetch_tv_analysis — TA_Handler mock orqali
# ---------------------------------------------------------------------------

class _FakeAnalysis:
    def __init__(self, rec: str = "BUY") -> None:
        self.summary = {"RECOMMENDATION": rec, "BUY": 12, "SELL": 3, "NEUTRAL": 9}
        self.oscillators = {"RECOMMENDATION": "NEUTRAL"}
        self.moving_averages = {"RECOMMENDATION": "BUY"}
        self.indicators = {
            "RSI": 58.4,
            "MACD.macd": 0.42,
            "MACD.signal": 0.31,
            "close": 182.3,
            "change": 1.8,
            "volume": 5_000_000,
            "EMA20": 180.1,
            "EMA50": 175.0,
        }


def _install_fake_handler(monkeypatch, *, fail_exchanges: Optional[set] = None, rec: str = "BUY") -> Dict[str, Any]:
    """tradingview_ta modulini soxta TA_Handler bilan o'rnatadi."""
    calls: Dict[str, Any] = {"exchanges_tried": []}
    fail = fail_exchanges or set()

    class _FakeHandler:
        def __init__(self, *, symbol: str, screener: str, exchange: str, interval: str) -> None:
            self.symbol = symbol
            self.exchange = exchange
            self.interval = interval
            calls["exchanges_tried"].append(exchange)

        def get_analysis(self) -> _FakeAnalysis:
            if self.exchange in fail:
                raise ValueError(f"symbol not found on {self.exchange}")
            return _FakeAnalysis(rec=rec)

    fake_mod = types.ModuleType("tradingview_ta")
    fake_mod.TA_Handler = _FakeHandler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tradingview_ta", fake_mod)
    return calls


def test_fetch_returns_simplified_dict(monkeypatch) -> None:
    _install_fake_handler(monkeypatch, rec="STRONG_BUY")
    data = fetch_tv_analysis("AAPL", interval="5m")
    assert data is not None
    assert data["ticker"] == "AAPL"
    assert data["recommendation"] == "STRONG_BUY"
    assert data["buy"] == 12
    assert data["rsi"] == 58.4
    assert data["close"] == 182.3
    assert data["exchange"] == "NASDAQ"  # birinchi birja


def test_fetch_falls_back_to_next_exchange(monkeypatch) -> None:
    calls = _install_fake_handler(monkeypatch, fail_exchanges={"NASDAQ"})
    data = fetch_tv_analysis("IBM", interval="1d")
    assert data is not None
    assert data["exchange"] == "NYSE"  # NASDAQ fail bo'ldi
    assert calls["exchanges_tried"][:2] == ["NASDAQ", "NYSE"]


def test_fetch_explicit_exchange_prefix(monkeypatch) -> None:
    calls = _install_fake_handler(monkeypatch)
    data = fetch_tv_analysis("NASDAQ:TSLA")
    assert data is not None
    assert data["ticker"] == "TSLA"
    assert calls["exchanges_tried"] == ["NASDAQ"]  # faqat ko'rsatilgan birja


def test_fetch_all_exchanges_fail_returns_none(monkeypatch) -> None:
    _install_fake_handler(monkeypatch, fail_exchanges={"NASDAQ", "NYSE", "AMEX"})
    assert fetch_tv_analysis("FAKE") is None


def test_fetch_empty_ticker_returns_none() -> None:
    assert fetch_tv_analysis("") is None
    assert fetch_tv_analysis("   ") is None


def test_fetch_no_library_returns_none(monkeypatch) -> None:
    # tradingview_ta o'rnatilmagan holatni taqlid qilish
    monkeypatch.setitem(sys.modules, "tradingview_ta", None)
    assert fetch_tv_analysis("AAPL") is None


def test_fetch_respects_env_exchanges(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGVIEW_EXCHANGES", "NYSE,AMEX")
    calls = _install_fake_handler(monkeypatch, fail_exchanges={"NYSE"})
    data = fetch_tv_analysis("F")
    assert data is not None
    assert calls["exchanges_tried"] == ["NYSE", "AMEX"]


# ---------------------------------------------------------------------------
# tv_signal_line
# ---------------------------------------------------------------------------

def test_tv_signal_line_contains_fields(monkeypatch) -> None:
    _install_fake_handler(monkeypatch, rec="BUY")
    data = fetch_tv_analysis("AAPL", interval="5m")
    line = tv_signal_line(data)
    assert "TradingView" in line
    assert "BUY" in line
    assert "RSI" in line
    assert "AAPL" in line


def test_tv_signal_line_empty_on_none() -> None:
    assert tv_signal_line(None) == ""
