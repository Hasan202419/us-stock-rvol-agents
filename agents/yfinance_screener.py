"""yfinance-based scalp / day-trade stock screener.

Tarmoqqa bog'liq (yfinance) — Render muhitida ishlaydi.
Testlarda `_yf_snapshot` mock qilinishi kerak.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Default universe (high-volume US equities / ETFs)
# ---------------------------------------------------------------------------

SCALP_UNIVERSE_DEFAULT: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL",
    "NFLX", "AVGO", "QCOM", "MU", "SMCI", "PLTR", "UBER", "CRM",
    "ORCL", "SHOP", "SOFI", "COIN", "HOOD", "RIVN", "NIO", "INTC",
    "ARM", "AMAT", "LRCX", "MRVL", "ON", "MARA", "RIOT", "BABA",
    "SPY", "QQQ", "IWM", "XLK", "SOXL", "TQQQ", "SQQQ",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _tv_url(ticker: str) -> str:
    sym = ticker.strip().upper()
    if not sym:
        return "https://www.tradingview.com/chart/"
    return f"https://www.tradingview.com/chart/?symbol={quote(sym, safe=':')}"


def _atr_simple(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Simplified ATR from daily candles [{o,h,l,c,v,t}]."""
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        h = float(candles[-i].get("h") or 0)
        lo = float(candles[-i].get("l") or 0)
        pc = float(candles[-i - 1].get("c") or lo)
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return round(sum(trs) / len(trs), 4) if trs else 0.0


# ---------------------------------------------------------------------------
# yfinance snapshot
# ---------------------------------------------------------------------------

def _yf_snapshot(ticker: str, *, period: str = "25d") -> Optional[Dict[str, Any]]:
    """Fetch yfinance daily candles and compute RVOL/gap/change for *ticker*.

    Returns None on any error or insufficient data.
    """
    try:
        import yfinance as yf  # lazy import — not available in all test envs

        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if hist is None or len(hist) < 5:
            return None

        candles: List[Dict[str, Any]] = []
        for dt, row in hist.iterrows():
            try:
                v = float(row.get("Volume") or 0)
                o = float(row.get("Open") or 0)
                h = float(row.get("High") or 0)
                lo = float(row.get("Low") or 0)
                c = float(row.get("Close") or 0)
                if c > 0:
                    candles.append({"t": int(dt.timestamp()), "o": o, "h": h, "l": lo, "c": c, "v": v})
            except Exception:
                continue

        if len(candles) < 5:
            return None

        today = candles[-1]
        prev = candles[-2]

        price = float(today["c"])
        prev_close = float(prev["c"])
        today_open = float(today["o"])
        today_vol = float(today["v"])
        today_high = float(today["h"])
        today_low = float(today["l"])

        volumes = [float(c["v"]) for c in candles]
        lookback_vols = volumes[-21:-1]
        avg_vol = sum(lookback_vols) / len(lookback_vols) if lookback_vols else today_vol
        rvol = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        gap_pct = round((today_open - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0

        day_range = today_high - today_low
        held_gap = (
            price > prev_close
            and (day_range <= 0 or (price - today_low) / day_range >= 0.4)
        )

        atr = _atr_simple(candles)

        return {
            "ticker": ticker.upper(),
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "change_percent": change_pct,
            "gap_pct": gap_pct,
            "held_gap": held_gap,
            "volume": int(today_vol),
            "avg_volume": int(avg_vol),
            "rvol": rvol,
            "atr": atr,
            "today_low": round(today_low, 4),
            "today_high": round(today_high, 4),
            "candles": candles[-30:],
            "tv_url": _tv_url(ticker),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def scalp_score(snap: Dict[str, Any]) -> float:
    """Priority score — higher = better scalp candidate."""
    score = 0.0
    rvol = float(snap.get("rvol") or 1.0)
    chg = float(snap.get("change_percent") or 0.0)
    gap = float(snap.get("gap_pct") or 0.0)
    vol = float(snap.get("volume") or 0.0)
    price = float(snap.get("price") or 0.0)

    # RVOL (most important for momentum/scalping)
    if rvol >= 3.0:
        score += 40.0
    elif rvol >= 2.0:
        score += 25.0
    elif rvol >= 1.5:
        score += 12.0

    # Price momentum (but not over-extended)
    if 0.5 <= chg <= 8.0:
        score += min(18.0, chg * 2.5)
    elif chg > 8.0:
        score += 8.0  # overextended — less ideal

    # Gap-up setup
    if gap >= 3.0:
        score += 15.0
        if snap.get("held_gap"):
            score += 10.0  # held gap = continuation
    elif gap >= 1.0:
        score += 5.0

    # Absolute volume (liquidity for fast fills)
    if vol >= 5_000_000:
        score += 10.0
    elif vol >= 1_000_000:
        score += 5.0

    # Price sweet-spot for scalping
    if 10.0 <= price <= 500.0:
        score += 5.0

    return score


def _setup_type(snap: Dict[str, Any]) -> str:
    gap = float(snap.get("gap_pct") or 0.0)
    rvol = float(snap.get("rvol") or 0.0)
    if gap >= 3.0 and snap.get("held_gap"):
        return "GAP-AND-GO"
    if gap >= 3.0:
        return "GAP (fade risk)"
    if rvol >= 2.5:
        return "RVOL BREAKOUT"
    if rvol >= 1.5:
        return "RVOL MOMENTUM"
    return "WATCHLIST"


def _trade_levels(snap: Dict[str, Any]) -> Dict[str, float]:
    """Simple ATR-based intraday trade levels."""
    price = float(snap.get("price") or 0.0)
    atr = float(snap.get("atr") or 0.0)
    today_low = float(snap.get("today_low") or price * 0.97)

    # SL: wider of ATR×1.5 or day's low (whichever is closer — tighter stop)
    sl_atr = round(price - max(atr * 1.5, price * 0.01), 4)
    sl_low = round(today_low * 0.998, 4)
    sl = max(sl_atr, sl_low)  # tighter stop (higher value = closer to price)
    sl = min(sl, price * 0.99)  # never tighter than 1%

    risk = max(price - sl, price * 0.005)
    min_rr = _env_float("MIN_RISK_REWARD_RATIO", 2.0)
    tp1 = round(price + min_rr * risk, 4)
    tp2 = round(price + (min_rr + 1.0) * risk, 4)
    rr = round((tp1 - price) / risk, 1) if risk > 0 else 0.0

    return {
        "entry": round(price, 2),
        "stop": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "rr": rr,
    }


# ---------------------------------------------------------------------------
# Main screener
# ---------------------------------------------------------------------------

def screen_scalp_candidates(
    universe: Optional[List[str]] = None,
    *,
    min_rvol: float = 1.5,
    min_price: float = 5.0,
    min_volume: int = 500_000,
    top_n: int = 10,
    delay_sec: float = 0.2,
) -> List[Dict[str, Any]]:
    """Screen *universe* for scalp/day-trade setups.

    Returns up to *top_n* candidates sorted by ``scalp_score`` (descending).
    Applies filters: min_rvol, min_price, min_volume.
    """
    if universe is None:
        raw = os.getenv("SCALP_UNIVERSE", "").strip()
        if raw:
            universe = [t.strip().upper() for t in raw.split(",") if t.strip()]
        else:
            universe = list(SCALP_UNIVERSE_DEFAULT)

    results: List[Dict[str, Any]] = []
    for ticker in universe:
        snap = _yf_snapshot(ticker)
        if snap is None:
            continue
        if float(snap.get("price") or 0) < min_price:
            continue
        if int(snap.get("volume") or 0) < min_volume:
            continue
        if float(snap.get("rvol") or 0) < min_rvol:
            continue

        snap["scalp_score"] = round(scalp_score(snap), 1)
        snap["setup_type"] = _setup_type(snap)
        snap["levels"] = _trade_levels(snap)
        results.append(snap)

        if delay_sec > 0:
            time.sleep(delay_sec)

    results.sort(key=lambda x: -float(x.get("scalp_score") or 0))
    return results[:top_n]


def format_scalp_html(candidates: List[Dict[str, Any]]) -> str:
    """Format screener results as Telegram HTML."""
    if not candidates:
        return "🔍 Skalp nomzod topilmadi."

    lines = [f"<b>📊 SKALP SKANER</b> · <b>{len(candidates)}</b> nomzod (yfinance)\n"]
    for i, s in enumerate(candidates, 1):
        t = str(s.get("ticker", "?"))
        price = float(s.get("price") or 0)
        chg = float(s.get("change_percent") or 0)
        gap = float(s.get("gap_pct") or 0)
        rvol = float(s.get("rvol") or 0)
        vol = int(s.get("volume") or 0)
        setup = str(s.get("setup_type") or "")
        tv = str(s.get("tv_url") or "")
        lvl = s.get("levels") or {}

        chg_icon = "🟢" if chg >= 0 else "🔴"
        vol_str = f"{vol / 1_000_000:.1f}M" if vol >= 1_000_000 else f"{vol / 1_000:.0f}K"
        gap_str = f" | Gap {gap:+.1f}%" if abs(gap) >= 0.5 else ""
        entry = lvl.get("entry", price)
        sl = lvl.get("stop", 0)
        tp1 = lvl.get("tp1", 0)
        rr = lvl.get("rr", 0)

        lines.append(
            f"<b>{i}. <code>{t}</code></b> — {setup} {chg_icon}\n"
            f"   💲 ${price:.2f} ({chg:+.1f}%{gap_str})\n"
            f"   📊 RVOL <b>{rvol:.1f}×</b> · Vol {vol_str}\n"
            f"   🎯 Kirish ~{entry} | SL ~{sl} | TP ~{tp1} | R:R {rr:.1f}\n"
            f"   📈 <a href=\"{tv}\">TradingView</a>"
        )

    lines.append("\n<i>ℹ️ Kunlik yfinance ma'lumoti — realtime emas. Kirishdan oldin tasdiqlang.</i>")
    return "\n".join(lines)
