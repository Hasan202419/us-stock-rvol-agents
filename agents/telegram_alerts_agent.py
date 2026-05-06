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
            f"• Eligible: {summary.get('eligible_signals')}"
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

    def _send(self, text: str) -> None:
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text[:3900]},
                timeout=12,
            )
        except requests.RequestException:
            pass
