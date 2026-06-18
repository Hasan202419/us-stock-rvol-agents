"""ibkr_web_api — REST mijoz, tarmoqsiz (requests mock)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import agents.ibkr_web_api as web


class _FakeResp:
    def __init__(self, payload: Any, ok: bool = True) -> None:
        self._payload = payload
        self.ok = ok

    def json(self) -> Any:
        return self._payload


def _setup(monkeypatch, *, base="https://gw/v1/api", enabled=True) -> None:
    monkeypatch.setenv("IBKR_WEB_API_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("IBKR_WEB_API_BASE_URL", base)
    web._CONID_CACHE.clear()


# ---------------------------------------------------------------------------
# _parse_number
# ---------------------------------------------------------------------------

def test_parse_number_plain() -> None:
    assert web._parse_number("297.19") == 297.19
    assert web._parse_number(297.19) == 297.19


def test_parse_number_suffixes() -> None:
    assert web._parse_number("45.6M") == 45_600_000.0
    assert web._parse_number("1.2K") == 1_200.0
    assert web._parse_number("3B") == 3_000_000_000.0


def test_parse_number_close_prefix_and_pct() -> None:
    assert web._parse_number("C295.95") == 295.95
    assert web._parse_number("0.42%") == 0.42


def test_parse_number_garbage_none() -> None:
    assert web._parse_number("") is None
    assert web._parse_number(None) is None
    assert web._parse_number("abc") is None


# ---------------------------------------------------------------------------
# web_search_conid
# ---------------------------------------------------------------------------

def test_search_conid_exact_match(monkeypatch) -> None:
    _setup(monkeypatch)

    def fake_post(path: str, payload: Dict[str, Any]) -> Any:
        return [{"symbol": "AAPL", "conid": 265598}, {"symbol": "AAPU", "conid": 1}]

    monkeypatch.setattr(web, "_post", fake_post)
    assert web.web_search_conid("AAPL") == 265598


def test_search_conid_caches(monkeypatch) -> None:
    _setup(monkeypatch)
    calls = {"n": 0}

    def fake_post(path: str, payload: Dict[str, Any]) -> Any:
        calls["n"] += 1
        return [{"symbol": "TSLA", "conid": 76792991}]

    monkeypatch.setattr(web, "_post", fake_post)
    assert web.web_search_conid("TSLA") == 76792991
    assert web.web_search_conid("TSLA") == 76792991
    assert calls["n"] == 1  # ikkinchisi keshdan


def test_search_conid_empty(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "_post", lambda p, x: [])
    assert web.web_search_conid("ZZZ") is None


# ---------------------------------------------------------------------------
# fetch_ibkr_web_snapshot
# ---------------------------------------------------------------------------

def test_snapshot_disabled_returns_empty(monkeypatch) -> None:
    _setup(monkeypatch, enabled=False)
    assert web.fetch_ibkr_web_snapshot("AAPL") == {}


def test_snapshot_full(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "web_search_conid", lambda s: 265598)

    def fake_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return [{
            "31": "297.19", "87": "45.6M", "7296": "C295.95",
            "83": "0.42", "70": "300.57", "71": "295.62", "7295": "298.43",
        }]

    monkeypatch.setattr(web, "_get", fake_get)
    snap = web.fetch_ibkr_web_snapshot("AAPL")
    assert snap["ticker"] == "AAPL"
    assert snap["price"] == 297.19
    assert snap["volume"] == 45_600_000
    assert snap["previous_close"] == 295.95
    assert snap["change_percent"] == 0.42
    assert snap["today_high"] == 300.57
    assert snap["quote_source"] == "ibkr_web"


def test_snapshot_no_last_price_empty(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "web_search_conid", lambda s: 1)
    monkeypatch.setattr(web, "_get", lambda p, x=None: [{"87": "1M"}])  # last yo'q
    assert web.fetch_ibkr_web_snapshot("AAPL") == {}


def test_snapshot_no_conid_empty(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "web_search_conid", lambda s: None)
    assert web.fetch_ibkr_web_snapshot("AAPL") == {}


# ---------------------------------------------------------------------------
# fetch_ibkr_web_daily_candles
# ---------------------------------------------------------------------------

def test_candles_full(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "web_search_conid", lambda s: 265598)

    def fake_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return {"data": [
            {"t": 1_700_000_000_000, "o": 100, "h": 102, "l": 99, "c": 101, "v": 1_000_000},
            {"t": 1_700_086_400_000, "o": 101, "h": 105, "l": 100, "c": 104, "v": 2_000_000},
        ]}

    monkeypatch.setattr(web, "_get", fake_get)
    candles = web.fetch_ibkr_web_daily_candles("AAPL", days=30)
    assert len(candles) == 2
    assert candles[0]["c"] == 101
    assert candles[-1]["v"] == 2_000_000


def test_candles_disabled_empty(monkeypatch) -> None:
    _setup(monkeypatch, enabled=False)
    assert web.fetch_ibkr_web_daily_candles("AAPL") == []


def test_candles_bad_payload_empty(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "web_search_conid", lambda s: 1)
    monkeypatch.setattr(web, "_get", lambda p, x=None: {"nope": []})
    assert web.fetch_ibkr_web_daily_candles("AAPL") == []


# ---------------------------------------------------------------------------
# status line
# ---------------------------------------------------------------------------

def test_status_off(monkeypatch) -> None:
    _setup(monkeypatch, enabled=False)
    assert "OFF" in web.ibkr_web_status_line()


def test_status_connected(monkeypatch) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(web, "_get", lambda p, x=None: {"authenticated": True})
    assert "ulangan" in web.ibkr_web_status_line()


def test_status_no_base(monkeypatch) -> None:
    _setup(monkeypatch, base="")
    assert "BASE_URL" in web.ibkr_web_status_line()
