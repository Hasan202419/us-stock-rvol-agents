"""Minimal Telegram signallari — alerting only, tasdiqlashdan keyingi fazada."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests


class TelegramAlertsAgent:
    """Xavfsiz: faqat yozma xabarlar, maxfiy kodlarni yozmaydi."""

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("TELEGRAM_ALERTS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

    def notify_scan_summary(self, summary: Dict[str, Any]) -> None:
        forced = os.getenv("TELEGRAM_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
        if not self.token or not self.chat_id or (not self.enabled and not forced):
            return
        text = (
            f"📡 Skan yakunlandi\n"
            f"• Tickers: {summary.get('tickers_scanned')}\n"
            f"• Eligible: {summary.get('eligible_signals')}\n"
            f"• Paper ready: {summary.get('paper_ready_signals', '—')}"
        )
        self._send(text)

    def notify_signals(self, signals: List[Dict[str, Any]], max_items: int = 3) -> None:
        forced = os.getenv("TELEGRAM_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
        if not signals or not self.token or not self.chat_id or (not self.enabled and not forced):
            return

        lines = ["📈 Top signallar:"]
        for row in signals[:max_items]:
            lines.append(f"• `{row.get('ticker')}` · score={row.get('score')} · {row.get('strategy_name')}")
        self._send("\n".join(lines))

    def notify_amt_buy_signals(
        self,
        amt_rows: List[Dict[str, Any]],
        *,
        summary: Dict[str, Any] | None = None,
    ) -> None:
        """AMT Scalping & Volume Profile BUY — alohida xabar."""

        from agents.telegram_amt_buy import build_amt_buy_alert_html

        forced = os.getenv("TELEGRAM_ALERT_ON_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
        if not amt_rows or not self.token or not self.chat_id or (not self.enabled and not forced):
            return
        text = build_amt_buy_alert_html(amt_rows, summary=summary)
        self._send_html(text)

    def _send_html(self, text: str) -> None:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text[:3900],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=12,
            )
            if not response.ok:
                print(
                    f"TelegramAlertsAgent sendMessage(HTML) error: {response.status_code} {response.text[:300]}",
                    flush=True,
                )
        except requests.RequestException:
            print("TelegramAlertsAgent sendMessage(HTML) request failed.", flush=True)

    def _send(self, text: str) -> None:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text[:3900]},
                timeout=12,
            )
            if not response.ok:
                print(
                    f"TelegramAlertsAgent sendMessage error: {response.status_code} {response.text[:300]}",
                    flush=True,
                )
        except requests.RequestException:
            print("TelegramAlertsAgent sendMessage request failed.", flush=True)
