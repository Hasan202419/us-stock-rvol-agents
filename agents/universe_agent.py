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

        # A small fallback keeps the demo usable while API keys are being added.
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN", "GOOGL"][:limit]

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

        url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "market": "stocks",
            "active": "true",
            "locale": "us",
            "limit": min(limit, 1000),
            "apiKey": self.polygon_api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            results = response.json().get("results", [])
        except requests.RequestException:
            return []

        return sorted(item["ticker"] for item in results if item.get("ticker"))[:limit]
