"""backtest_engine — sof birliklar (tarmoqsiz, sintetik shamlar)."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.backtest_engine import (
    build_default_grid,
    build_snapshot,
    evaluate_trade,
    replay_strategy,
    summarize,
)


def _candle(t: int, o: float, h: float, low: float, c: float, v: float) -> Dict[str, Any]:
    return {"t": t * 86_400_000, "o": o, "h": h, "l": low, "c": c, "v": v}


def _flat_series(n: int, *, close: float = 10.0, vol: float = 100_000.0) -> List[Dict[str, Any]]:
    return [_candle(i, close, close, close, close, vol) for i in range(n)]


def test_build_snapshot_no_lookahead() -> None:
    candles = _flat_series(30, vol=100_000)
    # i-bar hajmi katta; o‘rtacha faqat oldingi 20 bardan (lookahead yo‘q).
    candles[25]["v"] = 300_000
    snap = build_snapshot(candles, 25, avg_window=20)
    assert snap["volume"] == 300_000
    assert snap["avg_volume"] == 100_000  # oldingi 20 bar 100k
    assert snap["rvol"] == 3.0
    # Oyna i+1 dan oshmaydi
    assert len(snap["candles"]) == 26


def test_evaluate_trade_target_hit() -> None:
    candles = _flat_series(5, close=10.0)
    candles[2] = _candle(2, 10, 12.5, 9.9, 11.0, 100_000)  # high 12.5 >= target 12
    res = evaluate_trade(candles, entry_index=1, entry=10.0, stop=9.0, target=12.0, horizon=3)
    assert res["outcome"] == "target"
    assert res["win"] is True
    assert res["r_multiple"] == 2.0  # (12-10)/(10-9)


def test_evaluate_trade_stop_hit() -> None:
    candles = _flat_series(5, close=10.0)
    candles[2] = _candle(2, 10, 10.1, 8.5, 9.0, 100_000)  # low 8.5 <= stop 9
    res = evaluate_trade(candles, entry_index=1, entry=10.0, stop=9.0, target=12.0, horizon=3)
    assert res["outcome"] == "stop"
    assert res["win"] is False
    assert res["r_multiple"] == -1.0


def test_evaluate_trade_timeout_exits_at_close() -> None:
    candles = _flat_series(6, close=10.0)
    candles[2] = _candle(2, 10, 10.5, 9.8, 10.4, 100_000)
    candles[3] = _candle(3, 10.4, 10.6, 9.9, 10.5, 100_000)
    res = evaluate_trade(candles, entry_index=1, entry=10.0, stop=9.0, target=12.0, horizon=2)
    assert res["outcome"] == "timeout"
    assert res["exit"] == 10.5  # close[3] (entry_index+horizon)
    assert res["win"] is True


def test_stop_priority_when_both_touched_in_bar() -> None:
    candles = _flat_series(4, close=10.0)
    candles[2] = _candle(2, 10, 13.0, 8.0, 11.0, 100_000)  # ham stop, ham target shu barda
    res = evaluate_trade(candles, entry_index=1, entry=10.0, stop=9.0, target=12.0, horizon=2)
    assert res["outcome"] == "stop"  # konservativ: stop avval


def test_summarize_math() -> None:
    trades = [
        {"win": True, "return_pct": 10.0, "r_multiple": 2.0, "trend_stage": "Ignition", "continuation_probability": 75},
        {"win": False, "return_pct": -5.0, "r_multiple": -1.0, "trend_stage": "Ignition", "continuation_probability": 40},
    ]
    s = summarize(trades)
    assert s["trades"] == 2
    assert s["win_rate_pct"] == 50.0
    assert s["avg_return_pct"] == 2.5
    assert s["expectancy_r"] == 0.5  # 0.5*2 + 0.5*(-1)
    assert s["by_probability"]["70+"]["win_rate_pct"] == 100.0
    assert s["by_probability"]["<50"]["win_rate_pct"] == 0.0


def test_summarize_empty() -> None:
    s = summarize([])
    assert s["trades"] == 0
    assert s["expectancy_r"] == 0.0


def test_replay_rvol_finds_volume_spike() -> None:
    # 25 bar past hajm, keyin bir nechta spike + ko‘tariluvchi narx → rvol_momentum pass.
    candles: List[Dict[str, Any]] = []
    price = 10.0
    for i in range(26):
        candles.append(_candle(i, price, price * 1.001, price * 0.999, price, 100_000))
    # Spike bar: katta hajm + yashil kun
    price2 = 10.2
    candles.append(_candle(26, 10.0, 10.3, 9.99, price2, 400_000))  # rvol ~4, change +2%
    # Oldinga ko‘tarilish (target uchun)
    for i in range(27, 33):
        price2 *= 1.03
        candles.append(_candle(i, price2 * 0.99, price2 * 1.02, price2 * 0.985, price2, 150_000))

    trades = replay_strategy(candles, "rvol", min_history=25, horizon=6, avg_window=20)
    assert any(t["entry_index"] == 26 for t in trades)


def test_build_default_grid_shapes() -> None:
    ig = build_default_grid("volume_ignition")
    assert all("IGNITION_MIN_RVOL" in c for c in ig)
    rv = build_default_grid("rvol")
    assert all("MIN_RVOL" in c for c in rv)
