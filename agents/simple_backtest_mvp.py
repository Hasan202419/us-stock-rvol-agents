"""Minimal kunlik SMA-kesishma backtest (MVP) — lookaheadsiz bitta bar kechikish."""

from __future__ import annotations

from typing import Any, Dict, List


def daily_closes_yfinance(symbol: str, calendar_days: int) -> List[float]:
    """Kunlik yopilishlar (adjusted), bo‘sh ro‘yxat agar tarix topilmasa."""

    try:
        import yfinance as yf
    except ImportError:
        return []

    hist = yf.Ticker(symbol).history(period=f"{calendar_days}d", auto_adjust=True)
    if hist is None or hist.empty:
        return []
    return [float(x) for x in hist["Close"].astype(float).tolist()]


def daily_candles_yfinance(symbol: str, calendar_days: int) -> List[Dict[str, Any]]:
    """Kunlik OHLCV shamlar (t,o,h,l,c,v) — IBKR o‘chiq bo‘lsa zaxira manba. Bo‘sh agar topilmasa."""

    try:
        import yfinance as yf
    except ImportError:
        return []

    hist = yf.Ticker(symbol).history(period=f"{calendar_days}d", auto_adjust=False)
    if hist is None or hist.empty:
        return []

    out: List[Dict[str, Any]] = []
    for ts, row in hist.iterrows():
        try:
            t_ms = int(ts.timestamp() * 1000)
        except (AttributeError, TypeError, ValueError):
            continue
        out.append(
            {
                "t": t_ms,
                "o": float(row["Open"]),
                "h": float(row["High"]),
                "l": float(row["Low"]),
                "c": float(row["Close"]),
                "v": float(row.get("Volume") or 0),
            }
        )
    out.sort(key=lambda b: b["t"])
    return out


def _sma(closes: List[float], period: int, end_exclusive: int) -> float | None:
    if end_exclusive < period or period <= 0:
        return None
    window = closes[end_exclusive - period : end_exclusive]
    if len(window) != period:
        return None
    return sum(window) / period


def sma_crossover_long_only_backtest(
    closes: List[float],
    *,
    fast: int = 10,
    slow: int = 30,
) -> Dict[str, Any]:
    """Long-only: `t-1` paytida `SMA_fast > SMA_slow` bo‘lsa, `t-1` → `t` qaytishini hisobga ol.

    Buy-hold: birinchi savdo baridan (`slow`) oxirgacha barcha kunlik qaytishlar.
    """

    if fast >= slow or len(closes) < slow + 2:
        return {
            "ok": False,
            "error": "insufficient_bars_or_bad_period",
            "bars": len(closes),
            "fast": fast,
            "slow": slow,
        }

    equity = 1.0
    long_bars = 0
    for i in range(slow, len(closes) - 1):
        f_prev = _sma(closes, fast, i)
        s_prev = _sma(closes, slow, i)
        if f_prev is None or s_prev is None:
            continue
        in_long = f_prev > s_prev
        r = (closes[i + 1] - closes[i]) / closes[i] if closes[i] else 0.0
        if in_long:
            equity *= 1.0 + r
            long_bars += 1

    strat_pct = round((equity - 1.0) * 100.0, 2)
    warmup_close = closes[slow]
    last_close = closes[-1]
    bh_pct = round(((last_close - warmup_close) / warmup_close) * 100.0, 2) if warmup_close else 0.0

    return {
        "ok": True,
        "bars_evaluated": max(0, len(closes) - slow - 1),
        "bars_in_long": long_bars,
        "strategy_total_return_pct": strat_pct,
        "buy_hold_from_warmup_pct": bh_pct,
        "rule": "long_when_fast_sma_gt_slow_at_prior_close",
        "fast": fast,
        "slow": slow,
    }
