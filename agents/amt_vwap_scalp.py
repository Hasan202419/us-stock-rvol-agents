"""AMT / VWAP value-area uslubidagi scalping BUY (Pine `ta.vwap` + VAL/VAH zonasi) — intraday barlar bo‘yicha.

Pine mantiqiga yaqin:
- `session_len` oxirgi shamarda rolling highest/low
- POC proksi: `cumulative_session_vwap` (typical price * hajm)
- VAH = highest - (highest - poc) * 0.3 ; VAL = lowest + (poc - lowest) * 0.3
- BUY: `crossover(close, val)` yoki `close>val & crossover(close, ema9) & close<poc`
- TP kuzatuv: close >= poc ; kuchli: close >= vah
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agents.indicators import cumulative_session_vwap, ema


def _truthy(raw: str | None, *, default: bool) -> bool:
    s = (raw or "").strip().lower()
    if not s:
        return default
    if s in {"0", "false", "no", "off"}:
        return False
    return s in {"1", "true", "yes", "on"}


def _rolling_max(values: List[float], window: int) -> List[float]:
    n = len(values)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - window + 1)
        out.append(max(values[lo : i + 1]))
    return out


def _rolling_min(values: List[float], window: int) -> List[float]:
    n = len(values)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - window + 1)
        out.append(min(values[lo : i + 1]))
    return out


def compute_amt_vwap_scalp(
    bars: List[Dict[str, Any]],
    *,
    session_len: int = 20,
    ema_len: int = 9,
) -> Dict[str, Any]:
    """Oxirgi sham bo‘yicha BUY / TP zonasi (fakt)."""

    need = max(session_len, ema_len) + 2
    if len(bars) < need:
        return {
            "amt_ok": False,
            "amt_insufficient_bars": True,
            "amt_buy_signal": False,
            "amt_buy_from_val": False,
            "amt_buy_ema_reclaim": False,
            "amt_tp_zone": False,
            "amt_strong_tp_zone": False,
        }

    highs = [float(b.get("h") or 0.0) for b in bars]
    lows = [float(b.get("l") or 0.0) for b in bars]
    closes = [float(b.get("c") or 0.0) for b in bars]

    poc_s = cumulative_session_vwap(bars)
    hi_r = _rolling_max(highs, session_len)
    lo_r = _rolling_min(lows, session_len)

    vah_s: list[float | None] = []
    val_s: list[float | None] = []
    for i in range(len(bars)):
        poc = poc_s[i]
        hp, lp = hi_r[i], lo_r[i]
        if poc is None or poc <= 0:
            vah_s.append(None)
            val_s.append(None)
            continue
        rh = hp - float(poc)
        rl = float(poc) - lp
        vah_s.append(hp - rh * 0.3)
        val_s.append(lp + rl * 0.3)

    ema_s = ema(closes, ema_len)
    n = len(closes)
    i = n - 1
    c0, c1 = closes[i], closes[i - 1]
    v0, v1 = val_s[i], val_s[i - 1]
    e0, e1 = ema_s[i], ema_s[i - 1]
    p0 = poc_s[i]
    h0 = vah_s[i]

    buy_from_val = False
    if v0 is not None and v1 is not None:
        buy_from_val = c1 <= v1 and c0 > v0

    buy_ema_reclaim = False
    if (
        v0 is not None
        and p0 is not None
        and e0 is not None
        and e1 is not None
        and v0 > 0
        and p0 > 0
    ):
        co_ema = c1 <= e1 and c0 > e0
        buy_ema_reclaim = c0 > v0 and co_ema and c0 < float(p0)

    buy_signal = bool(buy_from_val or buy_ema_reclaim)
    tp_zone = bool(p0 is not None and p0 > 0 and c0 >= float(p0))
    strong_tp_zone = bool(h0 is not None and c0 >= float(h0))

    def _r4(x: float | None) -> float | None:
        if x is None:
            return None
        return round(float(x), 4)

    summary = (
        f"AMT BUY={'Y' if buy_signal else 'N'} "
        f"(VAL↑={buy_from_val}, EMA9={buy_ema_reclaim}) "
        f"TP={'Y' if tp_zone else 'N'} VAH={'Y' if strong_tp_zone else 'N'}"
    )

    return {
        "amt_ok": True,
        "amt_insufficient_bars": False,
        "amt_session_len": session_len,
        "amt_ema_len": ema_len,
        "amt_poc_proxy": _r4(float(p0) if p0 is not None else None),
        "amt_vah": _r4(float(h0) if h0 is not None else None),
        "amt_val": _r4(float(v0) if v0 is not None else None),
        "amt_buy_signal": buy_signal,
        "amt_buy_from_val": buy_from_val,
        "amt_buy_ema_reclaim": buy_ema_reclaim,
        "amt_tp_zone": tp_zone,
        "amt_strong_tp_zone": strong_tp_zone,
        "amt_summary_line": summary,
    }


def build_amt_from_intraday(
    market_data: Any,
    ticker: str,
    *,
    timeframe_minutes: int,
    lookback_calendar_days: int | None,
) -> Dict[str, Any]:
    try:
        bars = market_data.fetch_intraday_bars(
            ticker,
            timeframe_minutes=timeframe_minutes,
            lookback_calendar_days=lookback_calendar_days,
        )
    except Exception:
        bars = []
    if not bars:
        return {
            "amt_ok": False,
            "amt_no_bars": True,
            "amt_buy_signal": False,
            "amt_summary_line": "AMT — barlar yo‘q",
        }
    session_len = max(1, int(os.getenv("AMT_SESSION_LEN", "20")))
    ema_len = max(1, int(os.getenv("AMT_EMA_LEN", "9")))
    out = compute_amt_vwap_scalp(bars, session_len=session_len, ema_len=ema_len)
    out["amt_timeframe_minutes"] = timeframe_minutes
    return out


def maybe_attach_amt_snapshot(market_data: Any, ticker: str, signal: Dict[str, Any]) -> Dict[str, Any]:
    if not _truthy(os.getenv("AMT_VWAP_SCALP_ENABLED"), default=True):
        return signal
    pass_only = _truthy(os.getenv("AMT_SNAPSHOT_PASS_ONLY"), default=False)
    if pass_only and not bool(signal.get("strategy_pass")):
        return signal

    try:
        tf = int(os.getenv("AMT_TIMEFRAME_MINUTES", os.getenv("INTRADAY_TIMEFRAME_MINUTES", "5")))
    except ValueError:
        tf = 5
    tf = max(1, min(60, tf))
    try:
        lb = int(os.getenv("AMT_LOOKBACK_CALENDAR_DAYS", os.getenv("INTRADAY_LOOKBACK_DAYS", "7")))
    except ValueError:
        lb = 7
    lb = max(1, min(60, lb))

    extra = build_amt_from_intraday(market_data, ticker, timeframe_minutes=tf, lookback_calendar_days=lb)
    out = dict(signal)
    out.update(extra)
    return out
