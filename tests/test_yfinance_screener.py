"""yfinance_screener — tarmoqsiz unit testlar (yf mock)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from agents.yfinance_screener import (
    _atr_simple,
    _setup_type,
    _trade_levels,
    _tv_url,
    format_scalp_html,
    scalp_score,
    screen_scalp_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int = 25, base_close: float = 100.0, base_vol: float = 1_000_000.0) -> List[Dict[str, Any]]:
    return [
        {
            "t": 1_700_000_000 + i * 86_400,
            "o": base_close * 0.99,
            "h": base_close * 1.02,
            "l": base_close * 0.98,
            "c": base_close,
            "v": base_vol,
        }
        for i in range(n)
    ]


def _snap(
    ticker: str = "NVDA",
    price: float = 100.0,
    prev_close: float = 95.0,
    rvol: float = 3.0,
    volume: int = 5_000_000,
    gap_pct: float = 2.0,
    held_gap: bool = True,
    atr: float = 2.5,
) -> Dict[str, Any]:
    change_pct = round((price - prev_close) / prev_close * 100, 2)
    candles = _make_candles(25, price)
    return {
        "ticker": ticker,
        "price": price,
        "prev_close": prev_close,
        "change_percent": change_pct,
        "gap_pct": gap_pct,
        "held_gap": held_gap,
        "volume": volume,
        "avg_volume": volume,
        "rvol": rvol,
        "atr": atr,
        "today_low": round(price * 0.97, 4),
        "today_high": round(price * 1.03, 4),
        "candles": candles,
        "tv_url": _tv_url(ticker),
    }


# ---------------------------------------------------------------------------
# _tv_url
# ---------------------------------------------------------------------------

def test_tv_url_encodes_ticker() -> None:
    url = _tv_url("AAPL")
    assert "AAPL" in url
    assert "tradingview.com" in url


def test_tv_url_empty() -> None:
    url = _tv_url("")
    assert "tradingview.com" in url


# ---------------------------------------------------------------------------
# _atr_simple
# ---------------------------------------------------------------------------

def test_atr_simple_basic() -> None:
    candles = _make_candles(20, 100.0)
    atr = _atr_simple(candles)
    assert atr > 0


def test_atr_simple_too_few_candles() -> None:
    assert _atr_simple([]) == 0.0
    assert _atr_simple(_make_candles(1)) == 0.0


# ---------------------------------------------------------------------------
# scalp_score
# ---------------------------------------------------------------------------

def test_high_rvol_gap_held_scores_highest() -> None:
    s = _snap(rvol=3.5, gap_pct=4.0, held_gap=True, volume=6_000_000)
    assert scalp_score(s) >= 70.0


def test_low_rvol_low_volume_scores_low() -> None:
    s = _snap(rvol=1.0, gap_pct=0.1, held_gap=False, volume=100_000)
    assert scalp_score(s) < 20.0


def test_overextended_move_scores_less_than_moderate() -> None:
    s_mod = _snap(rvol=2.5, price=100.0, prev_close=96.0)  # ~4.2% chg
    s_ext = _snap(rvol=2.5, price=100.0, prev_close=80.0)  # ~25% chg
    assert scalp_score(s_mod) > scalp_score(s_ext)


# ---------------------------------------------------------------------------
# _setup_type
# ---------------------------------------------------------------------------

def test_setup_type_gap_and_go() -> None:
    s = _snap(gap_pct=4.0, held_gap=True)
    assert _setup_type(s) == "GAP-AND-GO"


def test_setup_type_gap_fade_risk() -> None:
    s = _snap(gap_pct=4.0, held_gap=False)
    assert _setup_type(s) == "GAP (fade risk)"


def test_setup_type_rvol_breakout() -> None:
    s = _snap(gap_pct=0.5, rvol=3.0, held_gap=False)
    assert _setup_type(s) == "RVOL BREAKOUT"


def test_setup_type_watchlist() -> None:
    s = _snap(gap_pct=0.1, rvol=1.2, held_gap=False)
    assert _setup_type(s) == "WATCHLIST"


# ---------------------------------------------------------------------------
# _trade_levels
# ---------------------------------------------------------------------------

def test_trade_levels_tp_above_entry() -> None:
    s = _snap(price=100.0, atr=2.0)
    lvl = _trade_levels(s)
    assert lvl["tp1"] > lvl["entry"] > lvl["stop"]
    assert lvl["rr"] >= 1.5


def test_trade_levels_stop_never_below_1pct() -> None:
    s = _snap(price=100.0, atr=0.001)  # tiny ATR
    lvl = _trade_levels(s)
    assert lvl["entry"] - lvl["stop"] >= lvl["entry"] * 0.005


def test_trade_levels_stop_never_above_price() -> None:
    s = _snap(price=100.0, atr=50.0)  # huge ATR
    lvl = _trade_levels(s)
    assert lvl["stop"] < lvl["entry"]


# ---------------------------------------------------------------------------
# screen_scalp_candidates (mocked _yf_snapshot)
# ---------------------------------------------------------------------------

def _fake_snapshot(ticker: str, **_: Any) -> Optional[Dict[str, Any]]:
    mapping = {
        "NVDA": _snap("NVDA", price=900.0, rvol=3.2, volume=8_000_000, gap_pct=4.0, held_gap=True),
        "AMD": _snap("AMD", price=120.0, rvol=2.1, volume=4_000_000, gap_pct=1.5, held_gap=True),
        "LOW_RVOL": _snap("LOW_RVOL", price=50.0, rvol=0.8, volume=2_000_000),
        "LOW_PRICE": _snap("LOW_PRICE", price=2.0, rvol=3.0, volume=5_000_000),
        "LOW_VOL": _snap("LOW_VOL", price=50.0, rvol=3.0, volume=100_000),
    }
    return mapping.get(ticker)


def test_screen_filters_low_rvol() -> None:
    universe = ["NVDA", "AMD", "LOW_RVOL"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, min_rvol=1.5, delay_sec=0)
    tickers = [r["ticker"] for r in res]
    assert "NVDA" in tickers
    assert "AMD" in tickers
    assert "LOW_RVOL" not in tickers


def test_screen_filters_low_price() -> None:
    universe = ["NVDA", "LOW_PRICE"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, min_price=5.0, delay_sec=0)
    tickers = [r["ticker"] for r in res]
    assert "LOW_PRICE" not in tickers


def test_screen_filters_low_volume() -> None:
    universe = ["NVDA", "LOW_VOL"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, min_volume=500_000, delay_sec=0)
    tickers = [r["ticker"] for r in res]
    assert "LOW_VOL" not in tickers


def test_screen_sorted_by_score() -> None:
    universe = ["AMD", "NVDA"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, delay_sec=0)
    assert res[0]["ticker"] == "NVDA"  # higher RVOL + gap + held


def test_screen_top_n_cap() -> None:
    universe = ["NVDA", "AMD"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, top_n=1, delay_sec=0)
    assert len(res) == 1


def test_screen_attaches_levels_and_setup() -> None:
    universe = ["NVDA"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        res = screen_scalp_candidates(universe, delay_sec=0)
    assert res
    assert "levels" in res[0]
    assert "setup_type" in res[0]
    assert res[0]["setup_type"] == "GAP-AND-GO"


def test_screen_empty_universe_returns_empty() -> None:
    with patch("agents.yfinance_screener._yf_snapshot", return_value=None):
        res = screen_scalp_candidates(["FAKE"], delay_sec=0)
    assert res == []


# ---------------------------------------------------------------------------
# format_scalp_html
# ---------------------------------------------------------------------------

def test_format_scalp_html_contains_key_fields() -> None:
    universe = ["NVDA", "AMD"]
    with patch("agents.yfinance_screener._yf_snapshot", side_effect=_fake_snapshot):
        candidates = screen_scalp_candidates(universe, delay_sec=0)
    html = format_scalp_html(candidates)
    assert "NVDA" in html
    assert "TradingView" in html
    assert "RVOL" in html
    assert "Kirish" in html
    assert "SL" in html


def test_format_scalp_html_empty() -> None:
    html = format_scalp_html([])
    assert "topilmadi" in html
