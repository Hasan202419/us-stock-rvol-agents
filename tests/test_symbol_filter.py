"""symbol_filter — warrant/unit chiqarish."""

from __future__ import annotations

from agents.symbol_filter import filter_scannable_symbols, is_scannable_us_equity


def test_rejects_warrants_and_units() -> None:
    assert not is_scannable_us_equity("BBBY.WS")
    assert not is_scannable_us_equity("BCS.U")
    assert not is_scannable_us_equity("BC.PRC")
    assert not is_scannable_us_equity("BEP.PRA")


def test_allows_common_stocks() -> None:
    assert is_scannable_us_equity("AAPL")
    assert is_scannable_us_equity("TSLA")
    assert is_scannable_us_equity("BRK.B")
    assert is_scannable_us_equity("SPY")


def test_filter_dedupes() -> None:
    out = filter_scannable_symbols(["AAPL", "BBBY.WS", "AAPL", "TSLA"])
    assert out == ["AAPL", "TSLA"]
