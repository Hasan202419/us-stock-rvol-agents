"""ignition_screener — volume ignition skaner, tarmoqsiz (_yf_snapshot mock)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from agents.ignition_screener import (
    evaluate_ignition_for_snapshot,
    format_ignition_html,
    screen_ignition_candidates,
)


def _ignition_candles(n: int = 40, base: float = 10.0, spike: bool = True) -> List[Dict[str, Any]]:
    """Hajm o'sishi + qarshilikka yaqin ignition shamlari."""
    out: List[Dict[str, Any]] = []
    for i in range(n):
        v = 1_000_000 + i * 10_000
        c = base + i * 0.02
        out.append({"t": i * 86_400_000, "o": c - 0.05, "h": c + 0.1, "l": c - 0.1, "c": c, "v": v})
    if spike:
        for k in range(1, 4):
            out[-k]["v"] = 3_000_000
    return out


def _snap(ticker: str = "TEST", spike: bool = True) -> Dict[str, Any]:
    candles = _ignition_candles(spike=spike)
    return {
        "ticker": ticker,
        "price": candles[-1]["c"],
        "rvol": 3.0 if spike else 0.8,
        "avg_volume": 1_200_000,
        "volume": candles[-1]["v"],
        "candles": candles,
        "tv_url": f"https://www.tradingview.com/chart/?symbol={ticker}",
    }


# ---------------------------------------------------------------------------
# evaluate_ignition_for_snapshot
# ---------------------------------------------------------------------------

def test_evaluate_produces_ignition_fields() -> None:
    res = evaluate_ignition_for_snapshot(_snap("NVDA"))
    assert res is not None
    assert res["ticker"] == "NVDA"
    for key in (
        "trend_stage", "continuation_probability", "distance_to_resistance_pct",
        "risk_level", "entry_zone_low", "entry_zone_high", "volume_pattern", "verdict",
    ):
        assert key in res


def test_evaluate_returns_none_for_few_candles() -> None:
    assert evaluate_ignition_for_snapshot({"ticker": "X", "candles": [{"c": 1}]}) is None
    assert evaluate_ignition_for_snapshot({"ticker": "X"}) is None


# ---------------------------------------------------------------------------
# screen_ignition_candidates
# ---------------------------------------------------------------------------

def _fake_snapshot(ticker: str, **_: Any) -> Optional[Dict[str, Any]]:
    table = {
        "GOOD": _snap("GOOD", spike=True),
        "WEAK": _snap("WEAK", spike=False),
        "NONE": None,
    }
    return table.get(ticker)


def test_screen_includes_buy_and_watch() -> None:
    with patch("agents.ignition_screener._yf_snapshot", side_effect=_fake_snapshot):
        rows = screen_ignition_candidates(["GOOD", "WEAK", "NONE"], delay_sec=0)
    tickers = [r["ticker"] for r in rows]
    assert "GOOD" in tickers  # spike -> BUY/WATCH
    # NONE snapshot yo'q -> chiqmaydi
    assert "NONE" not in tickers


def test_screen_buy_only_filter() -> None:
    with patch("agents.ignition_screener._yf_snapshot", side_effect=_fake_snapshot):
        rows = screen_ignition_candidates(["GOOD", "WEAK"], include_watch=False, delay_sec=0)
    for r in rows:
        assert r["verdict"] == "BUY"


def test_screen_top_n_cap() -> None:
    uni = ["GOOD"] * 5
    with patch("agents.ignition_screener._yf_snapshot", side_effect=_fake_snapshot):
        rows = screen_ignition_candidates(uni, top_n=2, delay_sec=0)
    assert len(rows) <= 2


def test_screen_ranks_buy_first() -> None:
    with patch("agents.ignition_screener._yf_snapshot", side_effect=_fake_snapshot):
        rows = screen_ignition_candidates(["WEAK", "GOOD"], delay_sec=0)
    if len(rows) >= 2:
        # BUY (GOOD) WATCH (WEAK) dan oldinda bo'lishi kerak
        verdict_ranks = {"BUY": 3, "WATCH": 2, "AVOID": 1}
        ranks = [verdict_ranks.get(r["verdict"], 0) for r in rows]
        assert ranks == sorted(ranks, reverse=True)


def test_screen_empty_universe() -> None:
    with patch("agents.ignition_screener._yf_snapshot", return_value=None):
        assert screen_ignition_candidates(["X", "Y"], delay_sec=0) == []


# ---------------------------------------------------------------------------
# format_ignition_html
# ---------------------------------------------------------------------------

def test_format_html_has_fields() -> None:
    with patch("agents.ignition_screener._yf_snapshot", side_effect=_fake_snapshot):
        rows = screen_ignition_candidates(["GOOD"], delay_sec=0)
    html = format_ignition_html(rows)
    assert "IGNITION" in html
    assert "GOOD" in html
    assert "RVOL" in html
    assert "Kirish zonasi" in html
    assert "TradingView" in html


def test_format_html_empty() -> None:
    html = format_ignition_html([])
    assert "topilmadi" in html
