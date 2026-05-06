from agents.finviz_elite_export import build_export_url, symbols_from_finviz_csv


def test_build_export_url_strips_auth_from_query() -> None:
    url = build_export_url(
        auth="token-abc",
        export_query="v=1&f=cap_large&auth=SHOULD_DROP",
    )
    assert "auth=token-abc" in url
    assert "SHOULD_DROP" not in url


def test_symbols_from_csv_ticker_column() -> None:
    raw = b"No.,Ticker,Price\n1,AAPL,100\n2,MSFT,200\n"
    assert symbols_from_finviz_csv(raw, limit=10) == ["AAPL", "MSFT"]
