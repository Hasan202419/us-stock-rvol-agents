"""scanner.py — ikki rejim skaner: Large Cap Quality + Penny Momentum.

Har ticker: ma'lumot olish -> indikatorlar+zona -> strategiya -> qaror.
Penny rejimida qattiq filtrlar (narx/hajm/RVOL/spread/% change) qo'llanadi.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import config
from .halal_filter import halal_status
from .indicators import dollar_volume, pct_change, rvol, spread_pct
from .market_regime import fetch_ticker
from .strategy import evaluate_setup


def _penny_passes_filters(data: Dict[str, Any]) -> bool:
    """MODE 2 qattiq filtrlari (price/volume/RVOL/dollar vol/% change/spread)."""
    price = float(data.get("price") or 0)
    if not (config.PENNY_PRICE_MIN <= price <= config.PENNY_PRICE_MAX):
        return False
    cur_vol = float(data.get("current_volume") or 0)
    if cur_vol < config.PENNY_MIN_CURRENT_VOLUME:
        return False
    avg_vol = float(data.get("avg_20d_volume") or 0)
    if avg_vol < config.PENNY_MIN_AVG_20D_VOLUME:
        return False
    if rvol(cur_vol, avg_vol) < config.PENNY_MIN_RVOL:
        return False
    if dollar_volume(price, cur_vol) < config.PENNY_MIN_DOLLAR_VOLUME:
        return False
    chg = pct_change(price, data.get("prev_close"))
    if chg is None or not (config.PENNY_MIN_CHANGE_PCT <= chg <= config.PENNY_MAX_CHANGE_PCT):
        return False
    sp = spread_pct(data.get("bid"), data.get("ask"), price)
    if sp is not None and sp > config.PENNY_MAX_SPREAD_PCT:
        return False
    return True


def scan_universe(
    tickers: List[str],
    *,
    mode: str,
    regime: Dict[str, Any],
    market_open: bool = True,
    preferred: str = "auto",
    apply_penny_filters: bool = False,
) -> List[Dict[str, Any]]:
    """Berilgan tickerlar bo'ylab skan -> signal ro'yxati."""
    out: List[Dict[str, Any]] = []
    for ticker in tickers:
        data = fetch_ticker(ticker, preferred=preferred)
        if not data or not data.get("candles_5m"):
            out.append({
                "ticker": ticker.upper(), "mode": mode, "decision": "WATCHLIST",
                "score": 0, "reason": "Ma'lumot yo'q/kechikkan (WATCHLIST only)",
                "halal_status": halal_status(ticker), "price": data.get("price") if data else None,
                "vwap_status": "—", "zone_status": "—", "volume_spike": None,
                "entry": None, "stop_loss": None, "target1": None, "target2": None, "risk_reward": None,
            })
            continue
        if apply_penny_filters and not _penny_passes_filters(data):
            continue
        sig = evaluate_setup(
            data, mode=mode, regime=regime,
            halal_status=halal_status(ticker), market_open=market_open,
        )
        out.append(sig)
    return out


def scan_all(regime: Dict[str, Any], *, market_open: bool = True, preferred: str = "auto") -> List[Dict[str, Any]]:
    """SCAN_MODE ga ko'ra Large Cap va/yoki Penny skan."""
    results: List[Dict[str, Any]] = []
    mode = config.SCAN_MODE
    if mode in {"large_cap", "both"}:
        results += scan_universe(
            config.LARGE_CAP_WATCHLIST, mode="Large Cap", regime=regime,
            market_open=market_open, preferred=preferred,
        )
    if mode in {"penny", "both"}:
        results += scan_universe(
            config.PENNY_WATCHLIST, mode="Penny Momentum", regime=regime,
            market_open=market_open, preferred=preferred, apply_penny_filters=True,
        )
    # Eng yaxshi ball birinchi
    results.sort(key=lambda s: int(s.get("score", 0)), reverse=True)
    return results
