"""order_flow_signal — CLC qoidasi (Context/Location/Confirmation), tarmoqsiz."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.order_flow_signal import (
    evaluate_order_flow,
    format_order_flow_html,
    order_flow_badge,
)


def _cage_candles(
    n: int = 12,
    cage_low: float = 98.0,
    cage_high: float = 102.0,
) -> List[Dict[str, Any]]:
    """Tor diapazonli (Qafas) shamlar."""
    out: List[Dict[str, Any]] = []
    mid = (cage_low + cage_high) / 2
    for i in range(n):
        out.append({"t": i, "o": mid, "h": cage_high, "l": cage_low, "c": mid, "v": 1_000_000})
    return out


def _breakout_signal(rvol: float = 2.5) -> Dict[str, Any]:
    """Qafasdan tepaga chiqqan + kuchli Initiative Candle."""
    candles = _cage_candles()
    # breakout shami: qafas tepasidan (102) yuqori, tepada yopilgan, katta tana
    candles.append({"t": 99, "o": 101.5, "h": 106.0, "l": 101.4, "c": 105.7, "v": 3_000_000})
    return {"ticker": "NVDA", "price": 105.7, "rvol": rvol, "candles": candles}


def test_full_clc_alignment_is_buy() -> None:
    res = evaluate_order_flow(_breakout_signal(rvol=2.5))
    assert res["clc_context"] is True
    assert res["clc_location"] is True
    assert res["clc_confirmation"] is True
    assert res["of_verdict"] == "BUY"
    assert res["of_icon"] == "🟢"
    assert res["of_pillars_ok"] == 3
    assert res["of_score"] == 100


def test_low_rvol_breaks_confirmation() -> None:
    # RVOL past -> tape sust -> confirmation yo'q -> BUY emas
    res = evaluate_order_flow(_breakout_signal(rvol=1.0))
    assert res["clc_confirmation"] is False
    assert res["of_verdict"] != "BUY"


def test_price_in_cage_middle_no_context() -> None:
    candles = _cage_candles()
    # oxirgi sham hali qafas ichida (o'rtada)
    candles.append({"t": 99, "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "v": 1_000_000})
    res = evaluate_order_flow({"ticker": "X", "price": 100.0, "rvol": 2.5, "candles": candles})
    assert res["clc_context"] is False
    assert res["of_verdict"] != "BUY"


def test_absorption_warning_forces_avoid() -> None:
    candles = _cage_candles()
    # breakout darajasida lekin: katta hajm (RVOL yuqori), kichik tana, tepadan qaytib pastda yopildi = Absorption
    candles.append({"t": 99, "o": 103.0, "h": 106.0, "l": 102.5, "c": 103.0, "v": 4_000_000})
    res = evaluate_order_flow({"ticker": "X", "price": 103.0, "rvol": 3.0, "candles": candles})
    assert res["of_absorption_warn"] is True
    assert res["of_verdict"] == "AVOID"
    assert res["of_icon"] == "⛔"


def test_location_uses_value_area_edges() -> None:
    sig = _breakout_signal(rvol=2.5)
    # POC o'rtasiga qo'ysak — location kuchsizlanadi
    sig["amt_val"] = 104.0
    sig["amt_vah"] = 108.0
    sig["amt_poc_proxy"] = 105.7  # narx aynan POC'da
    res = evaluate_order_flow(sig)
    assert res["clc_location"] is False  # POC o'rtasi — yangi kirish emas


def test_location_ok_above_vah() -> None:
    sig = _breakout_signal(rvol=2.5)
    sig["amt_val"] = 99.0
    sig["amt_vah"] = 103.0  # narx 105.7 > VAH -> breakout location
    res = evaluate_order_flow(sig)
    assert res["clc_location"] is True


def test_insufficient_candles_no_buy() -> None:
    res = evaluate_order_flow({"ticker": "X", "price": 100.0, "rvol": 3.0, "candles": [{"t": 1, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]})
    assert res["clc_context"] is False
    assert res["of_verdict"] != "BUY"


def test_empty_signal_safe() -> None:
    res = evaluate_order_flow({})
    assert res["of_verdict"] == "AVOID"
    assert res["of_pillars_ok"] == 0


def test_badge_strings() -> None:
    assert "KIRISH" in order_flow_badge({"of_verdict": "BUY", "of_icon": "🟢"})
    assert "KUTING" in order_flow_badge({"of_verdict": "WATCH", "of_icon": "🟡"})
    assert "O'TKAZ" in order_flow_badge({"of_verdict": "AVOID", "of_icon": "⛔"})


def test_html_report_has_clc_structure() -> None:
    res = evaluate_order_flow(_breakout_signal(rvol=2.5))
    html = format_order_flow_html(_breakout_signal(rvol=2.5), res, ticker="NVDA")
    for token in ("Order Flow", "Context", "Location", "Confirmation", "NVDA", "CLC"):
        assert token in html


def test_env_min_rvol_override(monkeypatch) -> None:
    monkeypatch.setenv("ORDERFLOW_MIN_RVOL", "5.0")
    res = evaluate_order_flow(_breakout_signal(rvol=2.5))  # 2.5 < 5.0 endi sust
    assert res["clc_confirmation"] is False
