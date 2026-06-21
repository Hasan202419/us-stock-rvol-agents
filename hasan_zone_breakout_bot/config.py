"""config.py — Hasan Zone Breakout VWAP Scalping Signal Bot sozlamalari.

Barcha chegaralar, ikki skaner rejimi, scoring, qaror (decision) bosqichlari va
risk-lock qiymatlari shu yerda. Hech qanday real order YO'Q — faqat signal.

.env dan kalitlar o'qiladi (python-dotenv). Maxfiy kalitlar kodda yozilmaydi.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # .env faylni o'qiydi (bo'lmasa jim o'tadi)
except Exception:
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# KALITLAR (.env dan) — kodga yozilmaydi
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = _env("ALPACA_API_KEY")
ALPACA_SECRET_KEY = _env("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ---------------------------------------------------------------------------
# AUTO-REFRESH
# ---------------------------------------------------------------------------
REFRESH_SECONDS = _env_int("REFRESH_SECONDS", 60)
SCAN_MODE = _env("SCAN_MODE", "both").lower()  # large_cap / penny / both

# ---------------------------------------------------------------------------
# MODE 1 — Large Cap Quality Scanner
# ---------------------------------------------------------------------------
LARGE_CAP_WATCHLIST = [
    "AAPL", "NVDA", "TSLA", "AMD", "MSFT", "META", "GOOGL",
    "AMZN", "AVGO", "PLTR", "SOFI", "ARM", "QQQ", "SPY",
]

# ---------------------------------------------------------------------------
# MODE 2 — Penny Momentum Scanner (filtrlar)
# ---------------------------------------------------------------------------
PENNY_PRICE_MIN = _env_float("PENNY_PRICE_MIN", 0.50)
PENNY_PRICE_MAX = _env_float("PENNY_PRICE_MAX", 5.00)
PENNY_MIN_CURRENT_VOLUME = _env_int("PENNY_MIN_CURRENT_VOLUME", 1_000_000)
PENNY_MIN_AVG_20D_VOLUME = _env_int("PENNY_MIN_AVG_20D_VOLUME", 500_000)
PENNY_MIN_RVOL = _env_float("PENNY_MIN_RVOL", 2.0)
PENNY_STRONG_RVOL = _env_float("PENNY_STRONG_RVOL", 3.0)
PENNY_MIN_DOLLAR_VOLUME = _env_float("PENNY_MIN_DOLLAR_VOLUME", 500_000)
PENNY_MIN_CHANGE_PCT = _env_float("PENNY_MIN_CHANGE_PCT", 3.0)
PENNY_MAX_CHANGE_PCT = _env_float("PENNY_MAX_CHANGE_PCT", 20.0)
PENNY_MAX_SPREAD_PCT = _env_float("PENNY_MAX_SPREAD_PCT", 2.0)
# Penny momentum nomzodlari (namuna — o'zgartirish mumkin: PENNY_WATCHLIST=...)
_penny_raw = _env("PENNY_WATCHLIST")
PENNY_WATCHLIST = (
    [t.strip().upper() for t in _penny_raw.split(",") if t.strip()]
    if _penny_raw
    else ["SNDL", "PLUG", "FCEL", "GERN", "BBD", "NIO", "GRAB", "RIG", "MARA", "RIOT"]
)

# ---------------------------------------------------------------------------
# UMUMIY filtrlar
# ---------------------------------------------------------------------------
MAX_SPREAD_PCT = _env_float("MAX_SPREAD_PCT", 2.0)
MAX_VWAP_EXTENSION_PCT = _env_float("MAX_VWAP_EXTENSION_PCT", 4.0)
MIN_RISK_REWARD = _env_float("MIN_RISK_REWARD", 2.0)

# ---------------------------------------------------------------------------
# VOLUME-TIME (hajm portlashi koeffitsiyenti)
# ---------------------------------------------------------------------------
VOL_SPIKE_STRONG = 1.5
VOL_SPIKE_IGNITION = 3.0

# ---------------------------------------------------------------------------
# ZONA aniqlash
# ---------------------------------------------------------------------------
ZONE_SWING_LOOKBACK = _env_int("ZONE_SWING_LOOKBACK", 3)       # swing uchun chap/o'ng shamlar
ZONE_ATR_WIDTH_MULT = _env_float("ZONE_ATR_WIDTH_MULT", 0.5)   # zona kengligi = ATR × bu
ZONE_CONSOLIDATION_MIN_BARS = _env_int("ZONE_CONSOLIDATION_MIN_BARS", 6)
ZONE_CONSOLIDATION_MAX_BARS = _env_int("ZONE_CONSOLIDATION_MAX_BARS", 12)
ZONE_CONSOLIDATION_INSIDE_FRAC = _env_float("ZONE_CONSOLIDATION_INSIDE_FRAC", 0.70)
ZONE_BREAKOUT_CLOSE_UPPER_FRAC = _env_float("ZONE_BREAKOUT_CLOSE_UPPER_FRAC", 0.60)  # close upper 40% => >=0.6

# ---------------------------------------------------------------------------
# SCORING (spec) -> har mezon uchun ball
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "in_zone": 2,
    "consolidation": 2,
    "volume_contraction": 1,
    "false_breakdown": 2,
    "zone_breakout": 2,
    "vwap_reclaim": 2,
    "confirm_3m": 1,
    "confirm_5m_vwap": 1,
    "spike_1_5x": 1,
    "spike_3x": 1,
    "ema_bullish": 1,
    "spread_ok": 1,
    "rr_ok": 1,
    "regime_bullish": 1,
    "halal_compliant": 1,
}

# DECISION bosqichlari (spec)
DECISION_THRESHOLDS = {
    "NO_TRADE": (0, 5),
    "WATCHLIST": (6, 8),
    "PAPER_READY": (9, 11),
    "HIGH_QUALITY_PAPER_READY": (12, 999),
}

# Telegramga faqat shu qarorlar yuboriladi
TELEGRAM_ALERT_DECISIONS = {"PAPER_READY", "HIGH_QUALITY_PAPER_READY"}
DEDUP_MINUTES = _env_int("DEDUP_MINUTES", 10)

# ---------------------------------------------------------------------------
# RISK-LOCK (prop himoya)
# ---------------------------------------------------------------------------
MAX_TRADES_PER_DAY = _env_int("MAX_TRADES_PER_DAY", 3)
RISK_PER_TRADE_MIN = _env_float("RISK_PER_TRADE_MIN", 10.0)
RISK_PER_TRADE_MAX = _env_float("RISK_PER_TRADE_MAX", 20.0)
DAILY_SOFT_STOP = _env_float("DAILY_SOFT_STOP", -50.0)
DAILY_HARD_STOP = _env_float("DAILY_HARD_STOP", -70.0)
MAX_CONSECUTIVE_LOSSES = _env_int("MAX_CONSECUTIVE_LOSSES", 2)

# ---------------------------------------------------------------------------
# Fayllar
# ---------------------------------------------------------------------------
SCAN_LOG_CSV = _env("SCAN_LOG_CSV", "scan_log.csv")
ALERTS_LOG_CSV = _env("ALERTS_LOG_CSV", "alerts_log.csv")
HALAL_WATCHLIST_CSV = _env("HALAL_WATCHLIST_CSV", "halal_watchlist.csv")

# Bozor rejimi benchmarklari
MARKET_REGIME_SYMBOLS = ["SPY", "QQQ"]
