"""Gap-and-Go strategiyasi — sof birliklar + backtest integratsiyasi."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.backtest_engine import build_default_grid, replay_strategy
from agents.strategy_gap_and_go import GapAndGoStrategyAgent


def _bar(t: int, o: float, h: float, low: float, c: float, v: float) -> Dict[str, Any]:
    return {"t": t * 86_400_000, "o": o, "h": h, "l": low, "c": c, "v": v}


def _history(n: int, *, close: float = 100.0, vol: float = 600_000.0) -> List[Dict[str, Any]]:
    return [_bar(i, close, close, close, close, vol) for i in range(n)]


def _snapshot(candles: List[Dict[str, Any]], *, rvol: float, avg_volume: float) -> Dict[str, Any]:
    last = candles[-1]
    return {
        "ticker": "TEST",
        "price": float(last["c"]),
        "volume": float(last["v"]),
        "avg_volume": avg_volume,
        "rvol": rvol,
        "candles": candles,
    }


def test_gap_and_go_passes_on_held_gap() -> None:
    candles = _history(20)
    # Gap +5%: kecha 100 → bugun open 105, kun yuqorida yopiladi (gap ushlandi).
    candles.append(_bar(20, 105.0, 108.0, 104.5, 107.5, 1_800_000))
    snap = _snapshot(candles, rvol=3.0, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is True
    assert out["failed_rules"] == []
    assert out["gap_pct"] == 5.0
    assert out["strategy_name"] == "gap_and_go_scan"
    assert out["stop_suggestion"] < out["price"] < out["take_profit_suggestion"]
    assert out["gap_go_bucket"] == "Gap3-6"


def test_gap_fade_fails_held_gap() -> None:
    candles = _history(20)
    # Gap up, lekin kun pastida yopiladi (gap-fade) → held_gap fail.
    candles.append(_bar(20, 105.0, 105.5, 99.0, 99.5, 1_800_000))
    snap = _snapshot(candles, rvol=3.0, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is False
    assert "held_gap" in out["failed_rules"]


def test_no_gap_fails_gap_up() -> None:
    candles = _history(20)
    candles.append(_bar(20, 100.5, 101.5, 100.2, 101.4, 1_800_000))  # gap +0.5%
    snap = _snapshot(candles, rvol=3.0, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is False
    assert "gap_up" in out["failed_rules"]


def test_exhausted_gap_fails() -> None:
    candles = _history(20)
    candles.append(_bar(20, 130.0, 135.0, 129.0, 134.0, 1_800_000))  # gap +30%
    snap = _snapshot(candles, rvol=3.0, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is False
    assert "gap_exhausted" in out["failed_rules"]


def test_low_rvol_fails() -> None:
    candles = _history(20)
    candles.append(_bar(20, 105.0, 108.0, 104.5, 107.5, 700_000))
    snap = _snapshot(candles, rvol=1.1, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is False
    assert "rvol" in out["failed_rules"]


def test_short_history_fails_gracefully() -> None:
    candles = _history(3)
    snap = _snapshot(candles, rvol=3.0, avg_volume=600_000)
    out = GapAndGoStrategyAgent().evaluate(snap)
    assert out["strategy_pass"] is False
    assert "bars_history" in out["failed_rules"]
    assert out["score"] >= 0


def test_replay_gap_go_finds_entry() -> None:
    candles = _history(25, close=100.0, vol=600_000)
    # 25-bar: gap +5% + kuchli yopilish.
    candles.append(_bar(25, 105.0, 108.0, 104.5, 107.5, 1_800_000))
    # Oldinga ko‘tarilish (target uchun).
    px = 107.5
    for i in range(26, 33):
        px *= 1.02
        candles.append(_bar(i, px * 0.995, px * 1.02, px * 0.99, px, 700_000))

    trades = replay_strategy(candles, "gap_go", min_history=25, horizon=6, avg_window=20)
    assert any(t["entry_index"] == 25 for t in trades)


def test_build_default_grid_gap_go_shape() -> None:
    grid = build_default_grid("gap_go")
    assert grid
    assert all("GAP_GO_MIN_GAP_PCT" in c and "GAP_GO_MIN_RVOL" in c for c in grid)
