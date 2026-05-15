"""Market Shield regime va signal gate."""

from __future__ import annotations

from agents.market_shield import (
    apply_market_shield_to_signal,
    classify_regime,
    market_shield_blocks_paper,
)


def _spy_bull() -> dict:
    return {"ok": True, "bull": True, "day_pct": 0.3, "above_vwap": True, "above_ema20": True}


def _qqq_bull() -> dict:
    return _spy_bull()


def test_classify_bull() -> None:
    regime, flags = classify_regime(_spy_bull(), _qqq_bull(), {"ok": True, "calm": True, "rising": False, "day_pct": 1.0, "close": 18.0})
    assert regime == "BULL"
    assert flags["market_ok_for_long"] is True


def test_classify_news_lock() -> None:
    spy = {"ok": True, "bull": False, "day_pct": -1.5, "above_vwap": False, "above_ema20": False}
    qqq = {"ok": True, "bull": False, "day_pct": -1.3, "above_vwap": False, "above_ema20": False}
    vix = {"ok": True, "calm": False, "rising": True, "day_pct": 12.0, "close": 26.0}
    regime, flags = classify_regime(spy, qqq, vix)
    assert regime == "NEWS_LOCK"
    assert flags["market_blocked"] is True


def test_apply_blocks_low_score_neutral(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_SHIELD_MIN_SCORE_NEUTRAL", "80")
    shield = {
        "market_shield_enabled": True,
        "market_regime": "NEUTRAL",
        "market_shield_min_score": 80,
        "market_shield_spy": _spy_bull(),
        "market_shield_vix": {"rising": False},
    }
    sig = apply_market_shield_to_signal({"ticker": "AAA", "score": 65, "strategy_pass": True}, shield)
    assert sig.get("market_shield_buy_blocked") is True


def test_paper_blocks_news_lock() -> None:
    blocked, reason = market_shield_blocks_paper({"market_regime": "NEWS_LOCK"})
    assert blocked is True
    assert "NEWS_LOCK" in reason
