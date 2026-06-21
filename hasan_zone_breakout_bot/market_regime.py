"""market_regime.py — SPY/QQQ bo'yicha bozor rejimi + manba tanlash (fallback).

Manba tartibi: Alpaca -> IBKR -> yfinance. Rejim: BULLISH / CHOPPY / BEARISH / UNKNOWN.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import config, data_alpaca, data_ibkr, data_yfinance
from .indicators import ema, session_vwap


def fetch_ticker(ticker: str, *, preferred: str = "auto") -> Optional[Dict[str, Any]]:
    """Bitta ticker uchun ma'lumot — Alpaca -> IBKR -> yfinance."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    if preferred == "yfinance":
        order = [data_yfinance.fetch]
    elif preferred == "alpaca":
        order = [data_alpaca.fetch, data_yfinance.fetch]
    elif preferred == "ibkr":
        order = [data_ibkr.fetch, data_alpaca.fetch, data_yfinance.fetch]
    else:  # auto
        order = [data_alpaca.fetch, data_ibkr.fetch, data_yfinance.fetch]
    for fetch in order:
        data = fetch(sym)
        if data and data.get("price"):
            return data
    return None


def _is_bullish(data: Dict[str, Any]) -> Dict[str, Any]:
    candles = data.get("candles_5m") or []
    if len(candles) < 5:
        return {"ok": False}
    closes = [float(c.get("c") or 0) for c in candles]
    vwap_series = session_vwap(candles)
    vwap = vwap_series[-1] if vwap_series and vwap_series[-1] is not None else 0
    ema9 = ema(closes, 9)[-1] or 0
    ema20 = ema(closes, 20)[-1] or 0
    price = closes[-1]
    above_vwap = price > vwap if vwap else False
    ema_bull = ema9 > ema20 if (ema9 and ema20) else False
    return {
        "ok": True, "price": round(price, 4), "vwap": round(vwap, 4) if vwap else None,
        "above_vwap": above_vwap, "ema_bullish": ema_bull,
        "bullish": above_vwap and ema_bull,
    }


def get_market_regime(preferred: str = "auto") -> Dict[str, Any]:
    """SPY va QQQ -> BULLISH / CHOPPY / BEARISH / UNKNOWN."""
    results: Dict[str, Any] = {}
    bullish = 0
    valid = 0
    for sym in config.MARKET_REGIME_SYMBOLS:
        data = fetch_ticker(sym, preferred=preferred)
        if not data:
            results[sym] = {"ok": False}
            continue
        info = _is_bullish(data)
        results[sym] = info
        if info.get("ok"):
            valid += 1
            if info.get("bullish"):
                bullish += 1

    if valid == 0:
        regime = "UNKNOWN"
    elif bullish == valid:
        regime = "BULLISH"
    elif bullish == 0:
        regime = "BEARISH"
    else:
        regime = "CHOPPY"

    results["regime"] = regime
    results["bullish"] = regime == "BULLISH"
    results["choppy"] = regime == "CHOPPY"
    results["bearish"] = regime == "BEARISH"
    return results
