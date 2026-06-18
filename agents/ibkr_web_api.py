"""IBKR Client Portal Web API (REST) — hosted ulanish, lokal TWS/Gateway shart emas.

Eski `ibkr_market_data.py` `ib_insync` + IB Gateway (kompyuterda ochiq) talab qiladi.
Bu modul esa IBKR **Client Portal Web API** REST endpointlariga ulanadi — gateway bulutda
(yoki OAuth-proksi orqali) bo'lishi mumkin, foydalanuvchi noutbuki ochiq turishi shart emas.

Sozlash (env):
- `IBKR_WEB_API_ENABLED=true`
- `IBKR_WEB_API_BASE_URL` — masalan `https://your-cp-gateway/v1/api` yoki OAuth-proksi URL
- `IBKR_WEB_API_TOKEN` — ixtiyoriy Bearer token (OAuth/sessiya)
- `IBKR_WEB_API_VERIFY_SSL=false` — self-signed gateway uchun

Snapshot/candles natijasi mavjud pipeline formati bilan mos (t,o,h,l,c,v / price,volume,previous_close).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

# IBKR snapshot maydon kodlari (Client Portal API).
_FIELD_LAST = "31"
_FIELD_HIGH = "70"
_FIELD_LOW = "71"
_FIELD_CHANGE = "82"
_FIELD_CHANGE_PCT = "83"
_FIELD_BID = "84"
_FIELD_ASK = "86"
_FIELD_VOLUME = "87"
_FIELD_OPEN = "7295"
_FIELD_PRIOR_CLOSE = "7296"

_SNAPSHOT_FIELDS = ",".join(
    [_FIELD_LAST, _FIELD_HIGH, _FIELD_LOW, _FIELD_CHANGE, _FIELD_CHANGE_PCT,
     _FIELD_BID, _FIELD_ASK, _FIELD_VOLUME, _FIELD_OPEN, _FIELD_PRIOR_CLOSE]
)

_CONID_CACHE: Dict[str, int] = {}


def ibkr_web_enabled() -> bool:
    return os.getenv("IBKR_WEB_API_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _base_url() -> str:
    return os.getenv("IBKR_WEB_API_BASE_URL", "").strip().rstrip("/")


def _verify_ssl() -> bool:
    return os.getenv("IBKR_WEB_API_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}


def _headers() -> Dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "us-stock-rvol-agents"}
    token = os.getenv("IBKR_WEB_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _timeout() -> float:
    try:
        return max(2.0, float(os.getenv("IBKR_WEB_API_TIMEOUT", "8")))
    except ValueError:
        return 8.0


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    base = _base_url()
    if not base:
        return None
    try:
        r = requests.get(
            f"{base}{path}", params=params, headers=_headers(),
            timeout=_timeout(), verify=_verify_ssl(),
        )
        if not r.ok:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def _post(path: str, payload: Dict[str, Any]) -> Optional[Any]:
    base = _base_url()
    if not base:
        return None
    try:
        r = requests.post(
            f"{base}{path}", json=payload, headers=_headers(),
            timeout=_timeout(), verify=_verify_ssl(),
        )
        if not r.ok:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def _parse_number(value: Any) -> Optional[float]:
    """IBKR qiymatlari: "297.19", "45.6M", "1.2K", "C297.19" (close prefiks) — float ga."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return None if v != v else v
    s = str(value).strip()
    if not s:
        return None
    # 'C' prefiksi = prior close belgisi; olib tashlaymiz
    if s and s[0] in {"C", "c"}:
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


def web_search_conid(symbol: str) -> Optional[int]:
    """Symbol -> IBKR conid (STK). Keshlanadi."""
    sym = symbol.strip().upper()
    if not sym:
        return None
    if sym in _CONID_CACHE:
        return _CONID_CACHE[sym]
    data = _post("/iserver/secdef/search", {"symbol": sym, "name": False, "secType": "STK"})
    if not isinstance(data, list):
        return None
    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol", "")).upper() == sym:
            conid = row.get("conid")
            try:
                cid = int(conid)
                _CONID_CACHE[sym] = cid
                return cid
            except (TypeError, ValueError):
                continue
    # exact mos kelmasa — birinchi natija
    first = data[0] if data else None
    if isinstance(first, dict) and first.get("conid") is not None:
        try:
            cid = int(first["conid"])
            _CONID_CACHE[sym] = cid
            return cid
        except (TypeError, ValueError):
            return None
    return None


def fetch_ibkr_web_snapshot(ticker: str) -> Dict[str, Any]:
    """Bitta ticker uchun jonli snapshot (price/volume/previous_close/change). Xato bo'lsa {}."""
    if not ibkr_web_enabled():
        return {}
    sym = str(ticker or "").strip().upper()
    if not sym:
        return {}
    conid = web_search_conid(sym)
    if conid is None:
        return {}
    data = _get("/iserver/marketdata/snapshot", {"conids": conid, "fields": _SNAPSHOT_FIELDS})
    if not isinstance(data, list) or not data:
        return {}
    row = data[0] if isinstance(data[0], dict) else {}
    last = _parse_number(row.get(_FIELD_LAST))
    if last is None or last <= 0:
        return {}
    out: Dict[str, Any] = {
        "ticker": sym,
        "price": round(last, 4),
        "quote_source": "ibkr_web",
        "candles_source": "ibkr_web",
    }
    vol = _parse_number(row.get(_FIELD_VOLUME))
    if vol is not None:
        out["volume"] = int(vol)
    prev = _parse_number(row.get(_FIELD_PRIOR_CLOSE))
    if prev is not None and prev > 0:
        out["previous_close"] = round(prev, 4)
    chg_pct = _parse_number(row.get(_FIELD_CHANGE_PCT))
    if chg_pct is not None:
        out["change_percent"] = round(chg_pct, 2)
    for key, field in (("today_high", _FIELD_HIGH), ("today_low", _FIELD_LOW), ("today_open", _FIELD_OPEN)):
        val = _parse_number(row.get(field))
        if val is not None:
            out[key] = round(val, 4)
    return out


def fetch_ibkr_web_daily_candles(ticker: str, days: int = 60) -> List[Dict[str, Any]]:
    """Kunlik OHLCV shamlar (t,o,h,l,c,v). Xato bo'lsa []."""
    if not ibkr_web_enabled():
        return []
    sym = str(ticker or "").strip().upper()
    if not sym:
        return []
    conid = web_search_conid(sym)
    if conid is None:
        return []
    period = f"{max(1, int(days))}d"
    data = _get(
        "/iserver/marketdata/history",
        {"conid": conid, "period": period, "bar": "1d", "outsideRth": "false"},
    )
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
            out.append({
                "t": int(b["t"]),
                "o": float(b["o"]),
                "h": float(b["h"]),
                "l": float(b["l"]),
                "c": float(b["c"]),
                "v": float(b.get("v") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["t"])
    return out


def ibkr_web_status_line() -> str:
    """Telegram /status uchun bir qator (ASCII + minimal HTML)."""
    if not ibkr_web_enabled():
        return "IBKR Web API: <i>OFF</i>"
    base = _base_url()
    if not base:
        return "IBKR Web API: <i>enabled</i> · IBKR_WEB_API_BASE_URL yo'q"
    # Yengil sog'liq tekshiruvi
    info = _get("/iserver/auth/status") or _get("/tickle")
    if info is not None:
        return f"IBKR Web API: <b>ulangan</b> ({base})"
    return f"IBKR Web API: <i>enabled</i> · javob yo'q ({base}) — sessiya/auth tekshiring"
