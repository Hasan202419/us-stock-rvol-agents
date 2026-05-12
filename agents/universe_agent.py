import os
from typing import List

import requests

from agents.finviz_elite_export import fetch_export_csv_bytes, symbols_from_finviz_csv


class UniverseAgent:
    """Fetch a starter universe of active US stock symbols."""

    def __init__(self, polygon_api_key: str | None = None, alpaca_api_key: str | None = None, alpaca_secret_key: str | None = None) -> None:
        self.polygon_api_key = polygon_api_key or os.getenv("POLYGON_API_KEY", "")
        self.alpaca_api_key = alpaca_api_key or os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret_key = alpaca_secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.finviz_auth = os.getenv("FINVIZ_ELITE_AUTH", "").strip()
        self.finviz_export_query = os.getenv("FINVIZ_ELITE_EXPORT_QUERY", "").strip()

    def fetch_symbols(self, limit: int = 100, *, use_finviz_elite: bool = False) -> List[str]:
        """Return tradable US symbols; optional Finviz Elite CSV first."""

        if use_finviz_elite or os.getenv("FETCH_UNIVERSE_FINVIZ_FIRST", "").strip().lower() in {"1", "true", "yes", "on"}:
            symbols = self._fetch_from_finviz_elite(limit)
            if symbols:
                return symbols

        symbols = self._fetch_from_alpaca(limit)
        if symbols:
            return symbols

        symbols = self._fetch_from_polygon(limit)
        if symbols:
            return symbols

        # Fallback without paid feeds: keep a broader, liquid universe so scans are less likely to return empty.
        fallback_symbols = [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "META",
            "GOOGL",
            "TSLA",
            "AMD",
            "NFLX",
            "AVGO",
            "QCOM",
            "INTC",
            "MU",
            "PLTR",
            "SMCI",
            "UBER",
            "CRM",
            "ORCL",
            "JPM",
            "BAC",
            "XOM",
            "CVX",
            "KO",
            "PEP",
            "WMT",
            "COST",
            "DIS",
            "NKE",
            "PYPL",
            "SHOP",
        ]
        return fallback_symbols[:limit]

    def _fetch_from_finviz_elite(self, limit: int) -> List[str]:
        if not self.finviz_auth or not self.finviz_export_query:
            return []
        try:
            raw, _url = fetch_export_csv_bytes(
                auth=self.finviz_auth,
                export_query=self.finviz_export_query,
                timeout_sec=60.0,
            )
        except (requests.RequestException, OSError, ValueError):
            return []
        try:
            return symbols_from_finviz_csv(raw, limit=limit)
        except Exception:
            return []

    def _fetch_from_alpaca(self, limit: int) -> List[str]:
        if not self.alpaca_api_key or not self.alpaca_secret_key:
            return []

        url = "https://paper-api.alpaca.markets/v2/assets"
        headers = {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }
        params = {"status": "active", "asset_class": "us_equity"}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            assets = response.json()
        except requests.RequestException:
            return []

        symbols = [
            asset["symbol"]
            for asset in assets
            if asset.get("tradable") and asset.get("exchange") in {"NYSE", "NASDAQ", "AMEX"}
        ]
        return sorted(symbols)[:limit]

    def _fetch_from_polygon(self, limit: int) -> List[str]:
        if not self.polygon_api_key:
            return []

        page_size = min(max(100, limit), 1000)
        url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "market": "stocks",
            "active": "true",
            "locale": "us",
            "limit": page_size,
            "apiKey": self.polygon_api_key,
        }

        out: list[str] = []
        seen: set[str] = set()
        next_url: str | None = None
        pages = 0
        # Polygon sahifalari o'zgaruvchan bo'lishi mumkin; katta limitda yetarli aylanish.
        max_pages = max(10, (limit + page_size - 1) // page_size + 15)

        while pages < max_pages and len(out) < limit:
            try:
                if next_url:
                    response = requests.get(next_url, timeout=20)
                else:
                    response = requests.get(url, params=params, timeout=20)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                break

            for item in payload.get("results", []) or []:
                ticker = str(item.get("ticker") or "").strip().upper()
                if not ticker or ticker in seen:
                    continue
                seen.add(ticker)
                out.append(ticker)
                if len(out) >= limit:
                    break

            raw_next = payload.get("next_url")
            if not raw_next or len(out) >= limit:
                break
            next_url = f"{raw_next}&apiKey={self.polygon_api_key}" if "apiKey=" not in raw_next else raw_next
            pages += 1

        return sorted(out)[:limit]
