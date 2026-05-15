"""Telegram: AMT Scalping & Volume Profile BUY — alohida xabar formatlari."""

from __future__ import annotations

import html
import os
from typing import Any, Dict, List, Mapping


def _truthy(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def amt_buy_alert_enabled() -> bool:
    return _truthy("TELEGRAM_AMT_BUY_ALERT_SEPARATE", default=True)


def collect_amt_buy_signals(results: Mapping[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Barcha skanlangan tickerlardan `amt_buy_signal=True` bo‘lganlar."""

    rows = [dict(sig) for sig in results.values() if bool(sig.get("amt_buy_signal"))]
    rows.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            str(item.get("ticker") or ""),
        )
    )
    try:
        cap = int(os.getenv("TELEGRAM_AMT_BUY_TOP_N", "12"))
    except ValueError:
        cap = 12
    cap = max(1, min(50, cap))
    return rows[:cap]


def escape_html(text: Any) -> str:
    return html.escape(str(text), quote=False)


def format_amt_buy_line(row: Dict[str, Any], *, chart_url: str = "") -> str:
    """Bitta ticker uchun AMT BUY kartochkasi (HTML)."""

    t = escape_html(row.get("ticker", "?"))
    parts: list[str] = []
    if bool(row.get("amt_buy_from_val")):
        parts.append("VAL↑")
    if bool(row.get("amt_buy_ema_reclaim")):
        parts.append("EMA9 qayta")
    trigger = ", ".join(parts) if parts else "BUY"

    val = row.get("amt_val")
    poc = row.get("amt_poc_proxy")
    vah = row.get("amt_vah")
    zone_bits: list[str] = []
    for label, val_raw in (("VAL", val), ("POC", poc), ("VAH", vah)):
        if val_raw is not None:
            try:
                zone_bits.append(f"{label} {escape_html(round(float(val_raw), 2))}")
            except (TypeError, ValueError):
                pass
    zone_txt = " · ".join(zone_bits) if zone_bits else ""

    lines = [f"<b>{t}</b> · 🟢 <b>AMT BUY</b> · <i>{escape_html(trigger)}</i>"]
    if zone_txt:
        lines.append(f"   {zone_txt}")
    levels = str(row.get("trade_levels_line") or "").strip()
    if levels:
        lines.append(f"   ⚡ <code>{escape_html(levels)}</code>")
    elif row.get("price") is not None:
        try:
            lines.append(f"   narx {escape_html(round(float(row['price']), 2))}")
        except (TypeError, ValueError):
            pass
    if bool(row.get("amt_tp_zone")):
        lines.append("   📈 TP zona (POC+)")
    if bool(row.get("amt_strong_tp_zone")):
        lines.append("   🎯 Kuchli TP (VAH+)")

    if chart_url:
        lines.append(f'   <a href="{chart_url}">TradingView</a>')
    return "\n".join(lines)


def build_amt_buy_alert_html(
    amt_rows: List[Dict[str, Any]],
    *,
    summary: Dict[str, Any] | None = None,
    chart_url_builder: Any = None,
) -> str:
    """Alohida Telegram xabari: faqat AMT Volume Profile BUY."""

    total = int((summary or {}).get("amt_buy_count") or len(amt_rows))
    scanned = (summary or {}).get("tickers_scanned", "—")
    lines = [
        "<b>🟢 AMT Scalping &amp; Volume Profile BUY</b>\n",
        "<i>TradingView Pine mantig‘i · VAL/POC/VAH + EMA9</i>\n",
        f"Skan: {escape_html(scanned)} ticker · AMT BUY: <b>{total}</b>\n\n",
    ]
    if not amt_rows:
        lines.append("— Hozircha AMT BUY sharti bajarilgan ticker yo‘q.\n")
        return "".join(lines)

    for row in amt_rows:
        url = ""
        if chart_url_builder:
            try:
                url = str(chart_url_builder(str(row.get("ticker", ""))))
            except Exception:
                url = ""
        lines.append(format_amt_buy_line(row, chart_url=url) + "\n\n")
    return "".join(lines)
