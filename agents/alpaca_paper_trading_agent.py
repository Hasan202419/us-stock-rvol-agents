import os
from datetime import UTC, datetime
from typing import Any, Dict

import requests


class AlpacaPaperTradingAgent:
    """Submit orders to Alpaca paper trading only after RiskManager approval."""

    def __init__(self) -> None:
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        self.trading_mode = os.getenv("TRADING_MODE", "paper").lower()
        self.order_style = os.getenv("ALPACA_ORDER_STYLE", "bracket").strip().lower()

    def headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    def fetch_order(self, order_id: str) -> Dict[str, Any] | None:
        """HTTP GET /v2/orders/{id} — polling uchun."""
        if not self.api_key or not self.secret_key or not order_id:
            return None
        try:
            response = requests.get(f"{self.base_url}/v2/orders/{order_id}", headers=self.headers(), timeout=15)
            response.raise_for_status()
            return dict(response.json())
        except requests.RequestException:
            return None

    def submit_order(
        self,
        ticker: str,
        quantity: int,
        stop_loss: float,
        risk_approved: bool,
        take_profit: float | None = None,
    ) -> Dict[str, Any]:
        if not risk_approved:
            return self._blocked("RiskManager did not approve the order.")

        if self.trading_mode != "paper" or "paper-api.alpaca.markets" not in self.base_url:
            return self._blocked("Only Alpaca paper trading mode is allowed.")

        if not self.api_key or not self.secret_key:
            return self._blocked("Alpaca API keys are missing.")

        if self.order_style == "bracket" and take_profit is not None and take_profit > 0:
            payload: Dict[str, Any] = {
                "symbol": ticker,
                "qty": str(quantity),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "take_profit": {"limit_price": str(round(float(take_profit), 4))},
                "stop_loss": {"stop_price": str(round(float(stop_loss), 4))},
            }
        else:
            payload = {
                "symbol": ticker,
                "qty": str(quantity),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "order_class": "oto",
                "stop_loss": {"stop_price": round(float(stop_loss), 2)},
            }

        cid = (
            os.getenv("ALPACA_ORDER_ID_PREFIX", "hasan")
            + "_"
            + ticker
            + "_"
            + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        )
        payload["client_order_id"] = cid[:48]

        try:
            response = requests.post(f"{self.base_url}/v2/orders", json=payload, headers=self.headers(), timeout=25)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            return {
                "submitted": False,
                "status": "ERROR",
                "message": f"Alpaca paper order failed: {exc}",
                "submitted_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

        return {
            "submitted": True,
            "status": data.get("status", "submitted"),
            "order_id": data.get("id", ""),
            "message": "Paper order submitted to Alpaca.",
            "submitted_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def _blocked(self, message: str) -> Dict[str, Any]:
        return {
            "submitted": False,
            "status": "BLOCKED",
            "message": message,
            "submitted_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
