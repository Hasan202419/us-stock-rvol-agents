import os
import time as time_module
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import requests

from agents.session_calendar import bar_end_in_regular_session


class MarketDataAgent:
    """Fetch price, volume, previous close, and candles from market data APIs."""

    def __init__(
        self,
        polygon_api_key: str | None = None,
        finnhub_api_key: str | None = None,
        alpaca_api_key: str | None = None,
        alpaca_secret_key: str | None = None,
        data_delay_minutes: int | None = None,
    ) -> None:
        self.polygon_api_key = polygon_api_key or os.getenv("POLYGON_API_KEY", "")
        self.finnhub_api_key = finnhub_api_key or os.getenv("FINNHUB_API_KEY", "")
        self.alpaca_api_key = alpaca_api_key or os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret_key = alpaca_secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.data_delay_minutes = data_delay_minutes or int(os.getenv("DATA_DELAY_MINUTES", "15"))
        # Yahoo Finance via yfinance: no API key; optional fallback when paid feeds miss fields.
        self.yahoo_finance_enabled = os.getenv("YAHOO_FINANCE_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.intraday_cache_ttl = float(os.getenv("INTRADAY_CACHE_TTL_SECONDS", "45"))
        self.http_max_retries = max(1, int(os.getenv("MARKET_HTTP_MAX_RETRIES", "4")))
        self.http_backoff_base = float(os.getenv("MARKET_HTTP_BACKOFF_BASE_SEC", "0.75"))
        self.regular_session_filter = os.getenv("FILTER_INTRADAY_REGULAR_SESSION", "false").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        self._intraday_cache: Dict[tuple[str, int], tuple[float, List[Dict[str, Any]]]] = {}

    def fetch_market_data(self, ticker: str) -> Dict[str, Any]:
        """Build one market data record for a ticker.

        Free and paper accounts often receive delayed data. The dashboard keeps
        that visible by carrying `data_delay` into every generated signal.
        """
        quote = self._fetch_finnhub_quote(ticker)
        snapshot = self._fetch_polygon_snapshot(ticker)
        candles = self._fetch_polygon_daily_candles(ticker)
        alpaca_bar = self._fetch_alpaca_latest_bar(ticker)
        yahoo_bundle = self._fetch_yahoo_daily_bundle(ticker)

        price = (
            quote.get("price")
            or snapshot.get("price")
            or alpaca_bar.get("price")
            or yahoo_bundle.get("price")
            or 0.0
        )
        previous_close = (
            quote.get("previous_close")
            or snapshot.get("previous_close")
            or yahoo_bundle.get("previous_close")
            or 0.0
        )
        volume = snapshot.get("volume") or alpaca_bar.get("volume") or yahoo_bundle.get("volume") or 0
        if not candles:
            candles = yahoo_bundle.get("candles") or []
        avg_volume = self._average_volume(candles) or snapshot.get("previous_volume") or volume
        change_percent = self._change_percent(price, previous_close)

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "previous_close": round(previous_close, 4),
            "change_percent": round(change_percent, 2),
            "volume": int(volume or 0),
            "avg_volume": int(avg_volume or 0),
            "candles": candles,
            "data_delay": f"{self.data_delay_minutes}-minute delayed",
            "updated_time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def _fetch_finnhub_quote(self, ticker: str) -> Dict[str, float]:
        if not self.finnhub_api_key:
            return {}

        try:
            response = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": ticker, "token": self.finnhub_api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            return {}

        return {
            "price": float(data.get("c") or 0),
            "previous_close": float(data.get("pc") or 0),
        }

    def _fetch_polygon_snapshot(self, ticker: str) -> Dict[str, float]:
        if not self.polygon_api_key:
            return {}

        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        try:
            response = requests.get(url, params={"apiKey": self.polygon_api_key}, timeout=10)
            response.raise_for_status()
            ticker_data = response.json().get("ticker", {})
        except requests.RequestException:
            return {}

        day = ticker_data.get("day", {}) or {}
        previous_day = ticker_data.get("prevDay", {}) or {}
        last_trade = ticker_data.get("lastTrade", {}) or {}

        return {
            "price": float(last_trade.get("p") or day.get("c") or 0),
            "previous_close": float(previous_day.get("c") or 0),
            "volume": float(day.get("v") or 0),
            "previous_volume": float(previous_day.get("v") or 0),
        }

    def _fetch_polygon_daily_candles(self, ticker: str, days: int = 30) -> List[Dict[str, Any]]:
        if not self.polygon_api_key:
            return []

        end_date = datetime.now(UTC).date() - timedelta(days=1)
        start_date = end_date - timedelta(days=days * 2)
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"

        try:
            response = requests.get(
                url,
                params={"adjusted": "true", "sort": "desc", "limit": days, "apiKey": self.polygon_api_key},
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.RequestException:
            return []

    def _fetch_alpaca_latest_bar(self, ticker: str) -> Dict[str, float]:
        if not self.alpaca_api_key or not self.alpaca_secret_key:
            return {}

        url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars/latest"
        headers = {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            bar = response.json().get("bar", {})
        except requests.RequestException:
            return {}

        return {
            "price": float(bar.get("c") or 0),
            "volume": float(bar.get("v") or 0),
        }

    def _average_volume(self, candles: List[Dict[str, Any]]) -> float:
        volumes = [float(candle.get("v") or 0) for candle in candles if candle.get("v")]
        if not volumes:
            return 0.0
        return sum(volumes) / len(volumes)

    @staticmethod
    def _yahoo_index_to_unix_ms(timestamp: Any) -> int:
        """Normalize yfinance timestamps (often tz-naive daily rows) into UTC millis."""

        stamp = pd.Timestamp(timestamp)
        stamp_utc = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        return int(stamp_utc.timestamp() * 1000)

    @staticmethod
    def _sanitize_scalar(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if isinstance(numeric, float) and pd.isna(numeric) else float(numeric)

    @staticmethod
    def _sanitize_volume(value: Any) -> int:
        magnitude = MarketDataAgent._sanitize_scalar(value)
        if magnitude <= 0:
            return 0
        return int(magnitude)

    def _change_percent(self, price: float, previous_close: float) -> float:
        if previous_close <= 0:
            return 0.0
        return ((price - previous_close) / previous_close) * 100

    def filter_bars_regular_session(
        self,
        bars: List[Dict[str, Any]],
        timeframe_minutes: int,
    ) -> List[Dict[str, Any]]:
        """Faqat NY regular sessionda tugaydigan barlar (rejim: FILTER_INTRADAY_REGULAR_SESSION)."""

        if not self.regular_session_filter or not bars:
            return bars
        tf = max(1, int(timeframe_minutes))
        return [bar for bar in bars if bar_end_in_regular_session(int(bar.get("t") or 0), tf)]

    def _purge_intraday_cache(self, now: float) -> None:
        expired = [k for k, (ts, _) in self._intraday_cache.items() if now - ts > self.intraday_cache_ttl]
        for k in expired:
            self._intraday_cache.pop(k, None)

    def _get_with_backoff(self, url: str, *, headers: Dict[str, str] | None = None, params: Dict[str, Any] | None = None) -> requests.Response | None:
        last_exc: Exception | None = None
        for attempt in range(self.http_max_retries):
            try:
                return requests.get(url, headers=headers or {}, params=params or {}, timeout=25)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt + 1 >= self.http_max_retries:
                    break
                sleep_s = min(30.0, self.http_backoff_base * (2**attempt))
                time_module.sleep(sleep_s)
        if last_exc:
            return None
        return None

    def fetch_intraday_bars(
        self,
        ticker: str,
        timeframe_minutes: int = 5,
        lookback_calendar_days: int | None = None,
    ) -> List[Dict[str, Any]]:
        """Grab recent intraday bars (Alpaca, then Polygon, then Yahoo Finance)."""

        minutes = max(1, int(timeframe_minutes))
        cache_key = (ticker.upper(), minutes)
        now = time_module.time()
        self._purge_intraday_cache(now)

        hit = self._intraday_cache.get(cache_key)
        if hit and now - hit[0] <= self.intraday_cache_ttl:
            return self.filter_bars_regular_session(list(hit[1]), minutes)

        bars = self._intraday_fetch_uncached(ticker=ticker, timeframe_minutes=minutes, lookback_calendar_days=lookback_calendar_days)
        filtered = self.filter_bars_regular_session(bars, minutes)
        self._intraday_cache[cache_key] = (now, filtered)
        return filtered

    def _intraday_fetch_uncached(
        self,
        *,
        ticker: str,
        timeframe_minutes: int,
        lookback_calendar_days: int | None,
    ) -> List[Dict[str, Any]]:
        window_days = int(lookback_calendar_days or os.getenv("INTRADAY_LOOKBACK_DAYS", "7"))

        bars = self._intraday_via_alpaca(ticker=ticker, timeframe_minutes=timeframe_minutes, window_days=window_days)
        if bars:
            return bars

        bars = self._intraday_via_polygon(ticker=ticker, timeframe_minutes=timeframe_minutes, window_days=window_days)
        if bars:
            return bars

        return self._intraday_via_yahoo(symbol=ticker, timeframe_minutes=timeframe_minutes, window_days=window_days)

    def _alpaca_timeframe_slug(self, minutes: int) -> str | None:
        timeframe_map = {1: "1Min", 2: "2Min", 3: "3Min", 5: "5Min", 15: "15Min", 30: "30Min", 60: "1Hour"}
        return timeframe_map.get(minutes)

    def _parse_iso8601_timestamp(self, raw_timestamp: str) -> int:
        normalized = raw_timestamp.replace("Z", "+00:00")
        stamp = datetime.fromisoformat(normalized)
        stamp_utc = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
        return int(stamp_utc.timestamp() * 1000)

    def _normalize_alpaca_bar(self, ticker: str, raw_bar: Dict[str, Any]) -> Dict[str, Any]:
        unix_ms = self._parse_iso8601_timestamp(str(raw_bar.get("t", "")))

        return {
            "t": unix_ms,
            "o": float(raw_bar.get("o") or 0),
            "h": float(raw_bar.get("h") or 0),
            "l": float(raw_bar.get("l") or 0),
            "c": float(raw_bar.get("c") or 0),
            "v": float(raw_bar.get("v") or 0),
            "ticker": ticker,
            "source": "alpaca",
        }

    def _normalize_polygon_bar(self, ticker: str, raw_bar: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "t": int(raw_bar.get("t") or 0),
            "o": float(raw_bar.get("o") or 0),
            "h": float(raw_bar.get("h") or 0),
            "l": float(raw_bar.get("l") or 0),
            "c": float(raw_bar.get("c") or 0),
            "v": float(raw_bar.get("v") or 0),
            "ticker": ticker,
            "source": "polygon",
        }

    def _intraday_via_alpaca(self, ticker: str, timeframe_minutes: int, window_days: int) -> List[Dict[str, Any]]:
        timeframe_slug = self._alpaca_timeframe_slug(timeframe_minutes)

        if not self.alpaca_api_key or not self.alpaca_secret_key or not timeframe_slug:
            return []

        end_point = datetime.now(tz=UTC)
        start_point = end_point - timedelta(days=window_days)

        headers = {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }

        params = {
            "timeframe": timeframe_slug,
            "start": start_point.isoformat(),
            "end": end_point.isoformat(),
            "limit": "10000",
            "adjustment": "raw",
            "feed": os.getenv("ALPACA_DATA_FEED", "iex"),
            "sort": "asc",
        }

        url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"

        response = self._get_with_backoff(url, headers=headers, params=params)
        if response is None:
            return []
        try:
            response.raise_for_status()
            raw_bars = response.json().get("bars", []) or []
        except requests.RequestException:
            return []

        return [self._normalize_alpaca_bar(ticker, bar) for bar in raw_bars]

    def _intraday_via_polygon(self, ticker: str, timeframe_minutes: int, window_days: int) -> List[Dict[str, Any]]:
        if not self.polygon_api_key:
            return []

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=max(window_days, 1))

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
            f"{timeframe_minutes}/minute/{start_date}/{end_date}"
        )

        try:
            response = self._get_with_backoff(
                url,
                params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.polygon_api_key},
            )
            if response is None:
                return []
            response.raise_for_status()
            results = response.json().get("results", []) or []
        except requests.RequestException:
            return []

        normalized = [self._normalize_polygon_bar(ticker, bar) for bar in results]

        cutoff = datetime.now(tz=UTC) - timedelta(days=window_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)

        return [bar for bar in normalized if int(bar["t"]) >= cutoff_ms]

    def _fetch_yahoo_daily_bundle(self, symbol: str) -> Dict[str, Any]:
        """Daily history + last prices from Yahoo (yfinance). No API key."""

        if not self.yahoo_finance_enabled:
            return {}

        try:
            import yfinance as yf
        except ImportError:
            return {}

        try:
            stock = yf.Ticker(symbol)
            history = stock.history(period="60d", interval="1d", auto_adjust=True, prepost=False)
        except Exception:
            return {}

        if history is None or history.empty or len(history) < 1:
            return {}

        latest_row = history.iloc[-1]
        price = self._sanitize_scalar(latest_row["Close"])
        volume = self._sanitize_volume(latest_row["Volume"])

        previous_close = (
            self._sanitize_scalar(history.iloc[-2]["Close"]) if len(history) >= 2 else 0.0
        )

        candles: List[Dict[str, Any]] = []
        for row_index, row in history.iterrows():
            unix_ms = self._yahoo_index_to_unix_ms(row_index)

            candles.append(
                {
                    "t": unix_ms,
                    "o": self._sanitize_scalar(row["Open"]),
                    "h": self._sanitize_scalar(row["High"]),
                    "l": self._sanitize_scalar(row["Low"]),
                    "c": self._sanitize_scalar(row["Close"]),
                    "v": self._sanitize_scalar(row["Volume"]),
                }
            )

        candles.sort(key=lambda candle: int(candle["t"]), reverse=True)

        return {
            "price": price,
            "previous_close": previous_close,
            "volume": volume,
            "candles": candles,
        }

    def _yahoo_intraday_interval(self, timeframe_minutes: int) -> str:
        """Map minute bars to yfinance-supported intervals."""

        mapping = {
            1: "1m",
            2: "2m",
            3: "3m",
            5: "5m",
            15: "15m",
            30: "30m",
            60: "60m",
        }
        return mapping.get(timeframe_minutes, "5m")

    def _intraday_via_yahoo(self, symbol: str, timeframe_minutes: int, window_days: int) -> List[Dict[str, Any]]:
        """Minute aggregates from Yahoo; used after Alpaca/Polygon."""

        if not self.yahoo_finance_enabled:
            return []

        try:
            import yfinance as yf
        except ImportError:
            return []

        interval = self._yahoo_intraday_interval(timeframe_minutes)
        # yfinance caps: ~7d for 1m, ~60d for wider minute bars (varies by version).
        if interval == "1m":
            period_days = min(max(window_days, 1), 7)
        else:
            period_days = min(max(window_days, 1), 59)

        try:
            stock = yf.Ticker(symbol)
            history = stock.history(period=f"{period_days}d", interval=interval, auto_adjust=True, prepost=False)
        except Exception:
            return []

        if history is None or history.empty:
            return []

        bars: List[Dict[str, Any]] = []
        for row_index, row in history.iterrows():
            unix_ms = self._yahoo_index_to_unix_ms(row_index)
            bars.append(
                {
                    "t": unix_ms,
                    "o": self._sanitize_scalar(row["Open"]),
                    "h": self._sanitize_scalar(row["High"]),
                    "l": self._sanitize_scalar(row["Low"]),
                    "c": self._sanitize_scalar(row["Close"]),
                    "v": self._sanitize_scalar(row["Volume"]),
                    "ticker": symbol,
                    "source": "yahoo",
                }
            )

        bars.sort(key=lambda bar: int(bar["t"]))

        cutoff = datetime.now(tz=UTC) - timedelta(days=window_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        return [bar for bar in bars if int(bar["t"]) >= cutoff_ms]
