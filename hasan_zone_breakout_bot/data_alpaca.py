"""data_alpaca.py — Alpaca market data (birinchi oson manba).

Multi-timeframe bars (1H/5M/3M/1M) + latest quote (bid/ask). `alpaca-py` kerak va
ALPACA_API_KEY/ALPACA_SECRET_KEY bo'lishi kerak; bo'lmasa None qaytadi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config


def available() -> bool:
    return bool(config.ALPACA_API_KEY and config.ALPACA_SECRET_KEY)


def fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """Alpaca'dan bitta ticker uchun bars + quote. Xato/kalitsiz bo'lsa None."""
    if not available():
        return None
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)

        def _bars(amount: int, unit: TimeFrameUnit, limit: int) -> List[Dict[str, Any]]:
            req = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame(amount, unit),
                limit=limit,
            )
            resp = client.get_stock_bars(req)
            data = getattr(resp, "data", {}) or {}
            rows: List[Dict[str, Any]] = []
            for b in data.get(ticker, []):
                rows.append({
                    "t": int(b.timestamp.timestamp() * 1000),
                    "o": float(b.open), "h": float(b.high), "l": float(b.low),
                    "c": float(b.close), "v": float(b.volume),
                })
            rows.sort(key=lambda x: x["t"])
            return rows

        c60 = _bars(1, TimeFrameUnit.Hour, 60)
        c5 = _bars(5, TimeFrameUnit.Minute, 80)
        c3 = _bars(3, TimeFrameUnit.Minute, 100)
        c1 = _bars(1, TimeFrameUnit.Minute, 120)
        daily = _bars(1, TimeFrameUnit.Day, 25)
        if len(c5) < 5:
            return None

        bid = ask = None
        try:
            q = client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker))
            qd = q.get(ticker) if isinstance(q, dict) else None
            if qd is not None:
                bid = float(getattr(qd, "bid_price", 0) or 0) or None
                ask = float(getattr(qd, "ask_price", 0) or 0) or None
        except Exception:
            bid = ask = None

        from .indicators import avg_volume_from_daily

        last = c5[-1]
        return {
            "ticker": ticker.upper(),
            "price": float(last["c"]),
            "prev_close": float(daily[-2]["c"]) if len(daily) >= 2 else None,
            "current_volume": sum(c["v"] for c in c5),
            "avg_20d_volume": avg_volume_from_daily(daily, 20),
            "bid": bid, "ask": ask,
            "candles_1h": c60,
            "candles_5m": c5,
            "candles_3m": c3,
            "candles_1m": c1,
            "day_high": max(c["h"] for c in c5),
            "day_low": min(c["l"] for c in c5),
            "source": "alpaca",
            "data_complete": (bid is not None and ask is not None),
        }
    except Exception:
        return None
