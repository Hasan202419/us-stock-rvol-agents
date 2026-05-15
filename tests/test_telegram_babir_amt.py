"""Babir skan + AMT VAL↑ birlashtirish."""

from __future__ import annotations

from agents.telegram_amt_buy import enrich_ranked_for_babir, format_amt_zone_inline


def test_format_amt_zone_inline_buy_val_up() -> None:
    line = format_amt_zone_inline(
        {
            "amt_ok": True,
            "amt_buy_signal": True,
            "amt_buy_from_val": True,
            "amt_val": 44.97,
            "amt_poc_proxy": 45.13,
            "amt_vah": 45.11,
        }
    )
    assert "AMT BUY" in line
    assert "VAL↑" in line
    assert "44.97" in line
    assert "45.13" in line


def test_enrich_ranked_for_babir_inserts_amt_buy() -> None:
    ranked = [{"ticker": "AAA", "strategy_pass": True, "score": 5}]
    summary = {
        "amt_buy_signals": [
            {
                "ticker": "ZZZ",
                "amt_buy_signal": True,
                "amt_buy_from_val": True,
                "strategy_pass": False,
                "score": 99,
            }
        ],
        "amt_near_val_signals": [],
    }
    out = enrich_ranked_for_babir(ranked, summary)
    assert out[0]["ticker"] == "ZZZ"
    assert out[0].get("babir_amt_card")
    assert any(r["ticker"] == "AAA" for r in out)
