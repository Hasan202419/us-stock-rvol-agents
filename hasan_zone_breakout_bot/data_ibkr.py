"""data_ibkr.py — IBKR ma'lumoti: IBKR.com hosted Web API (REST) yoki ib_insync (Gateway).

Ikki yo'l:
 1. IBKR.com Client Portal **Web API** (REST) — `IBKR_WEB_API_ENABLED=true` +
    `IBKR_WEB_API_BASE_URL`. Gateway/noutbuk SHART EMAS (bulutda/telefonda ishlaydi).
 2. `ib_insync` + IB Gateway/TWS — `IBKR_ENABLED=true` (kompyuterda ochiq turishi kerak).

Multi-timeframe bars (1H/5M/3M/1M) + bid/ask. Hech biri bo'lmasa None.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

# IBKR snapshot maydon kodlari (Client Portal API)
_F_LAST = "31"
_F_HIGH = "70"
_F_LOW = "71"
_F_CHG_PCT = "83"
_F_BID = "84"
_F_ASK = "86"
_F_VOL = "87"
_F_OPEN = "7295"
_F_PRIOR_CLOSE = "7296"

_CONID_CACHE: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Umumiy env yordamchilar
# ---------------------------------------------------------------------------

def web_enabled() -> bool:
    return os.getenv("IBKR_WEB_API_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def gateway_enabled() -> bool:
    return os.getenv("IBKR_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def enabled() -> bool:
    return web_enabled() or gateway_enabled()


def _base_url() -> str:
    return os.getenv("IBKR_WEB_API_BASE_URL", "").strip().rstrip("/")


def _verify_ssl() -> bool:
    return os.getenv("IBKR_WEB_API_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}


def _headers() -> Dict[str, str]:
    h = {"Accept": "application/json", "User-Agent": "hasan-zone-breakout-bot"}
    token = os.getenv("IBKR_WEB_API_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _timeout() -> float:
    try:
        return max(3.0, float(os.getenv("IBKR_WEB_API_TIMEOUT", "10")))
    except ValueError:
        return 10.0


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    base = _base_url()
    if not base:
        return None
    try:
        r = requests.get(f"{base}{path}", params=params, headers=_headers(),
                         timeout=_timeout(), verify=_verify_ssl())
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _post(path: str, payload: Dict[str, Any]) -> Optional[Any]:
    base = _base_url()
    if not base:
        return None
    try:
        r = requests.post(f"{base}{path}", json=payload, headers=_headers(),
                          timeout=_timeout(), verify=_verify_ssl())
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _num(value: Any) -> Optional[float]:
    """IBKR qiymatlari: "297.19", "45.6M", "C295.95", "0.42%" -> float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return None if v != v else v
    s = str(value).strip()
    if not s:
        return None
    if s[0] in {"C", "c"}:
        s = s[1:]
    mult = 1.0
    if s and s[-1] in {"M", "m"}:
        mult, s = 1_000_000.0, s[:-1]
    elif s and s[-1] in {"K", "k"}:
        mult, s = 1_000.0, s[:-1]
    elif s and s[-1] in {"B", "b"}:
        mult, s = 1_000_000_000.0, s[:-1]
    s = s.replace(",", "").replace("%", "")
    try:
        return float(s) * mult
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# IBKR.com Web API (REST) — hosted, Gateway shart emas
# ---------------------------------------------------------------------------

def _web_conid(symbol: str) -> Optional[int]:
    sym = symbol.strip().upper()
    if sym in _CONID_CACHE:
        return _CONID_CACHE[sym]
    data = _post("/iserver/secdef/search", {"symbol": sym, "name": False, "secType": "STK"})
    if not isinstance(data, list):
        return None
    rows = [r for r in data if isinstance(r, dict)]
    pick = next((r for r in rows if str(r.get("symbol", "")).upper() == sym), rows[0] if rows else None)
    if pick and pick.get("conid") is not None:
        try:
            cid = int(pick["conid"])
            _CONID_CACHE[sym] = cid
            return cid
        except (TypeError, ValueError):
            return None
    return None


def _web_history(conid: int, period: str, bar: str) -> List[Dict[str, Any]]:
    """Client Portal history -> [{t,o,h,l,c,v}]. bar: 1min/3min/5min/1h/1d."""
    data = _get("/iserver/marketdata/history",
                {"conid": conid, "period": period, "bar": bar, "outsideRth": "false"})
    if not isinstance(data, dict):
        return []
    bars = data.get("data")
    if not isinstance(bars, list):
        return []
    out: List[Dict[str, Any]] = []
    for b in bars:
        if not isinstance(b, dict):
            continue
        try:
            out.append({"t": int(b["t"]), "o": float(b["o"]), "h": float(b["h"]),
                        "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["t"])
    return out


def _fetch_web(ticker: str) -> Optional[Dict[str, Any]]:
    """IBKR.com hosted Web API orqali multi-timeframe + bid/ask."""
    sym = ticker.strip().upper()
    conid = _web_conid(sym)
    if conid is None:
        return None
    c5 = _web_history(conid, "2d", "5min")
    if len(c5) < 5:
        return None
    c3 = _web_history(conid, "1d", "3min")
    c1 = _web_history(conid, "1d", "1min")
    c60 = _web_history(conid, "5d", "1h")
    daily = _web_history(conid, "40d", "1d")

    # snapshot -> bid/ask + prior close
    bid = ask = prev_close = None
    fields = ",".join([_F_LAST, _F_BID, _F_ASK, _F_VOL, _F_PRIOR_CLOSE, _F_HIGH, _F_LOW, _F_OPEN])
    snap = _get("/iserver/marketdata/snapshot", {"conids": conid, "fields": fields})
    if isinstance(snap, list) and snap and isinstance(snap[0], dict):
        row = snap[0]
        bid = _num(row.get(_F_BID))
        ask = _num(row.get(_F_ASK))
        prev_close = _num(row.get(_F_PRIOR_CLOSE))

    from .indicators import avg_volume_from_daily

    last = c5[-1]
    if prev_close is None and len(daily) >= 2:
        prev_close = float(daily[-2]["c"])
    return {
        "ticker": sym,
        "price": float(last["c"]),
        "prev_close": prev_close,
        "current_volume": sum(c["v"] for c in c5),
        "avg_20d_volume": avg_volume_from_daily(daily, 20),
        "bid": bid, "ask": ask,
        "candles_1h": c60, "candles_5m": c5, "candles_3m": c3, "candles_1m": c1,
        "day_high": max(c["h"] for c in c5),
        "day_low": min(c["l"] for c in c5),
        "source": "ibkr_web",
        "data_complete": (bid is not None and ask is not None),
    }


# ---------------------------------------------------------------------------
# ib_insync (Gateway/TWS) — lokal/VPS
# ---------------------------------------------------------------------------

def _fetch_gateway(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        import ib_insync  # type: ignore[import-untyped]

        host = os.getenv("IB_GATEWAY_HOST", "127.0.0.1")
        port = int(os.getenv("IB_GATEWAY_PORT", "4002"))
        client_id = int(os.getenv("IBKR_CLIENT_ID", "9"))

        ib = ib_insync.IB()
        ib.connect(host, port, clientId=client_id, readonly=True, timeout=8)
        try:
            contract = ib_insync.Stock(ticker, "SMART", "USD")
            ib.qualifyContracts(contract)

            def _bars(duration: str, bar_size: str) -> List[Dict[str, Any]]:
                bars = ib.reqHistoricalData(
                    contract, endDateTime="", durationStr=duration,
                    barSizeSetting=bar_size, whatToShow="TRADES", useRTH=True, formatDate=2)
                rows: List[Dict[str, Any]] = []
                for b in bars or []:
                    ts = getattr(b, "date", None)
                    try:
                        t_ms = int(ts.timestamp() * 1000)
                    except (AttributeError, TypeError, ValueError):
                        continue
                    rows.append({"t": t_ms, "o": float(b.open), "h": float(b.high),
                                 "l": float(b.low), "c": float(b.close), "v": float(b.volume or 0)})
                rows.sort(key=lambda x: x["t"])
                return rows

            c60 = _bars("3 D", "1 hour")
            c5 = _bars("2 D", "5 mins")
            c3 = _bars("1 D", "3 mins")
            c1 = _bars("1 D", "1 min")
            daily = _bars("40 D", "1 day")
            if len(c5) < 5:
                return None

            from .indicators import avg_volume_from_daily

            last = c5[-1]
            return {
                "ticker": ticker.upper(), "price": float(last["c"]),
                "prev_close": float(daily[-2]["c"]) if len(daily) >= 2 else None,
                "current_volume": sum(c["v"] for c in c5),
                "avg_20d_volume": avg_volume_from_daily(daily, 20),
                "bid": None, "ask": None,
                "candles_1h": c60, "candles_5m": c5, "candles_3m": c3, "candles_1m": c1,
                "day_high": max(c["h"] for c in c5), "day_low": min(c["l"] for c in c5),
                "source": "ibkr_gateway", "data_complete": False,
            }
        finally:
            ib.disconnect()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Asosiy: Web API -> Gateway
# ---------------------------------------------------------------------------

def fetch(ticker: str) -> Optional[Dict[str, Any]]:
    """IBKR ma'lumoti: avval IBKR.com Web API, bo'lmasa ib_insync Gateway."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    if web_enabled():
        try:
            data = _fetch_web(sym)
            if data and data.get("price"):
                return data
        except Exception:
            pass
    if gateway_enabled():
        return _fetch_gateway(sym)
    return None


def status_line() -> str:
    """Holat (diagnostika uchun)."""
    if web_enabled():
        base = _base_url()
        if not base:
            return "IBKR Web API: enabled, lekin IBKR_WEB_API_BASE_URL yo'q"
        info = _get("/iserver/auth/status") or _get("/tickle")
        return f"IBKR.com Web API: {'ulangan' if info is not None else 'javob yo''q'} ({base})"
    if gateway_enabled():
        return "IBKR: ib_insync Gateway rejimi (IBKR_ENABLED=true)"
    return "IBKR: OFF"
