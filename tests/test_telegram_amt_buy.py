"""AMT BUY Telegram formatlari."""

from __future__ import annotations

from agents.telegram_amt_buy import (
    build_amt_buy_alert_html,
    collect_amt_buy_signals,
    format_amt_buy_line,
)


def test_collect_amt_buy_signals_sorts_by_score() -> None:
    results = {
        "A": {"ticker": "A", "amt_buy_signal": True, "score": 10},
        "B": {"ticker": "B", "amt_buy_signal": False, "score": 99},
        "C": {"ticker": "C", "amt_buy_signal": True, "score": 50},
    }
    rows = collect_amt_buy_signals(results)
    assert [r["ticker"] for r in rows] == ["C", "A"]


def test_format_amt_buy_line_contains_zones() -> None:
    html = format_amt_buy_line(
        {
            "ticker": "AAPL",
            "amt_buy_signal": True,
            "amt_buy_from_val": True,
            "amt_val": 180.5,
            "amt_poc_proxy": 182.0,
            "amt_vah": 184.0,
            "trade_levels_line": "KIRISH 181 · SL 179 · TP1 183",
        },
        chart_url="https://example.com/chart",
    )
    assert "AAPL" in html
    assert "AMT BUY" in html
    assert "VAL" in html
    assert "KIRISH" in html


def test_build_amt_buy_alert_html_empty() -> None:
    body = build_amt_buy_alert_html([], summary={"tickers_scanned": 100, "amt_buy_count": 0})
    assert "AMT" in body
    assert "yo‘q" in body or "yo'q" in body


def test_build_amt_buy_alert_html_includes_near_watch() -> None:
    body = build_amt_buy_alert_html(
        [],
        summary={"tickers_scanned": 500, "amt_buy_count": 0},
        near_rows=[{"ticker": "MSFT", "amt_ok": True, "amt_val": 400.0, "price": 401.0}],
    )
    assert "VAL yaqin" in body
    assert "MSFT" in body
