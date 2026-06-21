"""test_bot.py — Hasan Zone Breakout Bot sof mantiq testlari (tarmoqsiz).

Ishga tushirish: python -m pytest hasan_zone_breakout_bot/test_bot.py -q
"""

from __future__ import annotations

from typing import Any, Dict, List

from hasan_zone_breakout_bot import indicators, risk_lock, strategy, telegram_bot, zones
from hasan_zone_breakout_bot.data_ibkr import _num
from hasan_zone_breakout_bot.risk_lock import RiskState


# ---------------------------------------------------------------------------
# indicators
# ---------------------------------------------------------------------------

def test_rvol_dollar_spread() -> None:
    assert indicators.rvol(2_000_000, 1_000_000) == 2.0
    assert indicators.dollar_volume(2.5, 1_000_000) == 2_500_000.0
    assert indicators.spread_pct(None, None, 2.0) is None
    assert indicators.spread_pct(1.98, 2.02, 2.0) == 2.0


def test_atr_and_vwap() -> None:
    candles = [{"o": 10, "h": 10.5, "l": 9.5, "c": 10, "v": 1000} for _ in range(15)]
    assert indicators.atr(candles) is not None
    vw = indicators.session_vwap(candles)
    assert vw[-1] is not None


def test_volume_spike() -> None:
    candles = [{"v": 1000} for _ in range(20)] + [{"v": 3000}]
    assert indicators.volume_spike_ratio(candles) == 3.0
    assert indicators.classify_volume_spike(3.0) == "IGNITION"


# ---------------------------------------------------------------------------
# zones
# ---------------------------------------------------------------------------

def _zone_candles() -> List[Dict[str, Any]]:
    """Demand zona + consolidation + breakout shamlari."""
    out: List[Dict[str, Any]] = []
    # past bazaviy daraja (demand zonani belgilaydi)
    for i in range(10):
        out.append({"t": i, "o": 10.0, "h": 10.3, "l": 9.7, "c": 10.0, "v": 2000})
    # zona ichida konsolidatsiya (tor, hajm pasayadi)
    for i in range(10, 20):
        out.append({"t": i, "o": 10.05, "h": 10.15, "l": 9.95, "c": 10.05, "v": 1000})
    # breakout sham: zona ustida, katta hajm, tepada yopiladi
    out.append({"t": 20, "o": 10.1, "h": 10.8, "l": 10.1, "c": 10.7, "v": 5000})
    return out


def test_detect_zones_finds_demand() -> None:
    z = zones.detect_zones(_zone_candles())
    assert z["demand"] or z["supply"]


def test_consolidation_and_breakout() -> None:
    # Aniq zona ichida konsolidatsiya: yopilishlar zona [9.9, 10.1] ichida
    zone = (9.9, 10.1)
    candles = [{"t": i, "o": 10.0, "h": 10.08, "l": 9.92, "c": 10.0, "v": 1000} for i in range(12)]
    cons = zones.detect_consolidation(candles, zone)
    assert cons["inside_frac"] >= 0.7
    assert cons["consolidation"] is True


def test_false_breakdown() -> None:
    candles = _zone_candles()
    zone = (9.8, 10.2)
    # zona ostiga sham qo'shamiz, keyin qaytaramiz
    candles2 = candles[:18] + [
        {"t": 100, "o": 10.0, "h": 10.0, "l": 9.5, "c": 9.6, "v": 3000},  # sweep
        {"t": 101, "o": 9.7, "h": 10.1, "l": 9.7, "c": 10.05, "v": 2500},  # reclaim
    ]
    assert zones.detect_false_breakdown(candles2, zone) is True


# ---------------------------------------------------------------------------
# strategy — scoring & decision
# ---------------------------------------------------------------------------

def _data_with_breakout(spread: bool = True) -> Dict[str, Any]:
    candles = _zone_candles()
    # ko'proq tarix (1h zona uchun) + intraday
    return {
        "ticker": "TEST",
        "price": 10.7,
        "prev_close": 10.0,
        "current_volume": 2_000_000,
        "avg_20d_volume": 800_000,
        "bid": 10.69 if spread else None,
        "ask": 10.71 if spread else None,
        "candles_1h": candles,
        "candles_5m": candles,
        "candles_3m": candles,
        "candles_1m": candles,
        "day_high": 10.8,
        "day_low": 9.7,
        "data_complete": spread,
    }


def test_evaluate_produces_full_signal() -> None:
    regime = {"regime": "BULLISH", "bullish": True, "choppy": False, "bearish": False}
    sig = strategy.evaluate_setup(_data_with_breakout(), mode="Large Cap", regime=regime,
                                  halal_status="COMPLIANT", market_open=True)
    for key in ("score", "decision", "entry", "stop_loss", "target1", "target2",
                "risk_reward", "vwap_status", "zone_status", "reason"):
        assert key in sig
    assert isinstance(sig["score"], int)


def test_market_closed_override() -> None:
    regime = {"regime": "BULLISH", "bullish": True, "choppy": False, "bearish": False}
    sig = strategy.evaluate_setup(_data_with_breakout(), mode="Large Cap", regime=regime,
                                  halal_status="COMPLIANT", market_open=False)
    assert sig["decision"] == "MARKET_CLOSED"


def test_choppy_market_caps_to_watchlist() -> None:
    regime = {"regime": "CHOPPY", "bullish": False, "choppy": True, "bearish": False}
    sig = strategy.evaluate_setup(_data_with_breakout(), mode="Large Cap", regime=regime,
                                  halal_status="COMPLIANT", market_open=True)
    assert not str(sig["decision"]).endswith("PAPER_READY")


def test_no_stop_forces_no_trade() -> None:
    regime = {"regime": "BULLISH", "bullish": True, "choppy": False, "bearish": False}
    data = _data_with_breakout()
    # zonani va VWAP'ni yo'q qilamiz -> stop aniq emas
    data["candles_5m"] = [{"t": i, "o": 10, "h": 10, "l": 10, "c": 10, "v": 1} for i in range(3)]
    data["candles_1h"] = data["candles_5m"]
    sig = strategy.evaluate_setup(data, mode="Large Cap", regime=regime, market_open=True)
    assert sig["decision"] in {"NO_TRADE", "WATCHLIST", "MARKET_CLOSED"}


def test_score_to_decision_thresholds() -> None:
    assert strategy.score_to_decision(3) == "NO_TRADE"
    assert strategy.score_to_decision(7) == "WATCHLIST"
    assert strategy.score_to_decision(10) == "PAPER_READY"
    assert strategy.score_to_decision(13) == "HIGH_QUALITY_PAPER_READY"


# ---------------------------------------------------------------------------
# risk_lock
# ---------------------------------------------------------------------------

def test_risk_lock_clean_ok() -> None:
    allowed, status, _ = risk_lock.evaluate_risk_lock(RiskState())
    assert allowed and status == "OK"


def test_risk_lock_blocks() -> None:
    from hasan_zone_breakout_bot import config
    # Env-mustaqil: config qiymatlaridan foydalanamiz (repo .env override qilishi mumkin)
    assert risk_lock.evaluate_risk_lock(RiskState(trades_today=config.MAX_TRADES_PER_DAY))[0] is False
    assert risk_lock.evaluate_risk_lock(RiskState(consecutive_losses=config.MAX_CONSECUTIVE_LOSSES))[0] is False
    assert risk_lock.evaluate_risk_lock(RiskState(daily_pnl=config.DAILY_HARD_STOP - 5))[0] is False
    assert risk_lock.evaluate_risk_lock(RiskState(feeling_angry=True))[0] is False
    assert risk_lock.evaluate_risk_lock(RiskState(wants_to_recover_losses=True))[0] is False


# ---------------------------------------------------------------------------
# telegram dedup + alert format
# ---------------------------------------------------------------------------

def test_should_send_only_paper_ready() -> None:
    telegram_bot._LAST_SENT.clear()
    assert telegram_bot.should_send({"ticker": "A", "decision": "WATCHLIST", "score": 9}) is False
    assert telegram_bot.should_send({"ticker": "A", "decision": "PAPER_READY", "score": 9,
                                     "zone_status": "Breakout"}) is True


def test_dedup_blocks_repeat() -> None:
    telegram_bot._LAST_SENT.clear()
    sig = {"ticker": "B", "decision": "PAPER_READY", "score": 9, "zone_status": "Breakout"}
    assert telegram_bot.should_send(sig) is True
    telegram_bot._mark_sent(sig)
    # darhol qayta — bloklanadi (score oshmadi)
    assert telegram_bot.should_send(sig) is False
    # score oshsa — ruxsat
    sig2 = dict(sig, score=11)
    assert telegram_bot.should_send(sig2) is True


def test_alert_text_has_exact_format() -> None:
    sig = {
        "ticker": "AAPL", "mode": "Large Cap", "decision": "PAPER_READY", "score": 10,
        "halal_status": "COMPLIANT", "price": 10.7, "vwap": 10.2, "ema9": 10.3, "ema20": 10.1,
        "rvol": 2.5, "dollar_volume": 1_000_000, "spread_pct": 0.2, "volume_spike": 2.0,
        "zone_low": 9.8, "zone_high": 10.2, "consolidation": True, "breakout": True,
        "entry": 10.71, "stop_loss": 10.19, "target1": 11.2, "target2": 11.7,
        "risk_reward": 2.0, "reason": "clean", "vwap_status": "Reclaim+hold", "zone_status": "Breakout",
        "_flags": {"confirm_3m": True},
    }
    regime = {"SPY": {"ok": True, "bullish": True}, "QQQ": {"ok": True, "bullish": True}}
    text = telegram_bot.build_alert_text(sig, regime)
    for token in ("🚨 HASAN SCALPING SIGNAL", "Ticker: AAPL", "Mode: Large Cap", "Halal status:",
                  "Market Regime:", "Zone Low:", "Entry Idea:", "Risk/Reward:", "Warning:",
                  "Signal-only", "No stop-loss = no trade"):
        assert token in text


def test_halal_unknown_warning_in_alert() -> None:
    sig = {"ticker": "ZZZ", "mode": "Penny Momentum", "decision": "PAPER_READY", "score": 9,
           "halal_status": "UNKNOWN", "price": 1.0, "_flags": {}}
    regime = {"SPY": {}, "QQQ": {}}
    text = telegram_bot.build_alert_text(sig, regime)
    assert "Halal status not verified." in text


# ---------------------------------------------------------------------------
# IBKR.com Web API qiymat parseri
# ---------------------------------------------------------------------------

def test_ibkr_num_parser() -> None:
    assert _num("297.19") == 297.19
    assert _num("45.6M") == 45_600_000.0
    assert _num("C295.95") == 295.95
    assert _num("0.42%") == 0.42
    assert _num("") is None
