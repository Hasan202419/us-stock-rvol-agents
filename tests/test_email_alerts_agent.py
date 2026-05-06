from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from agents.email_alerts_agent import EmailAlertsAgent


@patch("agents.email_alerts_agent.smtplib.SMTP_SSL")
@patch("agents.email_alerts_agent.smtplib.SMTP")
def test_email_skips_when_not_requested(mock_smtp: MagicMock, mock_ssl: MagicMock) -> None:
    with patch.dict(
        os.environ,
        {
            "EMAIL_ALERTS_ENABLED": "false",
            "EMAIL_ALERT_ON_SCAN": "false",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "u",
            "SMTP_PASSWORD": "p",
            "EMAIL_FROM": "a@example.com",
            "EMAIL_TO": "b@example.com",
        },
        clear=False,
    ):
        em = EmailAlertsAgent()
        em.notify_scan_summary({"tickers_scanned": 1, "eligible_signals": 0, "strategy_mode": "rvol"})
        em.notify_signals([{"ticker": "X", "score": 1, "strategy_name": "t"}])

    mock_smtp.assert_not_called()
    mock_ssl.assert_not_called()


@patch("agents.email_alerts_agent.smtplib.SMTP_SSL")
@patch("agents.email_alerts_agent.smtplib.SMTP")
def test_email_sends_summary_when_on_scan(mock_smtp: MagicMock, mock_ssl: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance

    with patch.dict(
        os.environ,
        {
            "EMAIL_ALERT_ON_SCAN": "true",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pw",
            "EMAIL_FROM": "from@test.com",
            "EMAIL_TO": "to@test.com",
        },
        clear=False,
    ):
        em = EmailAlertsAgent()
        em.notify_scan_summary({"tickers_scanned": 5, "eligible_signals": 2, "strategy_mode": "rvol"})
        mock_smtp.assert_called_once()
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user", "pw")
        mock_instance.send_message.assert_called_once()
        mock_ssl.assert_not_called()
