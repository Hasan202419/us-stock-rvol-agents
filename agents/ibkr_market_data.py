"""Interactive Brokers (IBKR) — ixtiyoriy ma’lumot manbai (TWS / IB Gateway orqali).

Render cloud workerda Gateway odatda yo‘q — lokal/VPN da `IBKR_ENABLED=true` va Gateway ishga tushgan bo‘lsa
snapshot olish mumkin. Cloud skan uchun Alpaca + Polygon + Yahoo ishlatiladi.
"""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from typing import Any, Dict

_IB_INSYNC = None
try:
    import ib_insync as _IB_INSYNC  # type: ignore[import-untyped]
except ImportError:
    _IB_INSYNC = None


def ibkr_enabled() -> bool:
    return os.getenv("IBKR_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _gateway_host() -> str:
    return os.getenv("IB_GATEWAY_HOST", os.getenv("IBKR_HOST", "127.0.0.1")).strip() or "127.0.0.1"


def _gateway_port() -> int:
    raw = os.getenv("IB_GATEWAY_PORT", os.getenv("IBKR_PORT", "4002")).strip()
    try:
        return int(raw)
    except ValueError:
        return 4002


def _client_id() -> int:
    try:
        return max(1, int(os.getenv("IBKR_CLIENT_ID", "7")))
    except ValueError:
        return 7


def gateway_tcp_reachable(timeout_sec: float = 2.0) -> bool:
    """Gateway port ochiqmi (tez socket tekshiruv)."""

    if not ibkr_enabled():
        return False
    host, port = _gateway_host(), _gateway_port()
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


@contextmanager
def ibkr_session(*, readonly: bool = True, timeout: float = 8.0):
    """Bitta IB ulanishni ochib, ish tugagach yopadi (ko‘p ticker uchun qayta ulanmaslik).

    `with ibkr_session() as ib:` — ib None bo‘lsa (gateway/ib_insync yo‘q) chaqiruvchi {} qaytaradi.
    """

    if not ibkr_enabled() or _IB_INSYNC is None:
        yield None
        return

    ib = _IB_INSYNC.IB()
    try:
        ib.connect(_gateway_host(), _gateway_port(), clientId=_client_id(), readonly=readonly, timeout=timeout)
        yield ib
    except Exception:
        yield None
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def _snapshot_with_ib(ib: Any, symbol: str) -> Dict[str, Any]:
    """Ochiq `ib` ulanishida bitta ticker snapshot — price/volume/previous_close."""

    try:
        contract = _IB_INSYNC.Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        tickers = ib.reqMktData(contract, "", False, False)
        ib.sleep(1.5)
        last = float(tickers.last or tickers.close or 0)
        prev_close = float(tickers.close or 0)
        vol = int(tickers.volume or 0)
        ib.cancelMktData(contract)
        if last <= 0:
            return {}
        out: Dict[str, Any] = {
            "ticker": symbol,
            "price": round(last, 4),
            "volume": vol,
            "quote_source": "ibkr",
            "candles_source": "ibkr",
        }
        if prev_close > 0:
            out["previous_close"] = round(prev_close, 4)
        return out
    except Exception:
        return {}


def _candles_with_ib(ib: Any, symbol: str, days: int) -> list[Dict[str, Any]]:
    """Ochiq `ib` ulanishida kunlik OHLCV shamlar — Polygon/Yahoo formati (t,o,h,l,c,v)."""

    try:
        contract = _IB_INSYNC.Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=f"{max(1, int(days))} D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=2,
        )
        out: list[Dict[str, Any]] = []
        for bar in bars or []:
            ts = getattr(bar, "date", None)
            try:
                t_ms = int(ts.timestamp() * 1000)
            except (AttributeError, TypeError, ValueError):
                continue
            out.append(
                {
                    "t": t_ms,
                    "o": float(bar.open),
                    "h": float(bar.high),
                    "l": float(bar.low),
                    "c": float(bar.close),
                    "v": float(bar.volume or 0),
                }
            )
        out.sort(key=lambda b: b["t"])
        return out
    except Exception:
        return []


def fetch_ibkr_snapshot(ticker: str) -> Dict[str, Any]:
    """Bitta ticker uchun narx/hajm/previous_close (ib_insync bo‘lsa). Gateway yo‘q bo‘lsa {}."""

    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {}
    with ibkr_session() as ib:
        if ib is None:
            return {}
        return _snapshot_with_ib(ib, symbol)


def fetch_ibkr_daily_candles(ticker: str, days: int = 60) -> list[Dict[str, Any]]:
    """Kunlik OHLCV shamlar (RVOL/ignition uchun). Gateway yo‘q bo‘lsa []."""

    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return []
    with ibkr_session() as ib:
        if ib is None:
            return []
        return _candles_with_ib(ib, symbol, days)


def ibkr_status_line() -> str:
    """Telegram /status uchun bir qator HTML (escape qilinmasin — faqat ASCII)."""

    if not ibkr_enabled():
        return "IBKR: <i>OFF</i> (cloud: Alpaca/Polygon/Yahoo)"
    host = _gateway_host()
    port = _gateway_port()
    if _IB_INSYNC is None:
        return "IBKR: <i>enabled</i> · pip install ib_insync · Gateway not tested"
    if gateway_tcp_reachable():
        return f"IBKR: <b>Gateway reachable</b> ({host}:{port})"
    return f"IBKR: <i>enabled</i> · Gateway unreachable ({host}:{port}) — TWS/IBG ishga tushiring"
