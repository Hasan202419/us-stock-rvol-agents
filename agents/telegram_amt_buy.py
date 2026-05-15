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
        cap = int(os.getenv("TELEGRAM_AMT_BUY_TOP_N", "20"))
    except ValueError:
        cap = 20
    cap = max(1, min(50, cap))
    return rows[:cap]


def collect_amt_near_val_watch(
    results: Mapping[str, Dict[str, Any]],
    *,
    max_dist_pct: float = 2.5,
) -> List[Dict[str, Any]]:
    """AMT zona bor, lekin hali BUY emas — VAL ga yaqin tickerlar (kuzatuv)."""

    scored: list[tuple[float, Dict[str, Any]]] = []
    for sig in results.values():
        if not bool(sig.get("amt_ok")) or bool(sig.get("amt_buy_signal")):
            continue
        val = sig.get("amt_val")
        price = sig.get("price")
        if val is None or price is None:
            continue
        try:
            val_f = float(val)
            px = float(price)
            if val_f <= 0:
                continue
            dist_pct = abs(px - val_f) / val_f * 100.0
            if dist_pct <= max_dist_pct:
                scored.append((dist_pct, dict(sig)))
        except (TypeError, ValueError):
            continue
    scored.sort(key=lambda item: (item[0], -float(item[1].get("score") or 0)))
    try:
        cap = int(os.getenv("TELEGRAM_AMT_NEAR_VAL_TOP_N", "15"))
    except ValueError:
        cap = 15
    cap = max(0, min(30, cap))
    return [row for _, row in scored[:cap]]


def format_amt_near_line(row: Dict[str, Any], *, chart_url: str = "") -> str:
    t = escape_html(row.get("ticker", "?"))
    val = row.get("amt_val")
    poc = row.get("amt_poc_proxy")
    bits: list[str] = []
    if val is not None:
        try:
            bits.append(f"VAL {escape_html(round(float(val), 2))}")
        except (TypeError, ValueError):
            pass
    if poc is not None:
        try:
            bits.append(f"POC {escape_html(round(float(poc), 2))}")
        except (TypeError, ValueError):
            pass
    if row.get("price") is not None:
        try:
            bits.append(f"narx {escape_html(round(float(row['price']), 2))}")
        except (TypeError, ValueError):
            pass
    line = f"<b>{t}</b> · 🟡 AMT kuzatuv · {' · '.join(bits)}"
    if chart_url:
        line += f' · <a href="{chart_url}">Chart</a>'
    amt_s = str(row.get("amt_summary_line") or "").strip()
    if amt_s:
        if len(amt_s) > 100:
            amt_s = amt_s[:97] + "…"
        line += f"\n   <i>{escape_html(amt_s)}</i>"
    return line


def escape_html(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _amt_zone_bits(row: Dict[str, Any]) -> list[str]:
    bits: list[str] = []
    for label, key in (("VAL", "amt_val"), ("POC", "amt_poc_proxy"), ("VAH", "amt_vah")):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            bits.append(f"{label} {round(float(raw), 2)}")
        except (TypeError, ValueError):
            pass
    return bits


def format_amt_zone_inline(row: Dict[str, Any]) -> str:
    """Babir skan qatorida qisqa AMT zona (oddiy matn, HTML emas)."""

    if not bool(row.get("amt_ok")):
        return ""
    zone = " · ".join(_amt_zone_bits(row))
    if bool(row.get("amt_buy_signal")):
        triggers: list[str] = []
        if bool(row.get("amt_buy_from_val")):
            triggers.append("VAL↑")
        if bool(row.get("amt_buy_ema_reclaim")):
            triggers.append("EMA9")
        trig = ", ".join(triggers) if triggers else "BUY"
        head = f"AMT BUY · {trig}"
        return f"{head} · {zone}" if zone else head
    if zone:
        return f"AMT kuzatuv · {zone}"
    return ""


def enrich_ranked_for_babir(
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any] | None,
    *,
    max_amt_buy: int | None = None,
    max_near_val: int | None = None,
) -> List[Dict[str, Any]]:
    """Pass/watchlist ga kirmagan AMT BUY va VAL yaqin tickerlarni Babir ro‘yxatiga qo‘shadi."""

    if not summary:
        return ranked

    try:
        cap_buy = int(os.getenv("TELEGRAM_AMT_BUY_TOP_N", "20"))
    except ValueError:
        cap_buy = 20
    cap_buy = max(1, min(50, cap_buy))
    if max_amt_buy is not None:
        cap_buy = max(0, min(50, int(max_amt_buy)))

    try:
        cap_near = int(os.getenv("TELEGRAM_AMT_NEAR_VAL_TOP_N", "15"))
    except ValueError:
        cap_near = 15
    cap_near = max(0, min(30, cap_near))
    if max_near_val is not None:
        cap_near = max(0, min(30, int(max_near_val)))

    seen = {str(r.get("ticker") or "").upper() for r in ranked if r.get("ticker")}
    out: list[Dict[str, Any]] = []

    amt_rows = summary.get("amt_buy_signals") or []
    if isinstance(amt_rows, list):
        for row in amt_rows[:cap_buy]:
            if not isinstance(row, dict) or not bool(row.get("amt_buy_signal")):
                continue
            t = str(row.get("ticker") or "").upper()
            if not t or t in seen:
                continue
            cloned = dict(row)
            cloned["babir_amt_card"] = True
            if not bool(cloned.get("strategy_pass")):
                cloned["watchlist_only"] = True
                cloned.setdefault("chatgpt_decision", "AMT_BUY")
            out.append(cloned)
            seen.add(t)

    near_rows = summary.get("amt_near_val_signals") or []
    if isinstance(near_rows, list):
        for row in near_rows[:cap_near]:
            if not isinstance(row, dict):
                continue
            t = str(row.get("ticker") or "").upper()
            if not t or t in seen:
                continue
            cloned = dict(row)
            cloned["babir_amt_near"] = True
            cloned["watchlist_only"] = True
            cloned.setdefault("chatgpt_decision", "AMT_WATCH")
            out.append(cloned)
            seen.add(t)

    out.extend(ranked)
    return out


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
    near_rows: List[Dict[str, Any]] | None = None,
) -> str:
    """Alohida Telegram xabari #2: AMT Volume Profile BUY (+ ixtiyoriy VAL yaqin kuzatuv)."""

    total = int((summary or {}).get("amt_buy_count") or len(amt_rows))
    scanned = (summary or {}).get("tickers_scanned", "—")
    lines = [
        "<b>🟢 AMT Scalping &amp; Volume Profile BUY</b>\n",
        "<i>TradingView Pine · VAL/POC/VAH + EMA9</i>\n",
        f"Skanlangan: <b>{escape_html(scanned)}</b> ticker · AMT BUY: <b>{total}</b>\n\n",
    ]
    if amt_rows:
        lines.append(f"<b>AMT BUY signallar ({len(amt_rows)})</b>\n")
        for row in amt_rows:
            url = ""
            if chart_url_builder:
                try:
                    url = str(chart_url_builder(str(row.get("ticker", ""))))
                except Exception:
                    url = ""
            lines.append(format_amt_buy_line(row, chart_url=url) + "\n\n")
    else:
        lines.append("— Hozircha to‘liq AMT BUY yo‘q (bozor yopiq yoki VAL↑ sharti bajarilmagan).\n\n")

    near = near_rows or []
    if near:
        lines.append(f"<b>VAL yaqin kuzatuv</b> <i>(hali BUY emas)</i>\n")
        for row in near:
            url = ""
            if chart_url_builder:
                try:
                    url = str(chart_url_builder(str(row.get("ticker", ""))))
                except Exception:
                    url = ""
            lines.append(format_amt_near_line(row, chart_url=url) + "\n")
    return "".join(lines)
