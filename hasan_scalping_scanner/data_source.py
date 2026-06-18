"""data_source.py — ma'lumot manbalari: Alpaca -> IBKR (placeholder) -> yfinance.

Tartib:
 1. Alpaca API (kalit bo'lsa) — realtime quote + bid/ask
 2. IBKR Web API (placeholder — ulangan bo'lsa)
 3. yfinance — bepul zaxira (bid/ask ko'pincha yo'q -> spread UNKNOWN)

Ma'lumot kechikkan/to'liq bo'lmasa `data_complete=False` qaytadi -> strategiya
uni PAPER_READY emas, WATCHLIST qiladi. HECH qanday order/trade YO'Q.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from . import indicators


def _to_candles(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tashqi formatdan ichki {t,o,h,l,c,v} ga."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            out.append({
                "t": int(r["t"]),
                "o": float(r["o"]), "h": float(r["h"]),
                "l": float(r["l"]), "c": float(r["c"]),
                "v": float(r.get("v") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["t"])
    return out


# ---------------------------------------------------------------------------
# yfinance (bepul zaxira)
# ---------------------------------------------------------------------------

def _yf_fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """yfinance orqali 5m/1m shamlar + kunlik o'rtacha hajm + quote."""
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        intraday = tk.history(period="1d", interval="5m", auto_adjust=False)
        intraday_1m = tk.history(period="1d", interval="1m", auto_adjust=False)
        daily = tk.history(period="1mo", interval="1d", auto_adjust=False)
        if intraday is None or len(intraday) < 3:
            return None

        candles_5m = _to_candles([
            {"t": int(idx.timestamp() * 1000), "o": row["Open"], "h": row["High"],
             "l": row["Low"], "c": row["Close"], "v": row["Volume"]}
            for idx, row in intraday.iterrows()
        ])
        candles_1m = _to_candles([
            {"t": int(idx.timestamp() * 1000), "o": row["Open"], "h": row["High"],
             "l": row["Low"], "c": row["Close"], "v": row["Volume"]}
            for idx, row in intraday_1m.iterrows()
        ]) if intraday_1m is not None else []
        daily_candles = _to_candles([
            {"t": int(idx.timestamp() * 1000), "o": row["Open"], "h": row["High"],
             "l": row["Low"], "c": row["Close"], "v": row["Volume"]}
            for idx, row in daily.iterrows()
        ]) if daily is not None else []

        last = candles_5m[-1]
        price = float(last["c"])
        day_high = max(c["h"] for c in candles_5m)
        day_low = min(c["l"] for c in candles_5m)
        current_volume = sum(c["v"] for c in candles_5m)
        prev_close = float(daily_candles[-2]["c"]) if len(daily_candles) >= 2 else None

        # yfinance bid/ask — ko'pincha ishonchsiz; fast_info dan urinib ko'ramiz
        bid = ask = None
        try:
            fi = getattr(tk, "fast_info", {}) or {}
            bid = fi.get("bid") or fi.get("last_price")
            ask = fi.get("ask")
        except Exception:
            bid = ask = None

        return {
            "ticker": ticker.upper(),
            "price": price,
            "prev_close": prev_close,
            "current_volume": current_volume,
            "avg_20d_volume": indicators.avg_volume_from_daily(daily_candles, 20),
            "bid": bid,
            "ask": ask,
            "candles_5m": candles_5m,
            "candles_1m": candles_1m,
            "day_high": day_high,
            "day_low": day_low,
            "source": "yfinance",
            "data_complete": (ask is not None and bid is not None),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Alpaca (kalit bo'lsa) — realtime quote bilan bid/ask
# ---------------------------------------------------------------------------

def _alpaca_available() -> bool:
    return bool(os.getenv("ALPACA_API_KEY", "").strip() and os.getenv("ALPACA_SECRET_KEY", "").strip())


def _alpaca_fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """Alpaca market data — 5m/1m bars + latest quote (bid/ask). Kalit yo'q bo'lsa None."""
    if not _alpaca_available():
        return None
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        key = os.getenv("ALPACA_API_KEY", "").strip()
        sec = os.getenv("ALPACA_SECRET_KEY", "").strip()
        client = StockHistoricalDataClient(key, sec)

        def _bars(amount: int, unit: TimeFrameUnit, limit: int) -> List[Dict[str, Any]]:
            req = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame(amount, unit),
                limit=limit,
            )
            bars = client.get_stock_bars(req)
            rows: List[Dict[str, Any]] = []
            data = getattr(bars, "data", {}) or {}
            for b in data.get(ticker, []):
                rows.append({
                    "t": int(b.timestamp.timestamp() * 1000),
                    "o": b.open, "h": b.high, "l": b.low, "c": b.close, "v": b.volume,
                })
            return _to_candles(rows)

        candles_5m = _bars(5, TimeFrameUnit.Minute, 80)
        candles_1m = _bars(1, TimeFrameUnit.Minute, 120)
        daily = _bars(1, TimeFrameUnit.Day, 25)
        if not candles_5m:
            return None

        # latest quote -> bid/ask
        bid = ask = None
        try:
            q = client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker))
            qd = q.get(ticker) if isinstance(q, dict) else None
            if qd is not None:
                bid = float(getattr(qd, "bid_price", 0) or 0) or None
                ask = float(getattr(qd, "ask_price", 0) or 0) or None
        except Exception:
            bid = ask = None

        last = candles_5m[-1]
        price = float(last["c"])
        return {
            "ticker": ticker.upper(),
            "price": price,
            "prev_close": float(daily[-2]["c"]) if len(daily) >= 2 else None,
            "current_volume": sum(c["v"] for c in candles_5m),
            "avg_20d_volume": indicators.avg_volume_from_daily(daily, 20),
            "bid": bid,
            "ask": ask,
            "candles_5m": candles_5m,
            "candles_1m": candles_1m,
            "day_high": max(c["h"] for c in candles_5m),
            "day_low": min(c["l"] for c in candles_5m),
            "source": "alpaca",
            "data_complete": (bid is not None and ask is not None),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IBKR Web API (placeholder — ulangan bo'lsa ishlatiladi)
# ---------------------------------------------------------------------------

def _ibkr_fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """IBKR Client Portal Web API placeholder. IBKR_WEB_API_ENABLED bo'lsa urinadi."""
    if os.getenv("IBKR_WEB_API_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        # Loyihaning mavjud IBKR Web API moduli bo'lsa, undan foydalanamiz
        from agents.ibkr_web_api import fetch_ibkr_web_daily_candles, fetch_ibkr_web_snapshot

        snap = fetch_ibkr_web_snapshot(ticker)
        if not snap:
            return None
        daily = fetch_ibkr_web_daily_candles(ticker, 25)
        # IBKR Web snapshot intraday bermaydi — 5m yo'q, shuning uchun watchlist sifatida
        return {
            "ticker": ticker.upper(),
            "price": snap.get("price"),
            "prev_close": snap.get("previous_close"),
            "current_volume": snap.get("volume", 0),
            "avg_20d_volume": indicators.avg_volume_from_daily(daily, 20),
            "bid": None, "ask": None,
            "candles_5m": [],  # intraday yo'q -> data_complete False
            "candles_1m": [],
            "day_high": snap.get("today_high"),
            "day_low": snap.get("today_low"),
            "source": "ibkr_web",
            "data_complete": False,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Asosiy: manba tanlash + fallback
# ---------------------------------------------------------------------------

def fetch_ticker(ticker: str, *, preferred: str = "auto") -> Optional[Dict[str, Any]]:
    """Bitta ticker uchun raw ma'lumot. preferred: auto / alpaca / ibkr / yfinance."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None

    order: List[str]
    if preferred == "alpaca":
        order = ["alpaca", "yfinance"]
    elif preferred == "ibkr":
        order = ["ibkr", "alpaca", "yfinance"]
    elif preferred == "yfinance":
        order = ["yfinance"]
    else:  # auto
        order = ["alpaca", "ibkr", "yfinance"]

    fetchers = {"alpaca": _alpaca_fetch, "ibkr": _ibkr_fetch, "yfinance": _yf_fetch}
    for name in order:
        data = fetchers[name](sym)
        if data and data.get("price"):
            return data
    return None


def fetch_market_regime(preferred: str = "auto") -> Dict[str, Any]:
    """SPY va QQQ bo'yicha bozor rejimi: bullish / bearish / choppy."""
    from . import config

    results: Dict[str, Any] = {}
    bullish_count = 0
    valid = 0
    for sym in config.MARKET_REGIME_SYMBOLS:
        data = fetch_ticker(sym, preferred=preferred)
        if not data or not data.get("candles_5m"):
            results[sym] = {"ok": False}
            continue
        valid += 1
        ind = indicators.compute_indicators(
            price=data["price"], prev_close=data.get("prev_close"),
            current_volume=data.get("current_volume", 0),
            avg_20d_volume=data.get("avg_20d_volume", 0),
            bid=data.get("bid"), ask=data.get("ask"),
            candles_5m=data["candles_5m"],
            day_high=data.get("day_high"), day_low=data.get("day_low"),
        )
        price = ind["price"]
        vwap = ind.get("vwap") or 0
        ema9 = ind.get("ema9") or 0
        ema20 = ind.get("ema20") or 0
        above_vwap = price > vwap if vwap else False
        ema_bull = ema9 > ema20 if (ema9 and ema20) else False
        is_bull = above_vwap and ema_bull
        if is_bull:
            bullish_count += 1
        results[sym] = {
            "ok": True, "price": price, "vwap": vwap,
            "above_vwap": above_vwap, "ema_bullish": ema_bull, "bullish": is_bull,
        }

    if valid == 0:
        regime = "UNKNOWN"
    elif bullish_count == valid:
        regime = "BULLISH"
    elif bullish_count == 0:
        regime = "BEARISH"
    else:
        regime = "CHOPPY"

    results["regime"] = regime
    results["bullish"] = regime == "BULLISH"
    results["choppy"] = regime == "CHOPPY"
    results["bearish"] = regime == "BEARISH"
    results["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return results
