"""signal_chart — PNG render + daraja ajratish (tarmoqsiz)."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.signal_chart import chart_caption, extract_levels, render_signal_chart

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _candles(n: int = 40, start: float = 100.0) -> List[Dict[str, Any]]:
    bars: List[Dict[str, Any]] = []
    px = start
    for i in range(n):
        o = px
        c = px * (1.01 if i % 2 else 0.995)
        h = max(o, c) * 1.01
        low = min(o, c) * 0.99
        bars.append({"t": i * 86_400_000, "o": o, "h": h, "l": low, "c": c, "v": 500_000 + i * 1000})
        px = c
    return bars


def _signal() -> Dict[str, Any]:
    return {
        "ticker": "nvda",
        "price": 120.0,
        "score": 87,
        "rvol": 3.2,
        "strategy_name": "gap_and_go_scan",
        "stop_suggestion": 114.0,
        "take_profit_suggestion": 132.0,
        "trade_tp2": 140.0,
        "ignition_resistance": 130.0,
        "ignition_entry_zone_low": 118.0,
        "ignition_entry_zone_high": 121.0,
        "amt_val": 116.0,
        "amt_vah": 124.0,
        "amt_poc": 119.0,
    }


def test_extract_levels_maps_fields() -> None:
    lv = extract_levels(_signal())
    assert lv["entry"] == 120.0
    assert lv["stop"] == 114.0
    assert lv["tp1"] == 132.0
    assert lv["tp2"] == 140.0
    assert lv["resistance"] == 130.0
    assert lv["val"] == 116.0 and lv["vah"] == 124.0 and lv["poc"] == 119.0


def test_extract_levels_ignores_nonpositive() -> None:
    lv = extract_levels({"price": 0, "stop_suggestion": -1, "take_profit_suggestion": "x"})
    assert lv["price"] is None
    assert lv["stop"] is None
    assert lv["tp1"] is None


def test_render_returns_valid_png() -> None:
    data = render_signal_chart(_signal(), _candles())
    assert data is not None
    assert data[:8] == _PNG_MAGIC
    assert len(data) > 1500


def test_render_writes_file(tmp_path) -> None:
    p = tmp_path / "chart.png"
    data = render_signal_chart(_signal(), _candles(), out_path=str(p))
    assert p.is_file()
    assert p.read_bytes()[:8] == _PNG_MAGIC
    assert data is not None


def test_render_none_when_no_candles() -> None:
    assert render_signal_chart(_signal(), []) is None
    assert render_signal_chart(_signal(), [{"t": 1, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]) is None


def test_render_uses_signal_candles_fallback() -> None:
    sig = dict(_signal())
    sig["candles"] = _candles()
    assert render_signal_chart(sig) is not None


def test_chart_caption_has_levels_and_rr() -> None:
    cap = chart_caption(_signal())
    assert "NVDA" in cap
    assert "Entry" in cap and "SL" in cap and "TP" in cap
    assert "R:R" in cap
