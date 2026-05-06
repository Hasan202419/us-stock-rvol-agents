from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import requests

from src.config.settings import get_settings
from src.models.schemas import HalalReport

CACHE_FILE = Path(__file__).resolve().parents[2] / ".zoya_cache.json"
CACHE_TTL_SEC = 86400


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")


def fetch_zoya_compliance(symbol: str, api_key: Optional[str] = None) -> HalalReport:
    """Zoya GraphQL (SPEC bilan mos). API kalit bo‘lmasa → unknown / fallback."""
    key = api_key or get_settings().zoya_api_key
    if not key:
        return HalalReport(symbol=symbol, status="unknown", source="fallback", detail="ZOYA_API_KEY missing")

    cache = _load_cache()
    now = time.time()
    ent = cache.get(symbol)
    if ent and (now - float(ent.get("ts", 0))) < CACHE_TTL_SEC:
        return HalalReport(
            symbol=symbol,
            status=ent["status"],  # type: ignore[arg-type]
            source="cache",
            detail=str(ent.get("detail", "")),
        )

    query = {
        "query": """
            query StockCompliance($ticker: String!) {
              stock(ticker: $ticker) {
                ticker
                shariahCompliance {
                  status
                  standard
                }
              }
            }
        """,
        "variables": {"ticker": symbol},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post("https://api.zoya.finance/graphql", json=query, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
        raw = (
            data.get("data", {})
            .get("stock", {})
            .get("shariahCompliance", {})
            .get("status", "unknown")
            or "unknown"
        )
        s = str(raw).lower()
        if "compliant" in s and "non" not in s:
            st = "compliant"
        elif "non" in s or "haram" in s:
            st = "non_compliant"
        elif "question" in s or "doubt" in s:
            st = "questionable"
        else:
            st = "unknown"

        cache[symbol] = {"status": st, "ts": now, "detail": raw}
        _save_cache(cache)
        return HalalReport(symbol=symbol, status=st, source="zoya", detail=str(raw))
    except Exception as exc:  # noqa: BLE001
        return HalalReport(symbol=symbol, status="unknown", source="fallback", detail=str(exc))
