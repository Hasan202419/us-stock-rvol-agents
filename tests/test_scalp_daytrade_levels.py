"""Skalp / day-trade darajalari (trade_levels_line)."""

from agents.scalp_daytrade_levels import compute_scalp_daytrade_levels


def test_amt_levels_long():
    sig = {
        "price": 10.5,
        "amt_ok": True,
        "amt_val": 10.0,
        "amt_poc_proxy": 10.8,
        "amt_vah": 11.2,
        "amt_buy_signal": True,
    }
    out = compute_scalp_daytrade_levels(sig)
    assert out["trade_levels_ok"] is True
    assert out["trade_entry_price"] == 10.5
    assert out["trade_stop_loss"] < 10.5
    assert out["trade_tp1"] == 10.8
    assert out["trade_tp2"] == 11.2
    assert "KIRISH" in out["trade_levels_line"]
    assert out["stop_suggestion"] == out["trade_stop_loss"]


def test_strategy_fallback_when_no_amt():
    sig = {
        "price": 50.0,
        "strategy_name": "VWAP Breakout",
        "stop_suggestion": 48.0,
        "take_profit_suggestion": 55.0,
        "amt_ok": False,
    }
    out = compute_scalp_daytrade_levels(sig)
    assert out["trade_levels_ok"] is True
    assert out["trade_setup_style"] == "day_vwap"
    assert out["trade_tp1"] == 55.0
    assert out["trade_stop_loss"] == 48.0


def test_no_levels_when_insufficient():
    sig = {"price": 1.0, "amt_ok": False}
    out = compute_scalp_daytrade_levels(sig)
    assert out["trade_levels_ok"] is False
    assert out.get("trade_levels_line") == ""
