"""config.py — Hasan Auto-Refresh Scalping Signal Scanner sozlamalari.

Barcha chegaralar (filtrlar), risk-lock qiymatlari va ballash (scoring) shu yerda.
Hech qanday real order YO'Q — bu fayl faqat raqamlarni saqlaydi.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# NARX (Price) filtri — $0.50 .. $5.00
# ---------------------------------------------------------------------------
PRICE_MIN = 0.50
PRICE_MAX = 5.00

# ---------------------------------------------------------------------------
# HAJM (Volume) filtri
# ---------------------------------------------------------------------------
MIN_CURRENT_VOLUME = 1_000_000     # bugungi joriy hajm
MIN_AVG_20D_VOLUME = 500_000       # 20-kunlik o'rtacha hajm
MIN_RVOL = 2.0                     # majburiy minimal RVOL
STRONG_RVOL = 3.0                  # qo'shimcha ball uchun

# ---------------------------------------------------------------------------
# DOLLAR VOLUME = narx × joriy hajm
# ---------------------------------------------------------------------------
MIN_DOLLAR_VOLUME = 500_000

# ---------------------------------------------------------------------------
# % O'ZGARISH (Change) — +3% .. +20%
# ---------------------------------------------------------------------------
MIN_CHANGE_PCT = 3.0
MAX_CHANGE_PCT = 20.0

# ---------------------------------------------------------------------------
# SPREAD — (ask - bid) / last × 100, maksimal 2%
# ---------------------------------------------------------------------------
MAX_SPREAD_PCT = 2.0

# ---------------------------------------------------------------------------
# VOLUME-TIME (5-min hajm portlashi koeffitsiyenti)
# ---------------------------------------------------------------------------
VOL_SPIKE_NORMAL = 1.0
VOL_SPIKE_STRONG = 1.5
VOL_SPIKE_IGNITION = 3.0
MIN_VOL_SPIKE_FOR_SIGNAL = 1.5     # signal uchun kamida "strong"

# ---------------------------------------------------------------------------
# VWAP extension — narx VWAP'dan qancha uzoqlashsa "chased" hisoblanadi (%)
# ---------------------------------------------------------------------------
MAX_VWAP_EXTENSION_PCT = 4.0

# ---------------------------------------------------------------------------
# RISK / REWARD
# ---------------------------------------------------------------------------
MIN_RISK_REWARD = 2.0              # kamida 1:2

# ---------------------------------------------------------------------------
# BALL (Score) -> QAROR (Decision)
# ---------------------------------------------------------------------------
SCORE_MAX = 10
DECISION_THRESHOLDS = {
    "NO_TRADE": (0, 4),
    "WATCHLIST": (5, 6),
    "PAPER_READY": (7, 8),
    "HIGH_QUALITY_PAPER_READY": (9, 10),
}

# ---------------------------------------------------------------------------
# RISK-LOCK (prop-uslub himoya qoidalari)
# ---------------------------------------------------------------------------
MAX_TRADES_PER_DAY = 3
RISK_PER_TRADE_MIN = 10.0          # o'rganish bosqichida $10..$20
RISK_PER_TRADE_MAX = 20.0
DAILY_SOFT_STOP = -50.0            # yumshoq to'xtash
DAILY_HARD_STOP = -70.0           # qattiq to'xtash
MAX_CONSECUTIVE_LOSSES = 2         # ketma-ket 2 zarar -> to'xta

# ---------------------------------------------------------------------------
# AUTO-REFRESH (avtomatik yangilanish) — soniyalarda
# ---------------------------------------------------------------------------
REFRESH_OPTIONS = {"30 soniya": 30, "60 soniya": 60, "Qo'lda (manual)": 0}
DEFAULT_REFRESH_LABEL = "60 soniya"

# ---------------------------------------------------------------------------
# DEFAULT kuzatuv ro'yxati (low-float scalp nomzodlari namunasi)
# ---------------------------------------------------------------------------
DEFAULT_WATCHLIST = [
    "SNDL", "MARA", "RIOT", "PLUG", "FCEL", "SOFI",
    "NIO", "BBD", "GRAB", "RIG", "AMC", "GERN",
]

# Bozor rejimi uchun benchmark
MARKET_REGIME_SYMBOLS = ["SPY", "QQQ"]

# Ruxsat etilgan birjalar (OTC / Pink Sheets chiqarib tashlanadi)
ALLOWED_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "NASDAQ", "NYSE", "AMEX", "ARCA"}
