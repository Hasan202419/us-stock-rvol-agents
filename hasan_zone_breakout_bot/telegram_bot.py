"""telegram_bot.py — Telegram alert (REAL yuborish) + dedup + aniq format.

XAVFSIZLIK: bu fayl FAQAT xabar yuboradi (sendMessage). Hech qanday order/trade yo'q.
Faqat PAPER_READY / HIGH_QUALITY_PAPER_READY qarorlari yuboriladi. 10 daqiqa dedup.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

import requests

from . import config
from .halal_filter import halal_warning

# Dedup xotirasi: {ticker: (last_unix_ts, last_score, last_zone_status)}
_LAST_SENT: Dict[str, Tuple[float, int, str]] = {}


def should_send(signal: Dict[str, Any]) -> bool:
    """Telegramga yuborish kerakmi? Faqat PAPER_READY+ va dedup qoidasiga mos."""
    decision = str(signal.get("decision", ""))
    if decision not in config.TELEGRAM_ALERT_DECISIONS:
        return False

    ticker = str(signal.get("ticker", "?")).upper()
    score = int(signal.get("score", 0))
    zone_status = str(signal.get("zone_status", ""))
    now = time.time()

    prev = _LAST_SENT.get(ticker)
    if prev is None:
        return True
    last_ts, last_score, last_zone = prev
    if (now - last_ts) >= config.DEDUP_MINUTES * 60:
        return True
    # 10 daqiqa ichida: faqat score oshsa yoki yangi breakout/reclaim bo'lsa
    if score > last_score:
        return True
    if zone_status == "Breakout" and last_zone != "Breakout":
        return True
    return False


def _mark_sent(signal: Dict[str, Any]) -> None:
    ticker = str(signal.get("ticker", "?")).upper()
    _LAST_SENT[ticker] = (time.time(), int(signal.get("score", 0)), str(signal.get("zone_status", "")))


def build_alert_text(signal: Dict[str, Any], regime: Dict[str, Any]) -> str:
    """Foydalanuvchi bergan aniq alert formati."""
    halal = str(signal.get("halal_status", "UNKNOWN"))
    warn = halal_warning(halal)
    spread = signal.get("spread_pct")
    spread_txt = f"{spread}%" if spread is not None else "UNKNOWN"
    spy = regime.get("SPY", {})
    qqq = regime.get("QQQ", {})

    def _yn(info: Dict[str, Any]) -> str:
        if not info.get("ok"):
            return "—"
        return "bullish" if info.get("bullish") else ("VWAP↑" if info.get("above_vwap") else "VWAP↓")

    base_warn = ("No stop-loss = no trade. If price closes back inside the zone or loses VWAP, "
                 "cancel setup.")
    if warn:
        base_warn = warn + " " + base_warn

    return (
        "🚨 HASAN SCALPING SIGNAL\n\n"
        f"Ticker: {signal.get('ticker')}\n"
        f"Mode: {signal.get('mode')}\n"
        f"Decision: {signal.get('decision')}\n"
        f"Score: {signal.get('score')}\n"
        f"Halal status: {halal}\n\n"
        "Setup:\n"
        "Zone Consolidation + Zone Breakout + VWAP Reclaim\n\n"
        "Market Regime:\n"
        f"SPY: {_yn(spy)}\n"
        f"QQQ: {_yn(qqq)}\n\n"
        "Timeframes:\n"
        f"1H Context: {signal.get('zone_status')}\n"
        f"5M Setup: {signal.get('vwap_status')}\n"
        f"3M Confirmation: {'OK' if signal.get('_flags', {}).get('confirm_3m') else '—'}\n"
        "1M Entry Timing: pullback/retest\n\n"
        f"Price: {signal.get('price')}\n"
        f"VWAP: {signal.get('vwap')}\n"
        f"EMA9: {signal.get('ema9')}\n"
        f"EMA20: {signal.get('ema20')}\n"
        f"RVOL: {signal.get('rvol')}\n"
        f"Dollar Volume: {signal.get('dollar_volume')}\n"
        f"Spread: {spread_txt}\n"
        f"Volume Spike Ratio: {signal.get('volume_spike')}\n\n"
        "Zone:\n"
        f"Zone Low: {signal.get('zone_low')}\n"
        f"Zone High: {signal.get('zone_high')}\n"
        f"Consolidation: {signal.get('consolidation')}\n"
        f"Breakout: {signal.get('breakout')}\n\n"
        f"Entry Idea: {signal.get('entry')}\n"
        f"Stop-loss: {signal.get('stop_loss')}\n"
        f"Target 1: {signal.get('target1')}\n"
        f"Target 2: {signal.get('target2')}\n"
        f"Risk/Reward: {signal.get('risk_reward')}\n\n"
        f"Reason: {signal.get('reason')}\n\n"
        "Warning:\n"
        f"{base_warn}\n"
        "(Signal-only bot — no auto trade, no real orders.)"
    )


def send_telegram(text: str) -> bool:
    """Telegramga xabar yuboradi. Token/chat_id yo'q bo'lsa False (jim)."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        return bool(r.ok and (r.json() or {}).get("ok"))
    except (requests.RequestException, ValueError):
        return False


def maybe_alert(signal: Dict[str, Any], regime: Dict[str, Any], *, dry: bool = False) -> bool:
    """Agar dedup/qaror ruxsat bersa alert yuboradi. dry=True -> konsolga chiqaradi."""
    if not should_send(signal):
        return False
    text = build_alert_text(signal, regime)
    if dry:
        print("\n--- DRY TELEGRAM ALERT ---")
        print(text)
        _mark_sent(signal)
        return True
    ok = send_telegram(text)
    if ok:
        _mark_sent(signal)
    return ok
