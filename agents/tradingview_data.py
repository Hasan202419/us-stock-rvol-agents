"""TradingView texnik tahlil ma'lumotlari (tradingview-ta kutubxonasi orqali).

TradingView'ning ochiq "scanner" endpointidan har bir ticker uchun **tavsiya**
(STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL) va indikatorlarni (RSI, MACD,
EMA20, close, change, volume) oladi. Istalgan timeframe — 1m/5m skalp uchun ham.

Tarmoqqa bog'liq (TradingView serveri) — Render'da ishlaydi. Testlarda
`TA_Handler` mock qilinadi.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# TradingView interval kodlari (tradingview_ta.Interval bilan mos).
_INTERVAL_MAP: Dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d",
    "1day": "1d",
    "daily": "1d",
    "1w": "1W",
    "1week": "1W",
}

# US aksiyalari uchun sinab ko'riladigan birjalar (birinchi muvaffaqiyatli ishlatiladi).
_US_EXCHANGES: tuple[str, ...] = ("NASDAQ", "NYSE", "AMEX")

_REC_BADGE: Dict[str, str] = {
    "STRONG_BUY": "🟢🟢 KUCHLI BUY",
    "BUY": "🟢 BUY",
    "NEUTRAL": "⚪ NEYTRAL",
    "SELL": "🔴 SELL",
    "STRONG_SELL": "🔴🔴 KUCHLI SELL",
}


def normalize_interval(value: str) -> str:
    """Foydalanuvchi intervalini tradingview_ta interval kodiga aylantiradi."""
    key = (value or "").strip().lower()
    return _INTERVAL_MAP.get(key, "5m")


def tv_recommendation_badge(recommendation: Optional[str]) -> str:
    """Tavsiya kalitiga emoji/ko'rinish."""
    return _REC_BADGE.get(str(recommendation or "").upper(), "⚪ NEYTRAL")


def _f(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        v = float(value)
        return None if v != v else round(v, 4)  # NaN tekshiruvi
    except (TypeError, ValueError):
        return None


def _exchange_list() -> List[str]:
    raw = os.getenv("TRADINGVIEW_EXCHANGES", "").strip()
    if raw:
        return [e.strip().upper() for e in raw.split(",") if e.strip()]
    return list(_US_EXCHANGES)


def fetch_tv_analysis(
    ticker: str,
    *,
    interval: str = "5m",
    screener: str = "america",
    exchanges: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """TradingView tahlilini *ticker* uchun olib, soddalashtirilgan dict qaytaradi.

    Birjalarni navbatma-navbat sinaydi (NASDAQ → NYSE → AMEX); birinchi
    muvaffaqiyatli javob qaytadi. Xato/topilmasa None.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    if ":" in sym:  # "NASDAQ:AAPL" — birjasi aniq berilgan
        exch, sym = sym.split(":", 1)
        exchanges = [exch]

    tv_interval = normalize_interval(interval)
    candidates = exchanges if exchanges is not None else _exchange_list()

    try:
        from tradingview_ta import TA_Handler  # lazy — barcha muhitda yo'q
    except ImportError:
        return None

    for exch in candidates:
        try:
            handler = TA_Handler(
                symbol=sym,
                screener=screener,
                exchange=exch,
                interval=tv_interval,
            )
            analysis = handler.get_analysis()
            if analysis is None:
                continue
            summary = analysis.summary or {}
            ind = analysis.indicators or {}
            return {
                "ticker": sym,
                "exchange": exch,
                "interval": tv_interval,
                "recommendation": str(summary.get("RECOMMENDATION") or "NEUTRAL").upper(),
                "buy": int(summary.get("BUY") or 0),
                "sell": int(summary.get("SELL") or 0),
                "neutral": int(summary.get("NEUTRAL") or 0),
                "oscillators": (analysis.oscillators or {}).get("RECOMMENDATION"),
                "moving_averages": (analysis.moving_averages or {}).get("RECOMMENDATION"),
                "rsi": _f(ind.get("RSI")),
                "macd": _f(ind.get("MACD.macd")),
                "macd_signal": _f(ind.get("MACD.signal")),
                "close": _f(ind.get("close")),
                "change": _f(ind.get("change")),
                "volume": _f(ind.get("volume")),
                "ema20": _f(ind.get("EMA20")),
                "ema50": _f(ind.get("EMA50")),
            }
        except Exception:  # noqa: BLE001 — birja mos kelmasa keyingisini sinaymiz
            continue
    return None


def tv_signal_line(data: Optional[Dict[str, Any]]) -> str:
    """TradingView tahlilidan bir qatorli HTML (Telegram)."""
    if not data:
        return ""
    badge = tv_recommendation_badge(data.get("recommendation"))
    buy = data.get("buy", 0)
    sell = data.get("sell", 0)
    neu = data.get("neutral", 0)
    interval = data.get("interval", "")
    rsi = data.get("rsi")
    rsi_txt = f" · RSI {rsi:.0f}" if isinstance(rsi, (int, float)) else ""
    exch = data.get("exchange", "")
    return (
        f"<b>TradingView</b> ({interval}): {badge} "
        f"<i>(↑{buy}/↓{sell}/={neu}{rsi_txt})</i> · <code>{exch}:{data.get('ticker')}</code>"
    )
