"""test_scanner.py — Hasan Scalping Scanner sof mantiq testlari (tarmoqsiz).

Ishga tushirish: `python -m pytest hasan_scalping_scanner/test_scanner.py -q`
"""

from __future__ import annotations

from typing import Any, Dict, List

from hasan_scalping_scanner import indicators, risk_lock, strategy
from hasan_scalping_scanner.risk_lock import RiskState


# ---------------------------------------------------------------------------
# indicators
# ---------------------------------------------------------------------------

def test_rvol_and_dollar_volume() -> None:
    assert indicators.rvol(2_000_000, 1_000_000) == 2.0
    assert indicators.rvol(100, 0) == 0.0
    assert indicators.dollar_volume(2.5, 1_000_000) == 2_500_000.0


def test_spread_pct_unknown_when_missing() -> None:
    assert indicators.spread_pct(None, None, 2.0) is None
    assert indicators.spread_pct(1.98, 2.02, 2.0) == 2.0


def test_ema_basic() -> None:
    vals = [float(i) for i in range(1, 21)]
    e = indicators.ema(vals, 9)
    assert e[-1] is not None and e[-1] > e[8]  # ko'tarilayotgan seriya


def test_session_vwap_monotonic_rising() -> None:
    candles = [{"h": 10 + i, "l": 9 + i, "c": 9.5 + i, "v": 1000} for i in range(5)]
    vw = indicators.session_vwap(candles)
    assert all(v is not None for v in vw)
    assert vw[-1] > vw[0]


def test_volume_spike_ratio() -> None:
    candles = [{"v": 1000} for _ in range(20)]
    candles.append({"v": 3000})
    ratio = indicators.volume_spike_ratio(candles, lookback=20)
    assert ratio == 3.0
    assert indicators.classify_volume_spike(ratio) == "IGNITION"


# ---------------------------------------------------------------------------
# strategy — VWAP reclaim
# ---------------------------------------------------------------------------

def _reclaim_candles() -> List[Dict[str, Any]]:
    """VWAP ostidan tepaga reclaim qilgan 5-min shamlar."""
    out: List[Dict[str, Any]] = []
    # 18 ta past, tor sham (VWAP ni pastga belgilaydi)
    for i in range(18):
        out.append({"t": i, "o": 1.0, "h": 1.02, "l": 0.98, "c": 1.0, "v": 1000})
    # tushish (VWAP ostida)
    out.append({"t": 18, "o": 1.0, "h": 1.01, "l": 0.95, "c": 0.96, "v": 1500})
    # reclaim sham: VWAP ustida yopiladi, katta hajm
    out.append({"t": 19, "o": 0.97, "h": 1.10, "l": 0.97, "c": 1.08, "v": 6000})
    # ushlab turish
    out.append({"t": 20, "o": 1.08, "h": 1.12, "l": 1.05, "c": 1.10, "v": 4000})
    return out


def test_detect_vwap_reclaim() -> None:
    candles = _reclaim_candles()
    vw = indicators.session_vwap(candles)
    res = strategy.detect_vwap_reclaim(candles, vw)
    assert res["reclaimed"] is True
    assert res["closed_above_vwap"] is True
    assert res["reclaim_high"] is not None


def test_full_signal_paper_ready_when_clean() -> None:
    candles = _reclaim_candles()
    ind = indicators.compute_indicators(
        price=1.10, prev_close=1.00,
        current_volume=2_000_000, avg_20d_volume=800_000,
        bid=1.095, ask=1.105, candles_5m=candles,
        day_high=1.12, day_low=0.95,
    )
    ind["ticker"] = "TEST"
    ind["_candles_5m"] = candles
    sig = strategy.evaluate(ind, market_bullish=True, data_complete=True)
    assert sig["score"] >= 7
    assert sig["decision"].endswith("PAPER_READY")
    assert sig["entry"] is not None and sig["stop_loss"] is not None
    assert sig["stop_loss"] < sig["entry"]
    assert sig["risk_reward"] >= 2.0


def test_no_trade_when_price_out_of_range() -> None:
    candles = _reclaim_candles()
    ind = indicators.compute_indicators(
        price=50.0, prev_close=48.0,  # $50 — oraliqdan tashqarida
        current_volume=2_000_000, avg_20d_volume=800_000,
        bid=49.9, ask=50.1, candles_5m=candles, day_high=51, day_low=47,
    )
    ind["ticker"] = "BIG"
    ind["_candles_5m"] = candles
    sig = strategy.evaluate(ind, market_bullish=True, data_complete=True)
    assert sig["decision"] == "NO_TRADE"


def test_spread_unknown_blocks_paper_ready() -> None:
    candles = _reclaim_candles()
    ind = indicators.compute_indicators(
        price=1.10, prev_close=1.00,
        current_volume=2_000_000, avg_20d_volume=800_000,
        bid=None, ask=None, candles_5m=candles, day_high=1.12, day_low=0.95,
    )
    ind["ticker"] = "NOSPREAD"
    ind["_candles_5m"] = candles
    sig = strategy.evaluate(ind, market_bullish=True, data_complete=False)
    assert not sig["decision"].endswith("PAPER_READY")  # watchlist yoki pastroq


def test_bearish_market_blocks_weak_paper_ready() -> None:
    candles = _reclaim_candles()
    ind = indicators.compute_indicators(
        price=1.10, prev_close=1.00,
        current_volume=2_000_000, avg_20d_volume=800_000,
        bid=1.095, ask=1.105, candles_5m=candles, day_high=1.12, day_low=0.95,
    )
    ind["ticker"] = "TEST"
    ind["_candles_5m"] = candles
    # rvol ~2.5 (<3 strong emas) -> bearish bozorda paper-ready bloklanadi
    sig = strategy.evaluate(ind, market_bullish=False, market_bearish=True, data_complete=True)
    assert sig["decision"] == "WATCHLIST"


# ---------------------------------------------------------------------------
# risk_lock
# ---------------------------------------------------------------------------

def test_risk_lock_ok_when_clean() -> None:
    allowed, status, _ = risk_lock.evaluate_risk_lock(RiskState())
    assert allowed is True and status == "OK"


def test_risk_lock_max_trades() -> None:
    allowed, status, _ = risk_lock.evaluate_risk_lock(RiskState(trades_today=3))
    assert allowed is False and status == "STOP_TRADING"


def test_risk_lock_consecutive_losses() -> None:
    allowed, _, _ = risk_lock.evaluate_risk_lock(RiskState(consecutive_losses=2))
    assert allowed is False


def test_risk_lock_hard_stop() -> None:
    allowed, _, _ = risk_lock.evaluate_risk_lock(RiskState(daily_pnl=-75.0))
    assert allowed is False


def test_risk_lock_emotional() -> None:
    allowed, _, reasons = risk_lock.evaluate_risk_lock(RiskState(feeling_angry=True))
    assert allowed is False
    assert any("jahl" in r.lower() or "asabiy" in r.lower() for r in reasons)


def test_risk_lock_revenge() -> None:
    allowed, _, _ = risk_lock.evaluate_risk_lock(RiskState(wants_to_recover_losses=True))
    assert allowed is False


def test_alert_text_has_all_fields() -> None:
    sig = {
        "ticker": "SNDL", "price": 1.1, "decision": "PAPER_READY", "score": 8,
        "entry": 1.12, "stop_loss": 1.05, "target1": 1.19, "target2": 1.26,
        "risk_reward": 2.0, "reason": "clean", "mistake_warning": "none",
    }
    text = risk_lock.build_alert_text(sig)
    for token in ("HASAN SCALPING SIGNAL", "Ticker:", "Entry idea:", "Stop-loss:",
                  "Target 1:", "Risk/Reward:", "Warning:"):
        assert token in text


def test_telegram_placeholder_does_not_send() -> None:
    # V1: hech narsa yuborilmaydi
    assert risk_lock.send_telegram_alert_placeholder({"ticker": "X"}) is False
