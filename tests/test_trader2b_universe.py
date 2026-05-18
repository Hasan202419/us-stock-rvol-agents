"""trader2B universe va prop tartiblash."""

from __future__ import annotations

from agents.prop_scalp_rank import prop_scalp_priority_score, rank_for_prop_scalp
from agents.trader2b_universe import CORE_LIQUID_SYMBOLS, build_trader2b_universe


def test_core_symbols_in_universe() -> None:
    uni = build_trader2b_universe(limit=0)
    for sym in ("AAPL", "TSLA", "PLTR", "ORCL"):
        assert sym in uni
    assert "AAPL" in CORE_LIQUID_SYMBOLS


def test_prop_scalp_rank_prefers_mtf_and_amt() -> None:
    low = {"ticker": "X", "score": 50, "mtf_alignment_count": 0, "mtf_alignment_total": 3}
    high = {
        "ticker": "Y",
        "score": 50,
        "mtf_alignment_count": 3,
        "mtf_alignment_total": 3,
        "amt_buy_signal": True,
        "strategy_pass": True,
    }
    assert prop_scalp_priority_score(high) > prop_scalp_priority_score(low)
    ranked = rank_for_prop_scalp([low, high])
    assert ranked[0]["ticker"] == "Y"
