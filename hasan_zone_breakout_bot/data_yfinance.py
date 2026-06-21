"""data_yfinance.py — bepul zaxira ma'lumot (faqat test uchun).

yfinance 3m intervalni bermaydi -> 1m dan resample qilinadi. Realtime emas
(odatda kechikkan), shuning uchun `data_complete=False` (HIGH_QUALITY bo'lmaydi).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _candles_from_df(df) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if df is None:
        return out
    for idx, row in df.iterrows():
        try:
            c = float(row["Close"])
            if c <= 0:
                continue
            out.append({
                "t": int(idx.timestamp() * 1000),
                "o": float(row["Open"]), "h": float(row["High"]),
                "l": float(row["Low"]), "c": c, "v": float(row["Volume"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["t"])
    return out


def _resample_3m(candles_1m: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """1m shamlardan 3m yasaydi (yfinance 3m bermaydi)."""
    out: List[Dict[str, Any]] = []
    for i in range(0, len(candles_1m) - 2, 3):
        chunk = candles_1m[i:i + 3]
        if len(chunk) < 3:
            break
        out.append({
            "t": chunk[0]["t"],
            "o": chunk[0]["o"],
            "h": max(x["h"] for x in chunk),
            "l": min(x["l"] for x in chunk),
            "c": chunk[-1]["c"],
            "v": sum(x["v"] for x in chunk),
        })
    return out


def fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """yfinance orqali multi-timeframe shamlar + kunlik o'rtacha hajm."""
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        c5 = _candles_from_df(tk.history(period="2d", interval="5m", auto_adjust=False))
        c1 = _candles_from_df(tk.history(period="1d", interval="1m", auto_adjust=False))
        c60 = _candles_from_df(tk.history(period="1mo", interval="1h", auto_adjust=False))
        daily = _candles_from_df(tk.history(period="2mo", interval="1d", auto_adjust=False))
        if len(c5) < 5:
            return None
        c3 = _resample_3m(c1) if c1 else []

        last = c5[-1]
        price = float(last["c"])
        # bid/ask — yfinance da ko'pincha ishonchsiz
        bid = ask = None
        try:
            fi = getattr(tk, "fast_info", {}) or {}
            bid = fi.get("bid")
            ask = fi.get("ask")
        except Exception:
            bid = ask = None

        from .indicators import avg_volume_from_daily

        return {
            "ticker": ticker.upper(),
            "price": price,
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
            "source": "yfinance",
            "data_complete": False,  # yfinance kechikkan -> HIGH_QUALITY bermaydi
        }
    except Exception:
        return None
