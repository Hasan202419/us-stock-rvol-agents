"""Tests for agents.trade_plan_format."""

from __future__ import annotations

from agents.trade_plan_format import (
    TRADE_PLAN_KEYS,
    deterministic_trade_plan_from_signal,
    format_trade_plan_markdown,
    parse_trade_plan_dict,
    trade_plan_dict_has_content,
)


def test_parse_trade_plan_dict_filters_keys() -> None:
    raw = {"company": "Acme", "noise": "x", "reason_catalyst": "Earnings"}
    d = parse_trade_plan_dict(raw)
    assert d["company"] == "Acme"
    assert d["reason_catalyst"] == "Earnings"
    assert "noise" not in d
    assert all(k in d for k in TRADE_PLAN_KEYS)


def test_parse_trade_plan_dict_accepts_json_string() -> None:
    raw = '{"company": "Globex", "reason_catalyst": "Guidance"}'
    d = parse_trade_plan_dict(raw)
    assert d["company"] == "Globex"
    assert d["reason_catalyst"] == "Guidance"


def test_parse_trade_plan_dict_invalid_json_string_returns_empty() -> None:
    assert parse_trade_plan_dict("{not json") == {}


def test_trade_plan_dict_has_content_false_when_empty() -> None:
    assert trade_plan_dict_has_content({k: "" for k in TRADE_PLAN_KEYS}) is False


def test_format_trade_plan_markdown_includes_ticker() -> None:
    tp = {k: "" for k in TRADE_PLAN_KEYS}
    tp["company"] = "TestCo"
    tp["reason_catalyst"] = "Volume"
    md = format_trade_plan_markdown("AAA", tp)
    assert "AAA" in md
    assert "TestCo" in md
    assert "Volume" in md


def test_deterministic_en_contains_ticker_and_price() -> None:
    s = {
        "ticker": "zz",
        "price": 12.5,
        "rvol": 2.0,
        "strategy_name": "rvol_momentum",
        "stop_suggestion": 11.0,
        "take_profit_suggestion": 14.0,
    }
    m = deterministic_trade_plan_from_signal(s, lang="en")
    assert "ZZ" in m
    assert "12.5000" in m
