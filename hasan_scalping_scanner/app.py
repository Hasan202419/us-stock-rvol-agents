"""app.py — Hasan Auto-Refresh Scalping Signal Scanner (Streamlit).

XAVFSIZLIK: bu tizim REAL ORDER QO'YMAYDI. Auto-buy yo'q, auto-sell yo'q,
jonli ijro yo'q. V1 — faqat signal va paper-review. Standart qaror QAT'IY:
setup toza bo'lmasa NO_TRADE.

Ishga tushirish (Windows):
    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# Loyiha papkasini import yo'liga qo'shamiz (to'g'ridan-to'g'ri `streamlit run app.py` uchun)
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from hasan_scalping_scanner import config, data_source, indicators, risk_lock, strategy  # noqa: E402

st.set_page_config(page_title="Hasan Scalping Scanner", layout="wide", initial_sidebar_state="expanded")


def _now_str() -> str:
    try:
        tz = ZoneInfo("Asia/Tashkent")
    except Exception:
        tz = None
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ Sozlamalar")
st.sidebar.caption("Hasan Auto-Refresh Scalping Signal Scanner — signal-only, order YO'Q.")

source = st.sidebar.selectbox("Ma'lumot manbai", ["auto", "alpaca", "ibkr", "yfinance"], index=0)

refresh_label = st.sidebar.selectbox(
    "Yangilanish oralig'i",
    list(config.REFRESH_OPTIONS.keys()),
    index=list(config.REFRESH_OPTIONS.keys()).index(config.DEFAULT_REFRESH_LABEL),
)
refresh_sec = config.REFRESH_OPTIONS[refresh_label]

scan_now = st.sidebar.button("🔄 Scan Now (hozir skanla)", use_container_width=True)

st.sidebar.divider()
st.sidebar.subheader("Filtrlar")
price_min = st.sidebar.number_input("Narx min ($)", value=config.PRICE_MIN, step=0.1)
price_max = st.sidebar.number_input("Narx max ($)", value=config.PRICE_MAX, step=0.1)
vol_min = st.sidebar.number_input("Joriy hajm min", value=config.MIN_CURRENT_VOLUME, step=100_000)
rvol_min = st.sidebar.number_input("RVOL min", value=config.MIN_RVOL, step=0.5)
dvol_min = st.sidebar.number_input("Dollar volume min ($)", value=config.MIN_DOLLAR_VOLUME, step=100_000)
spread_max = st.sidebar.number_input("Spread max (%)", value=config.MAX_SPREAD_PCT, step=0.5)
chg_min = st.sidebar.number_input("% o'zgarish min", value=config.MIN_CHANGE_PCT, step=1.0)
chg_max = st.sidebar.number_input("% o'zgarish max", value=config.MAX_CHANGE_PCT, step=1.0)

# Runtime override (config qiymatlarini sidebar bilan almashtiramiz)
config.PRICE_MIN, config.PRICE_MAX = price_min, price_max
config.MIN_CURRENT_VOLUME = vol_min
config.MIN_RVOL = rvol_min
config.MIN_DOLLAR_VOLUME = dvol_min
config.MAX_SPREAD_PCT = spread_max
config.MIN_CHANGE_PCT, config.MAX_CHANGE_PCT = chg_min, chg_max

st.sidebar.divider()
watchlist_raw = st.sidebar.text_area(
    "Kuzatuv tickerlari (vergul/probel bilan)",
    value=", ".join(config.DEFAULT_WATCHLIST),
    height=90,
)
watchlist = [t.strip().upper() for t in watchlist_raw.replace("\n", ",").replace(" ", ",").split(",") if t.strip()]

# ---------------------------------------------------------------------------
# RISK LOCK (psixologik himoya)
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("🛡️ Risk-lock")
trades_today = st.sidebar.number_input("Bugungi savdolar", value=0, min_value=0, step=1)
consecutive_losses = st.sidebar.number_input("Ketma-ket zarar", value=0, min_value=0, step=1)
daily_pnl = st.sidebar.number_input("Kunlik P&L ($)", value=0.0, step=5.0)
st.sidebar.caption("Halollik bilan belgilang — bu sizni himoya qiladi:")
feel_tired = st.sidebar.checkbox("Charchaganman")
feel_emotional = st.sidebar.checkbox("Emotsionalman")
feel_angry = st.sidebar.checkbox("Asabiyman / jahlim chiqqan")
feel_confused = st.sidebar.checkbox("Chalkashganman")
want_recover = st.sidebar.checkbox("Zararni qoplamoqchiman")

risk_state = risk_lock.RiskState(
    trades_today=int(trades_today),
    consecutive_losses=int(consecutive_losses),
    daily_pnl=float(daily_pnl),
    feeling_tired=feel_tired,
    feeling_emotional=feel_emotional,
    feeling_angry=feel_angry,
    feeling_confused=feel_confused,
    wants_to_recover_losses=want_recover,
)
trading_allowed, risk_status, risk_reasons = risk_lock.evaluate_risk_lock(risk_state)

# ---------------------------------------------------------------------------
# AUTO REFRESH
# ---------------------------------------------------------------------------
if refresh_sec > 0:
    try:
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=refresh_sec * 1000, key="auto_refresh")
    except Exception:
        # Paket yo'q bo'lsa — meta-refresh fallback
        st.markdown(
            f'<meta http-equiv="refresh" content="{refresh_sec}">',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.title("📈 Hasan Auto-Refresh Scalping Signal Scanner")
st.caption(
    "⚠️ Bu tizim REAL ORDER QO'YMAYDI. Faqat signal + paper-review. "
    "Standart qaror qat'iy: setup toza bo'lmasa NO_TRADE."
)

col_a, col_b, col_c = st.columns([2, 2, 3])
col_a.metric("Oxirgi yangilanish", _now_str())
col_b.metric("Manba", source)
col_c.metric("Yangilanish", refresh_label)

# RISK-LOCK paneli
if not trading_allowed:
    st.error("🛑 **STOP_TRADING** — bugun yangi setup tavsiya etilmaydi:")
    for r in risk_reasons:
        st.write(f"- {r}")
else:
    st.success("🛡️ Risk-lock toza: manual review (paper) uchun ruxsat — bu BUY emas.")
st.caption(risk_lock.risk_budget_line(risk_state))

# ---------------------------------------------------------------------------
# MARKET REGIME (SPY / QQQ)
# ---------------------------------------------------------------------------
st.subheader("🌐 Bozor rejimi (SPY / QQQ)")


@st.cache_data(ttl=20, show_spinner=False)
def _cached_regime(src: str, nonce: int):
    return data_source.fetch_market_regime(preferred=src)


_nonce = int(datetime.now().timestamp() // max(1, refresh_sec or 30))
if scan_now:
    _cached_regime.clear()
try:
    regime = _cached_regime(source, _nonce)
except Exception as exc:  # noqa: BLE001
    regime = {"regime": "UNKNOWN", "bullish": False, "choppy": False, "bearish": False}
    st.warning(f"Bozor ma'lumoti olinmadi: {exc}")

regime_name = regime.get("regime", "UNKNOWN")
regime_color = {"BULLISH": "🟢", "CHOPPY": "🟡", "BEARISH": "🔴", "UNKNOWN": "⚪"}.get(regime_name, "⚪")
rc1, rc2, rc3 = st.columns(3)
rc1.metric("Rejim", f"{regime_color} {regime_name}")
for sym, col in (("SPY", rc2), ("QQQ", rc3)):
    info = regime.get(sym, {})
    if info.get("ok"):
        txt = "🟢 bullish" if info.get("bullish") else ("VWAP↑" if info.get("above_vwap") else "VWAP↓")
        col.metric(sym, txt, f"px {info.get('price')}")
    else:
        col.metric(sym, "—", "ma'lumot yo'q")

# ---------------------------------------------------------------------------
# SCAN
# ---------------------------------------------------------------------------
st.subheader("🎯 Signal jadvali")


def _scan_one(ticker: str) -> dict | None:
    raw = data_source.fetch_ticker(ticker, preferred=source)
    if not raw or not raw.get("candles_5m"):
        # Ma'lumot yo'q/kechikkan -> watchlist sifatida ko'rsatamiz
        return {
            "ticker": ticker, "price": raw.get("price") if raw else None,
            "decision": "WATCHLIST", "score": 0,
            "reason": "Ma'lumot yo'q yoki intraday kelmadi (WATCHLIST only)",
            "mistake_warning": "Ma'lumot to'liq emas — paper-ready bloklangan",
            "vwap_status": "—", "ema_status": "—",
            "_change_pct": None, "_rvol": None, "_dvol": None, "_spread": None,
            "_avg_vol": None, "_cur_vol": None, "_spike": None,
            "entry": None, "stop_loss": None, "target1": None, "target2": None, "risk_reward": None,
        }
    ind = indicators.compute_indicators(
        price=raw["price"], prev_close=raw.get("prev_close"),
        current_volume=raw.get("current_volume", 0),
        avg_20d_volume=raw.get("avg_20d_volume", 0),
        bid=raw.get("bid"), ask=raw.get("ask"),
        candles_5m=raw["candles_5m"],
        day_high=raw.get("day_high"), day_low=raw.get("day_low"),
    )
    ind["ticker"] = ticker
    ind["_candles_5m"] = raw["candles_5m"]
    sig = strategy.evaluate(
        ind,
        market_bullish=regime.get("bullish", False),
        market_choppy=regime.get("choppy", False),
        market_bearish=regime.get("bearish", False),
        data_complete=raw.get("data_complete", False),
    )
    sig["price"] = ind["price"]
    sig["_change_pct"] = ind.get("change_pct")
    sig["_rvol"] = ind.get("rvol")
    sig["_dvol"] = ind.get("dollar_volume")
    sig["_spread"] = ind.get("spread_pct")
    sig["_avg_vol"] = ind.get("avg_20d_volume")
    sig["_cur_vol"] = ind.get("current_volume")
    sig["_spike"] = ind.get("vol_spike_ratio")
    # Risk-lock STOP bo'lsa — barcha qarorni STOP_TRADING ga aylantiramiz
    if not trading_allowed:
        sig["decision"] = "STOP_TRADING"
    return sig


@st.cache_data(ttl=20, show_spinner=True)
def _cached_scan(src: str, tickers: tuple, nonce: int):
    return [s for t in tickers if (s := _scan_one(t)) is not None]


if scan_now:
    _cached_scan.clear()

try:
    signals = _cached_scan(source, tuple(watchlist), _nonce)
except Exception as exc:  # noqa: BLE001
    signals = []
    st.error(f"Skan xatosi: {exc}")

if not signals:
    st.info("Hozircha signal yo'q. Tickerlarni tekshiring yoki **Scan Now** bosing.")
else:
    rows = []
    for s in signals:
        rows.append({
            "Ticker": s.get("ticker"),
            "Price": s.get("price"),
            "% Change": s.get("_change_pct"),
            "Volume": s.get("_cur_vol"),
            "Avg Volume": s.get("_avg_vol"),
            "RVOL": s.get("_rvol"),
            "Dollar Volume": s.get("_dvol"),
            "Spread %": s.get("_spread") if s.get("_spread") is not None else "UNKNOWN",
            "VWAP Status": s.get("vwap_status"),
            "EMA Status": s.get("ema_status"),
            "Vol Spike": s.get("_spike"),
            "Score": s.get("score"),
            "Decision": s.get("decision"),
            "Entry Idea": s.get("entry"),
            "Stop Loss": s.get("stop_loss"),
            "Target 1": s.get("target1"),
            "Target 2": s.get("target2"),
            "R/R": s.get("risk_reward"),
            "Reason": s.get("reason"),
            "Mistake Warning": s.get("mistake_warning"),
        })
    df = pd.DataFrame(rows)

    def _color_decision(val: str) -> str:
        colors = {
            "NO_TRADE": "background-color: #5c1a1a; color: white;",
            "WATCHLIST": "background-color: #5c531a; color: white;",
            "PAPER_READY": "background-color: #1a5c2a; color: white;",
            "HIGH_QUALITY_PAPER_READY": "background-color: #0f7a30; color: white; font-weight: bold;",
            "STOP_TRADING": "background-color: #2b0000; color: #ff6b6b; font-weight: bold;",
        }
        return colors.get(val, "")

    styled = df.style.map(_color_decision, subset=["Decision"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # PAPER_READY alertlari (matn tayyor — Telegram hali yuborilmaydi)
    ready = [s for s in signals if str(s.get("decision", "")).endswith("PAPER_READY")]
    if ready and trading_allowed:
        st.subheader("🚨 Paper-ready alertlar (manual review)")
        for s in ready:
            st.code(risk_lock.build_alert_text(s), language="text")

st.divider()
st.caption(
    "Eslatma: HIGH_QUALITY_PAPER_READY ham avtomatik BUY emas — faqat manual review ruxsati. "
    "Yomon savdodan ko'ra savdoni o'tkazib yuborish yaxshiroq."
)
