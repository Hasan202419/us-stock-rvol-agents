from __future__ import annotations

import os
from math import floor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import requests

from agents.kill_switch import is_kill_switch_active


class RiskManagerAgent:
    """Hard-coded trade gate that must approve every order."""

    def __init__(self, trades_log_path: str = "logs/trades.csv", repo_root: str | Path | None = None) -> None:
        # $100 default juda qattiq bo'lib, ko'p paper orderlarni bloklaydi; amaliy defaultni yuqoriroq qilamiz.
        self.max_position_size_usd = float(os.getenv("MAX_POSITION_SIZE_USD", "10000"))
        self.max_daily_loss_usd = float(os.getenv("MAX_DAILY_LOSS_USD", "50"))
        self.max_trades_per_day = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
        self.trades_log_path = Path(trades_log_path)
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[1])

        # % of equity allocated to risk amount (MASTER plan: trade_risk = equity * pct/100).
        self.max_risk_pct_of_equity = float(os.getenv("MAX_RISK_PCT_OF_EQUITY", os.getenv("MAX_RISK_PCT", "1.0")))
        self.min_rr_ratio = float(os.getenv("MIN_RISK_REWARD_RATIO", "2.0"))

        api = os.getenv("ALPACA_API_KEY", "").strip()
        sec = os.getenv("ALPACA_SECRET_KEY", "").strip()
        base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        self._alpaca_headers = (
            {
                "APCA-API-KEY-ID": api,
                "APCA-API-SECRET-KEY": sec,
            }
            if api and sec
            else {}
        )
        self.strict_ai_hard = os.getenv("STRICT_AI_HARD_GATES", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._alpaca_account_url = f"{base}/v2/account"

    def approve_order(
        self,
        signal: Dict[str, Any],
        analyst_view: Dict[str, Any],
        order: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Approve only validated paper setups."""
        if is_kill_switch_active():
            return False, "Kill switch is active — no new trades."

        if not analyst_view.get("allow_order", False):
            decision = str(analyst_view.get("decision") or "—").upper()
            analyst_reason = str(analyst_view.get("reason") or "").strip()
            extra = f" decision={decision}." if decision and decision != "—" else ""
            if analyst_reason:
                extra += f" Reason: {analyst_reason}"
            return False, f"AI analyst did not allow this setup for consideration.{extra}".strip()

        if analyst_view.get("decision") not in {"WATCH", "STRONG_WATCH"}:
            return False, "AI analyst decision is not watch-worthy."

        paper_block = analyst_view.get("paper_ready_blocked")
        if paper_block:
            return False, f"PAPER readiness blocked: {paper_block}"

        strict_flags = analyst_view.get("risk_flags_hard") or []
        if (
            self.strict_ai_hard
            and isinstance(strict_flags, list)
            and any(str(f).strip() for f in strict_flags)
        ):
            return False, f"Hard AI risk_flags: {'; '.join(str(f) for f in strict_flags if str(f).strip())}"

        tp = order.get("take_profit") or signal.get("take_profit_suggestion")

        sl_raw = order.get("stop_loss")
        if sl_raw is None:
            sl_raw = signal.get("stop_suggestion")
        if not sl_raw:
            return False, "Stop loss is required."

        price = float(signal.get("price") or 0)
        quantity = int(order.get("quantity") or 0)
        stop_loss = float(sl_raw)

        if price <= 0 or quantity <= 0:
            return False, "Price and quantity must be greater than zero."

        if stop_loss >= price:
            return False, "Stop loss must be below the current price for long orders."

        raw_equity = os.getenv("ACCOUNT_EQUITY_USD") or os.getenv("CAPITAL") or ""
        equity = 0.0
        try:
            if raw_equity.strip():
                equity = float(raw_equity)
        except ValueError:
            equity = 0.0

        live_equity = self._fetch_equity_snapshot()
        if live_equity and live_equity > 0:
            equity = live_equity

        if equity <= 0:
            return False, "Account equity unavailable — set ACCOUNT_EQUITY_USD/CAPITAL in .env or fix Alpaca auth."

        risk_amount = equity * (self.max_risk_pct_of_equity / 100.0)
        risk_per_share = abs(price - stop_loss)

        qty_by_risk = floor(risk_amount / risk_per_share) if risk_per_share > 0 else 0
        qty_allowed = max(0, min(qty_by_risk, floor(equity / price)))

        if qty_allowed <= 0:
            return False, "Risk-based position size resolves to zero (stop too tight vs risk budget)."

        if quantity > qty_allowed:
            return False, (
                f"Quantity {quantity} exceeds risk budget qty {qty_allowed} "
                f"({self.max_risk_pct_of_equity}% of ${equity:,.2f})."
            )

        if tp is not None:
            tp_f = float(tp)
            denom = risk_per_share
            reward = tp_f - price
            rr = reward / denom if denom > 0 else 0.0
            if rr + 1e-9 < self.min_rr_ratio:
                return False, f"Risk:reward too low (~{rr:.2f}); needs ≥ {self.min_rr_ratio}."

        notional = price * quantity
        if notional > self.max_position_size_usd:
            return False, f"Position size ${notional:.2f} exceeds ${self.max_position_size_usd:.2f} limit."

        trades_today = self._trades_today()
        if len(trades_today) >= self.max_trades_per_day:
            return False, "Maximum trades per day reached."

        realized_loss = self._daily_realized_loss(trades_today)
        if realized_loss >= self.max_daily_loss_usd:
            return False, "Maximum daily loss reached."

        return True, "Risk checks passed for paper trading."

    def suggest_quantity(self, signal: Dict[str, Any]) -> Tuple[int, str]:
        """1% equity risk model (buy-only), stop from signal/order context."""
        price = float(signal.get("price") or 0)
        stop = signal.get("stop_suggestion") or signal.get("stop_loss_ref")
        if price <= 0 or not stop:
            return 0, "Need price + stop suggestion for sizing."

        equity = 0.0
        env_eq = os.getenv("ACCOUNT_EQUITY_USD") or os.getenv("CAPITAL")
        if env_eq:
            try:
                equity = float(env_eq)
            except ValueError:
                equity = 0.0

        live_equity = self._fetch_equity_snapshot()
        if live_equity and live_equity > 0:
            equity = live_equity

        if equity <= 0:
            return 0, "Equity unavailable for sizing."

        risk_amount = equity * (self.max_risk_pct_of_equity / 100.0)
        risk_per_share = abs(price - float(stop))
        if risk_per_share <= 0:
            return 0, "Invalid stop distance."
        qty = max(0, min(int(floor(risk_amount / risk_per_share)), int(floor(equity / price))))
        return qty, f"Sized vs equity ${equity:,.2f} @ {self.max_risk_pct_of_equity}% risk."

    def _fetch_equity_snapshot(self) -> float | None:
        if not self._alpaca_headers:
            return None
        try:
            response = requests.get(self._alpaca_account_url, headers=self._alpaca_headers, timeout=12)
            response.raise_for_status()
            equity = float(response.json().get("equity", 0))
            return equity if equity > 0 else None
        except requests.RequestException:
            return None

    def _trades_today(self) -> pd.DataFrame:
        if not self.trades_log_path.exists():
            return pd.DataFrame()

        try:
            trades = pd.read_csv(self.trades_log_path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

        if "submitted_at" not in trades.columns:
            return pd.DataFrame()

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return trades[trades["submitted_at"].astype(str).str.startswith(today)]

    def _daily_realized_loss(self, trades_today: pd.DataFrame) -> float:
        if trades_today.empty or "realized_pnl" not in trades_today.columns:
            return 0.0

        pnl = pd.to_numeric(trades_today["realized_pnl"], errors="coerce").fillna(0)
        return abs(float(pnl[pnl < 0].sum()))
