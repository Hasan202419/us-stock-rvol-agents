"""Skan xabarlari uchun SMTP email — Telegram bilan analog; maxfiy qiymatlarni matnga kiritmaydi."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, List


class EmailAlertsAgent:
    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "").strip()
        port_raw = os.getenv("SMTP_PORT", "587").strip()
        try:
            self.smtp_port = int(port_raw) if port_raw else 587
        except ValueError:
            self.smtp_port = 587

        self.smtp_user = os.getenv("SMTP_USER", "").strip() or os.getenv("SMTP_USERNAME", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "").strip()

        self.mail_from = os.getenv("EMAIL_FROM", "").strip() or self.smtp_user
        raw_to = os.getenv("EMAIL_TO", "").strip()
        self.mail_to_list = [a.strip() for a in raw_to.replace(";", ",").split(",") if a.strip()]

        self.use_ssl = os.getenv("SMTP_USE_SSL", "").strip().lower() in {"1", "true", "yes", "on"}
        self.disabled_tls_verify = (
            os.getenv("SMTP_TLS_VERIFY", "true").strip().lower()
            not in {"1", "true", "yes", "on"}
        )

    def _smtp_config_ok(self) -> bool:
        return bool(self.smtp_host and self.mail_from and self.mail_to_list)

    @staticmethod
    def _alert_flag(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def _alerts_requested(self) -> bool:
        return self._alert_flag("EMAIL_ALERTS_ENABLED") or self._alert_flag("EMAIL_ALERT_ON_SCAN")

    def notify_scan_summary(self, summary: Dict[str, Any]) -> None:
        if not self._alerts_requested() or not self._smtp_config_ok():
            return

        text = (
            "Skan yakunlandi\n"
            f"- Tickers: {summary.get('tickers_scanned')}\n"
            f"- Eligible: {summary.get('eligible_signals')}\n"
            f"- Strategiya: {summary.get('strategy_mode', '-')}\n"
        )
        self._send("[RVOL] Skan yakunlandi", text)

    def notify_signals(self, signals: List[Dict[str, Any]], max_items: int = 3) -> None:
        if not signals or not self._alerts_requested() or not self._smtp_config_ok():
            return

        lines = ["Top signallar:", ""]
        for row in signals[:max_items]:
            lines.append(f"- {row.get('ticker')} | score={row.get('score')} | {row.get('strategy_name')}")
        self._send("[RVOL] Top signallar", "\n".join(lines))

    def _send(self, subject: str, body: str) -> None:
        if not self.smtp_host or not self.mail_from or not self.mail_to_list:
            return

        ctx = ssl.create_default_context()
        if self.disabled_tls_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        msg = EmailMessage()
        msg["Subject"] = subject[:800]
        msg["From"] = self.mail_from
        msg["To"] = ", ".join(self.mail_to_list)
        msg.set_content(body[:490_000])

        try:
            if self.use_ssl and self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=25, context=ctx) as smtp:
                    if self.smtp_user and self.smtp_password:
                        smtp.login(self.smtp_user, self.smtp_password)
                    smtp.send_message(msg)
                return

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=25) as smtp:
                try:
                    smtp.starttls(context=ctx)
                except smtplib.SMTPException:
                    pass
                if self.smtp_user and self.smtp_password:
                    smtp.login(self.smtp_user, self.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException):
            pass
