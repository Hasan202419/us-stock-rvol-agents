"""Long-poll Telegram bot: /scan uses agents.scan_pipeline (same path as dashboard)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import UTC, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

# Repo root: …/us-stock-rvol-agents/
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("PROJECT_ROOT", str(PROJECT_DIR))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402
from agents.scan_pipeline import (  # noqa: E402
    SidebarControls,
    _env_int_bounded,
    fetch_universe_for_scan,
    run_scan_market,
    telegram_default_controls,
)
from agents.scan_presets import SCAN_PRESETS  # noqa: E402
from agents.session_calendar import NY_TZ, is_weekday_et, ny_session_bounds_for_date  # noqa: E402
from agents.telegram_framework_html import build_telegram_framework_appendices_html  # noqa: E402
from agents.trade_plan_format import deterministic_trade_plan_from_signal  # noqa: E402
from agents.telegram_amt_buy import (  # noqa: E402
    amt_buy_alert_enabled,
    build_amt_buy_alert_html,
    enrich_ranked_for_babir,
    format_amt_buy_line,
    format_amt_zone_inline,
)
from agents.simple_backtest_mvp import (  # noqa: E402
    daily_closes_yfinance,
    sma_crossover_long_only_backtest,
)

TG_API = "https://api.telegram.org"
MAX_MESSAGE_LEN = 3800

# Pastki menyu tugmalari (ReplyKeyboardMarkup)
BTN_SCAN = "📊 Skan"
BTN_SIGNALS = "📋 Signallar"
BTN_PLAN = "📝 Plan"
BTN_STATUS = "⚙️ Holat"
BTN_HELP = "❓ Yordam"
BTN_RISK = "🛡 Risk"

_TEXT_BUTTON_TO_CMD: Dict[str, tuple[str, str]] = {
    BTN_SCAN: ("scan", ""),
    BTN_SIGNALS: ("signals", ""),
    BTN_PLAN: ("plan", ""),
    BTN_STATUS: ("status", ""),
    BTN_HELP: ("help", ""),
    BTN_RISK: ("risk", ""),
}


def _parse_allowed_chat_ids() -> Optional[set[str]]:
    """Guruh/supergroup `chat.id` lar manfiy (-100…) bo‘lishi mumkin — faqat `.isdigit()` yetarli emas."""

    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return None
    out: set[str] = set()
    for chunk in raw.split(","):
        part = chunk.strip().replace(" ", "")
        if not part:
            continue
        try:
            out.add(str(int(part, 10)))
        except ValueError:
            continue
    return out or None


def _effective_allowed_chat_ids(token: str) -> Optional[set[str]]:
    """TELEGRAM_ALLOWED_CHAT_IDS + TELEGRAM_CHAT_ID; umumiy xato: ikkalasi ham TOKEN dagi bot-id."""

    base = _parse_allowed_chat_ids()
    if base is None:
        return None

    merged: set[str] = set(base)
    raw_primary = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if raw_primary:
        try:
            merged.add(str(int(raw_primary.replace(" ", ""), 10)))
        except ValueError:
            pass

    pref = token.split(":", 1)[0].strip()
    if pref.isdigit() and merged and merged.issubset({pref}):
        print(
            "telegram_command_bot: XATO taxminiy `.env`: TELEGRAM_ALLOWED_CHAT_IDS va/yoki TELEGRAM_CHAT_ID "
            "`TELEGRAM_BOT_TOKEN` dagi bot IDs i bilan bir xil (masalan TOKEN=123:AA… → 123). "
            "DM da `chat.id` odatda boshqa raqam — @userinfobot dan o‘zingiznikini oling. "
            "Hozir chat filtri o‘chirildi (hammaga javob).",
            flush=True,
        )
        return None

    return merged


def _delete_webhook_for_long_poll(token: str) -> None:
    """Webhook + long-poll bir vaqtda emas — 409 Conflict oldini kamaytirish."""

    try:
        r = requests.post(
            f"{TG_API}/bot{token}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=30,
        )
        if r.ok:
            data = r.json()
            if data.get("ok"):
                print("telegram_command_bot: deleteWebhook OK (polling rejimi)", flush=True)
                return
        print(f"telegram_command_bot: deleteWebhook javob: {r.status_code} {r.text[:200]}", flush=True)
    except requests.RequestException as exc:
        print(f"telegram_command_bot: deleteWebhook xato: {exc}", flush=True)


def _register_bot_menu_commands(token: str) -> None:
    """Telegram `/` menyusidagi buyruqlar ro‘yxati (setMyCommands)."""

    if _truthy_env("TELEGRAM_SKIP_SET_MY_COMMANDS", default=False):
        print("telegram_command_bot: setMyCommands o‘tkazib yuborildi (TELEGRAM_SKIP_SET_MY_COMMANDS).", flush=True)
        return
    # Telegram: command 3–32, a-z 0-9 _ ; description ≤256
    commands: List[Dict[str, str]] = [
        {"command": "start", "description": "Yordam va bot haqida"},
        {"command": "help", "description": "Barcha buyruqlar (HTML yordam)"},
        {"command": "scan", "description": "US skan (dashboard bilan bir xil)"},
        {"command": "scanall", "description": "Keng qamrovli skan (/scanall)"},
        {"command": "signals", "description": "Oxirgi /scan qisqa natijasi"},
        {"command": "plan", "description": "Trade plan: /plan yoki /plan AAPL"},
        {"command": "tv", "description": "TradingView: /tv AAPL"},
        {"command": "chart", "description": "TradingView (tv bilan bir xil)"},
        {"command": "status", "description": "Bot, Alpaca, avto-push holati"},
        {"command": "risk", "description": "Paper risk limitlari"},
        {"command": "paper", "description": "Alpaca paper (keyingi fazada)"},
        {"command": "backtest", "description": "Kunlik SMA backtest: /backtest TSLA"},
    ]
    try:
        r = requests.post(
            f"{TG_API}/bot{token}/setMyCommands",
            json={"commands": commands},
            timeout=30,
        )
        if r.ok and (r.json() or {}).get("ok"):
            print("telegram_command_bot: setMyCommands OK (Telegram / menyusi yangilandi)", flush=True)
            return
        print(f"telegram_command_bot: setMyCommands xato: {r.status_code} {r.text[:400]}", flush=True)
    except requests.RequestException as exc:
        print(f"telegram_command_bot: setMyCommands so‘rov xatosi: {exc}", flush=True)


def _command_from_text(text: str) -> tuple[str, str]:
    """Return (cmd_lower, remainder). Supports /scan@BotName."""

    if not text or not text.startswith("/"):
        return "", ""
    head, _, tail = text.partition(" ")
    first = head.strip().lower()
    remainder = tail.strip()
    cmd_part = first.split("@", maxsplit=1)[0] if first else ""
    if not cmd_part.startswith("/"):
        return "", remainder
    return cmd_part[1:], remainder


def _backtest_symbol_from_remainder(remainder: str) -> str:
    return remainder.strip().upper() or os.getenv("TELEGRAM_BACKTEST_TICKER", "SPY").strip().upper()


def _html_plan_from_last_scan(ticker_filter: str) -> str:
    """Oxirgi saqlangan skandan bitta ticker uchun trade plan (HTML `<pre>`)."""

    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
    if not path.is_file():
        return "<b>/plan</b>: avval <code>/scan</code> ishga tushiring."
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "<b>/plan</b>: <code>last_telegram_scan.json</code> nosoz."
    rows_raw = blob.get("top_signals") or []
    rows: List[Dict[str, Any]] = rows_raw if isinstance(rows_raw, list) else []
    want = (ticker_filter or "").strip().upper()
    candidates = [r for r in rows if str(r.get("ticker", "")).upper() == want] if want else rows
    if not candidates:
        return (
            f"<b>/plan</b>: <code>{_escape_html(want or '—')}</code> topilmadi. "
            f"<code>/plan AAPL</code> yoki avval <code>/scan</code>."
        )
    r = candidates[0]
    sym = _escape_html(str(r.get("ticker", "?")))
    body = (str(r.get("analyst_trade_plan_text") or "").strip()) or (
        str(r.get("ignition_professional_outline") or "").strip()
    )
    if not body:
        body = deterministic_trade_plan_from_signal(
            r,
            lang=os.getenv("ANALYST_TRADE_PLAN_LANG", "uz"),
        )
    if not body:
        return f"<b>Plan</b> <code>{sym}</code> — matn yo‘q."
    return f"<b>Trade plan · {sym}</b>\n<pre>{_escape_html(body)}</pre>"


def _reply_keyboard_markup() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": BTN_SCAN}, {"text": BTN_SIGNALS}],
            [{"text": BTN_PLAN}, {"text": BTN_STATUS}],
            [{"text": BTN_RISK}, {"text": BTN_HELP}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _send_html(
    token: str,
    chat_id: str,
    text: str,
    *,
    disable_preview: bool = True,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> None:
    chunks: List[str] = []
    t = text
    while len(t) > MAX_MESSAGE_LEN:
        chunks.append(t[:MAX_MESSAGE_LEN])
        t = t[MAX_MESSAGE_LEN:]
    if t:
        chunks.append(t)
    for i, c in enumerate(chunks):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": c,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup is not None and i == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(
                f"{TG_API}/bot{token}/sendMessage",
                json=payload,
                timeout=30,
            )
            if not response.ok:
                print(f"telegram_command_bot sendMessage error: {response.status_code} {response.text[:300]}", flush=True)
        except requests.RequestException as exc:
            print(f"telegram_command_bot sendMessage request failed: {exc}", flush=True)


def _escape_html(s: Any) -> str:
    text = "" if s is None else str(s)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_auto_push_at(raw: str) -> tuple[int, int] | None:
    """`HH:MM` yoki `H:MM` — 00:00–23:59."""

    s = raw.strip()
    if not s or s.count(":") != 1:
        return None
    a, b = s.split(":", 1)
    try:
        hh = int(a.strip(), 10)
        mm = int(b.strip(), 10)
    except ValueError:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def _next_scheduled_fire_utc(hh: int, mm: int, tz_name: str) -> datetime:
    """Keyingi `hh:mm` lokal vaqt (NY savdo haftasi kunlarida)."""

    try:
        tz = ZoneInfo((tz_name or "Asia/Tashkent").strip() or "Asia/Tashkent")
    except Exception:
        tz = ZoneInfo("Asia/Tashkent")
    now_local = datetime.now(tz)
    for days_ahead in range(400):
        d = now_local.date() + timedelta(days=days_ahead)
        cand = datetime.combine(d, dt_time(hh, mm), tzinfo=tz)
        if cand <= now_local:
            continue
        ny = cand.astimezone(NY_TZ)
        if is_weekday_et(ny):
            return cand.astimezone(UTC)
    return datetime.now(UTC) + timedelta(hours=1)


def _next_ny_rth_open_utc(from_ny: datetime | None = None) -> datetime:
    """Keyingi NY oddiy sessiya 09:30 ET ochilish (UTC)."""

    base = from_ny or datetime.now(NY_TZ)
    d = base.date()
    open_t, _ = ny_session_bounds_for_date(d)
    if base.weekday() < 5 and base < open_t:
        return open_t.astimezone(UTC)
    for i in range(1, 22):
        d2 = d + timedelta(days=i)
        open_t2, _ = ny_session_bounds_for_date(d2)
        if open_t2.weekday() < 5:
            return open_t2.astimezone(UTC)
    return open_t.astimezone(UTC)


def _format_market_clock_footer() -> str:
    """NY ochilish va UZ vaqti — foydalanuvchi bozor oldi tayyorlovni solishtirishi uchun."""

    uz = ZoneInfo("Asia/Tashkent")
    open_utc = _next_ny_rth_open_utc()
    open_ny = open_utc.astimezone(NY_TZ)
    open_uz = open_utc.astimezone(uz)
    return (
        f"<i>Keyingi NY RTH ochilish: <code>{_escape_html(open_ny.strftime('%Y-%m-%d %H:%M %Z'))}</code> · "
        f"O‘zbekiston: <code>{_escape_html(open_uz.strftime('%Y-%m-%d %H:%M %Z'))}</code></i>\n"
    )


def _partition_ranked(ranked: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    passes = [r for r in ranked if not r.get("watchlist_only")]
    watchlist = [r for r in ranked if r.get("watchlist_only")]
    return passes, watchlist


def _signal_status_badge(row: Dict[str, Any]) -> str:
    if bool(row.get("amt_buy_signal")) or row.get("babir_amt_card"):
        return "🟢 AMT BUY"
    if row.get("babir_amt_near"):
        return "🟡 AMT VAL"
    regime = str(row.get("market_regime") or "").upper()
    if regime == "NEWS_LOCK":
        return "⛔ NEWS_LOCK"
    if regime == "RISK_OFF":
        return "🔴 RISK_OFF"
    if row.get("watchlist_only"):
        return "🟡 KUZATUV"
    if bool(row.get("paper_trade_ready")):
        return "🟢 PAPER"
    if row.get("strategy_pass"):
        return "🔵 SIGNAL"
    return "🟡 WATCH"


def _format_signal_line(row: Dict[str, Any]) -> str:
    t = _escape_html(row.get("ticker", "?"))
    score = row.get("score", 0)
    strat = _escape_html(row.get("strategy_name", "") or "—")
    dec = _escape_html(row.get("chatgpt_decision", "") or "—")
    badge = _signal_status_badge(row)
    tv = _tradingview_url(str(row.get("ticker", "")))
    rvol = row.get("rvol")
    rvol_txt = ""
    if rvol is not None:
        try:
            rvol_txt = f" · RVOL {_escape_html(round(float(rvol), 2))}"
        except (TypeError, ValueError):
            pass

    lines_out = [
        f"<b>{t}</b> · {badge} · skor {score}{rvol_txt}",
        f"AI: {dec} · {strat} · <a href=\"{tv}\">Chart</a>",
    ]

    levels_line = str(row.get("trade_levels_line") or "").strip()
    if levels_line:
        style = str(row.get("trade_setup_style") or "").strip()
        tag = "⚡" if style.startswith("scalp") else "📊"
        lines_out.append(f"{tag} <code>{_escape_html(levels_line)}</code>")
    else:
        price = row.get("price")
        bits: list[str] = []
        if price is not None:
            try:
                bits.append(f"narx {_escape_html(round(float(price), 2))}")
            except (TypeError, ValueError):
                pass
        sl = row.get("stop_suggestion") or row.get("trade_stop_loss")
        tp = row.get("take_profit_suggestion") or row.get("trade_tp1")
        if sl is not None:
            try:
                bits.append(f"SL {_escape_html(round(float(sl), 2))}")
            except (TypeError, ValueError):
                pass
        if tp is not None:
            try:
                bits.append(f"TP {_escape_html(round(float(tp), 2))}")
            except (TypeError, ValueError):
                pass
        if bits:
            lines_out.append(" · ".join(bits))

    mtf = str(row.get("mtf_summary_line") or "").strip()
    if mtf:
        if len(mtf) > 140:
            mtf = mtf[:137] + "…"
        lines_out.append(f"↳ {_escape_html(mtf)}")
    amt_inline = format_amt_zone_inline(row)
    if amt_inline:
        lines_out.append(f"↳ 🟢 <b>{_escape_html(amt_inline)}</b>" if bool(row.get("amt_buy_signal")) else f"↳ {_escape_html(amt_inline)}")
    else:
        amt_s = str(row.get("amt_summary_line") or "").strip()
        if amt_s:
            if len(amt_s) > 130:
                amt_s = amt_s[:127] + "…"
            prefix = "🟢 " if bool(row.get("amt_buy_signal")) else ""
            lines_out.append(f"↳ {prefix}{_escape_html(amt_s)}")

    if row.get("watchlist_only"):
        failed = row.get("failed_rules")
        if isinstance(failed, list) and failed:
            lines_out.append(f"<i>Qoidalar: {_escape_html(', '.join(str(x) for x in failed[:4]))}</i>")

    return "\n".join(lines_out)


def _build_scan_result_html(
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    *,
    top_n: int,
    include_watchlist: bool = True,
    heading: Optional[str] = "Skan yakunlandi",
    compact: bool = False,
) -> str:
    passes, watchlist = _partition_ranked(ranked)
    lines: List[str] = []
    if heading:
        lines.append(f"<b>{heading}</b>\n")
    if not compact:
        wl_n = int(summary.get("watchlist_fallback_count") or len(watchlist))
        stats = (
            f"Desk: {_escape_html(summary.get('desk_label'))} · "
            f"Preset: {_escape_html(summary.get('scan_preset'))}\n"
            f"Tickers: {summary.get('tickers_scanned')} · "
            f"pass: {summary.get('eligible_signals')} · "
            f"paper-ready: {summary.get('paper_ready_signals', '—')}"
        )
        if wl_n:
            stats += f" · kuzatuv: {wl_n}"
        amt_n = int(summary.get("amt_buy_count") or 0)
        if amt_n:
            stats += f" · AMT BUY: {amt_n}"
        regime = str(summary.get("market_regime") or "").strip()
        if regime:
            stats += f" · Market: <b>{_escape_html(regime)}</b>"
        shield_line = str(summary.get("market_shield_summary_line") or "").strip()
        if shield_line:
            lines.append(f"<i>{_escape_html(shield_line)}</i>\n")
        lines.append(stats + "\n")
    lines.append(_format_market_clock_footer())

    show_babir_amt = _truthy_env("TELEGRAM_BABIR_AMT_IN_SCAN", default=True)
    amt_rows = summary.get("amt_buy_signals") or []
    if show_babir_amt and isinstance(amt_rows, list) and amt_rows:
        show_amt = [r for r in amt_rows if isinstance(r, dict) and r.get("amt_buy_signal")][:top_n]
        if show_amt:
            lines.append(f"<b>🟢 AMT BUY · VAL↑</b> <i>({len(show_amt)})</i>\n")
            for r in show_amt:
                lines.append(
                    format_amt_buy_line(r, chart_url=_tradingview_url(str(r.get("ticker", ""))))
                    + "\n\n"
                )
    elif not amt_buy_alert_enabled():
        if isinstance(amt_rows, list) and amt_rows:
            show_amt = [r for r in amt_rows if isinstance(r, dict) and r.get("amt_buy_signal")][:top_n]
            if show_amt:
                lines.append(f"<b>AMT Volume Profile BUY ({len(show_amt)})</b>\n")
                for r in show_amt:
                    lines.append(
                        format_amt_buy_line(r, chart_url=_tradingview_url(str(r.get("ticker", ""))))
                        + "\n\n"
                    )

    if passes:
        lines.append(f"<b>Signallar ({min(len(passes), top_n)})</b>\n")
        for r in passes[:top_n]:
            lines.append(_format_signal_line(r) + "\n\n")
    elif not watchlist:
        lines.append("— Hozircha mos signal yo‘q. Bozor sust bo‘lishi mumkin.\n\n")

    if include_watchlist and watchlist:
        lines.append(f"<b>Kuzatuv ro‘yxati</b> <i>(signal emas)</i>\n")
        for r in watchlist[:top_n]:
            lines.append(_format_signal_line(r) + "\n\n")

    top_failed = summary.get("top_failed_rules") or []
    if top_failed:
        rendered = ", ".join(f"{name}:{count}" for name, count in top_failed[:3])
        lines.append(f"Sabab top-qoidalar: {rendered}\n")
    src_summary = summary.get("provider_source_summary") or {}
    quote_mix = src_summary.get("quote") if isinstance(src_summary, dict) else {}
    if isinstance(quote_mix, dict) and quote_mix:
        mix_txt = ", ".join(f"{k}:{v}" for k, v in list(quote_mix.items())[:3])
        lines.append(f"Quote manbalari: {mix_txt}\n")
    return "".join(lines)


def _normalize_tv_symbol(raw: str) -> str:
    sym = raw.strip().upper()
    if not sym:
        return ""
    return sym if ":" in sym else f"NASDAQ:{sym}"


def _tradingview_url(symbol_like: str) -> str:
    sym = _normalize_tv_symbol(symbol_like)
    if not sym:
        return "https://www.tradingview.com/chart/"
    return f"https://www.tradingview.com/chart/?symbol={quote(sym, safe=':')}"


def _persist_last_scan(
    *,
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    universe_size: int,
) -> None:
    state_dir = PROJECT_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    top_n = _env_int_bounded("TELEGRAM_BOT_TOP_ROWS", 6, 1, 500)
    amt_persist = summary.get("amt_buy_signals") or []
    if not isinstance(amt_persist, list):
        amt_persist = []
    amt_cap = _amt_buy_top_n()
    payload = {
        "saved_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "universe_size": universe_size,
        "summary": summary,
        "top_signals": ranked[:top_n],
        "amt_buy_signals": amt_persist[:amt_cap],
    }
    path = state_dir / "last_telegram_scan.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _telegram_reply_top_n() -> int:
    return _env_int_bounded("TELEGRAM_BOT_REPLY_TOP_N", 20, 1, 500)


def _amt_buy_top_n() -> int:
    return _env_int_bounded("TELEGRAM_AMT_BUY_TOP_N", 20, 1, 50)


def _resolve_auto_push_chat_id(allowed: Optional[set[str]]) -> Optional[str]:
    """Avtomatik push uchun chat: TELEGRAM_AUTO_PUSH_CHAT_ID > TELEGRAM_CHAT_ID > (allowlistda bitta id)."""

    raw = os.getenv("TELEGRAM_AUTO_PUSH_CHAT_ID", "").strip()
    if raw:
        try:
            cid = str(int(raw.replace(" ", ""), 10))
        except ValueError:
            return None
    else:
        raw2 = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not raw2:
            if allowed and len(allowed) == 1:
                return next(iter(allowed))
            return None
        try:
            cid = str(int(raw2.replace(" ", ""), 10))
        except ValueError:
            return None
    if allowed is not None and cid not in allowed:
        return None
    return cid


def _execute_scan_send_persist(
    token: str,
    chat_s: str,
    *,
    run_all: bool,
    heading_html: str = "",
    for_auto_push: bool = False,
) -> None:
    """Skan → state → HTML xabar ( /scan va fon push uchun umumiy yo‘l )."""

    kb = _reply_keyboard_markup()
    ctrls = telegram_default_controls()
    if run_all:
        max_all = _env_int_bounded("TELEGRAM_MAX_SYMBOLS_ALL", 0, 0, 9_999_999)
        ctrls = SidebarControls(
            desk_label=f"{ctrls.desk_label} all-us",
            max_symbols=max_all,
            preset_name=ctrls.preset_name,
            rvol_thresholds=dict(ctrls.rvol_thresholds),
            max_workers=ctrls.max_workers,
            finviz_csv_universe=ctrls.finviz_csv_universe,
        )
    tickers = fetch_universe_for_scan(ctrls)
    n_tickers = len(tickers)
    if run_all:
        start_msg = f"Keng skan boshlandi… <b>{n_tickers}</b> ticker tekshiriladi."
    else:
        start_msg = f"Skan boshlandi… <b>{n_tickers}</b> ticker (2 xabar: skan + AMT)."
    if heading_html:
        _send_html(token, chat_s, f"{heading_html}\n{start_msg}", reply_markup=kb)
    else:
        _send_html(token, chat_s, start_msg, reply_markup=kb)

    prev_alert_on_scan = os.environ.get("TELEGRAM_ALERT_ON_SCAN")
    prev_yahoo_first = os.environ.get("INTRADAY_YAHOO_BEFORE_POLYGON")
    os.environ["TELEGRAM_ALERT_ON_SCAN"] = "false"
    if _truthy_env("TELEGRAM_INTRADAY_YAHOO_FIRST", default=True):
        os.environ["INTRADAY_YAHOO_BEFORE_POLYGON"] = "true"
    try:
        ranked, _views, summary = run_scan_market(
            tickers,
            ctrls,
            repo_root=PROJECT_DIR,
            progress=None,
        )
        if not ranked and ctrls.preset_name != "Explorer":
            explorer_ctrls = SidebarControls(
                desk_label=ctrls.desk_label,
                max_symbols=ctrls.max_symbols,
                preset_name="Explorer",
                rvol_thresholds=dict(SCAN_PRESETS["Explorer"]),
                max_workers=ctrls.max_workers,
                finviz_csv_universe=ctrls.finviz_csv_universe,
            )
            tickers = fetch_universe_for_scan(explorer_ctrls)
            ranked, _views, summary = run_scan_market(
                tickers,
                explorer_ctrls,
                repo_root=PROJECT_DIR,
                progress=None,
            )
    finally:
        if prev_alert_on_scan is None:
            os.environ.pop("TELEGRAM_ALERT_ON_SCAN", None)
        else:
            os.environ["TELEGRAM_ALERT_ON_SCAN"] = prev_alert_on_scan
        if prev_yahoo_first is None:
            os.environ.pop("INTRADAY_YAHOO_BEFORE_POLYGON", None)
        else:
            os.environ["INTRADAY_YAHOO_BEFORE_POLYGON"] = prev_yahoo_first

    if _truthy_env("TELEGRAM_BABIR_MERGE_AMT_RANKED", default=True):
        ranked = enrich_ranked_for_babir(ranked, summary)

    _persist_last_scan(ranked=ranked, summary=summary, universe_size=len(tickers))

    top_n = _telegram_reply_top_n()
    passes, watch = _partition_ranked(ranked)
    # Babir uslubi (sukut): pass bo‘lmasa ham kuzatuv ro‘yxati. true = faqat haqiqiy pass.
    pass_only_push = for_auto_push and _truthy_env("TELEGRAM_AUTO_PUSH_PASS_ONLY", default=False)
    babir_watchlist = for_auto_push and _truthy_env("TELEGRAM_AUTO_PUSH_BABIR_WATCHLIST", default=True)

    if pass_only_push and not passes:
        _send_html(
            token,
            chat_s,
            (
                "<b>Avtomatik skan</b>\n"
                f"Tickers: {summary.get('tickers_scanned')} · pass: 0 · paper-ready: 0\n"
                "Hozircha strategiya filtridan o‘tgan signal yo‘q.\n"
                "Kuzatuv uchun: <code>TELEGRAM_AUTO_PUSH_PASS_ONLY=false</code> (Babir uslubi)."
            ),
            reply_markup=kb,
        )
        return

    if for_auto_push and babir_watchlist:
        include_watchlist = True
        scan_heading: Optional[str] = "Babir market skani"
    else:
        include_watchlist = not pass_only_push
        scan_heading = "Skan yakunlandi"

    if for_auto_push and not passes and watch:
        scan_heading = "Babir kuzatuv skani"

    body = _build_scan_result_html(
        ranked,
        summary,
        top_n=top_n,
        include_watchlist=include_watchlist,
        heading=scan_heading,
    )
    _send_html(token, chat_s, body, reply_markup=kb)

    # 2-xabar: har doim AMT bo‘limi (BUY + ixtiyoriy VAL yaqin kuzatuv)
    if amt_buy_alert_enabled():
        amt_rows_raw = summary.get("amt_buy_signals") or []
        near_raw = summary.get("amt_near_val_signals") or []
        amt_rows = [r for r in amt_rows_raw if isinstance(r, dict)][:_amt_buy_top_n()]
        near_rows = [r for r in near_raw if isinstance(r, dict)]
        amt_html = build_amt_buy_alert_html(
            amt_rows,
            summary=summary,
            chart_url_builder=_tradingview_url,
            near_rows=near_rows,
        )
        _send_html(token, chat_s, amt_html, reply_markup=kb)

    if _truthy_env("TELEGRAM_APPEND_FRAMEWORKS", default=False) and not for_auto_push:
        _send_html(token, chat_s, build_telegram_framework_appendices_html(), reply_markup=kb)


def _auto_push_loop(token: str, chat_id: str, scan_lock: threading.Lock) -> None:
    """Kunlik: interval yoki lokal soat bo‘yicha (UZ vaqti bilan NY savdo kunlari)."""

    interval_min = _env_int_bounded("TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES", 1440, 15, 10080)
    use_scanall = _truthy_env("TELEGRAM_AUTO_PUSH_USE_SCANALL", default=False)
    first_delay_sec = max(30, _env_int_bounded("TELEGRAM_AUTO_PUSH_FIRST_DELAY_SEC", 120, 30, 3600))
    at_raw = os.getenv("TELEGRAM_AUTO_PUSH_AT", "").strip()
    parsed_at = _parse_auto_push_at(at_raw) if at_raw else None
    tz_name = os.getenv("TELEGRAM_AUTO_PUSH_TZ", "Asia/Tashkent").strip() or "Asia/Tashkent"

    if parsed_at:
        hh, mm = parsed_at
        print(
            f"telegram_command_bot: auto-push — jadval rejimi {hh:02d}:{mm:02d} ({tz_name}), "
            f"NY hafta ichida · scanall={'ha' if use_scanall else 'yoq'} → chat {chat_id} "
            f"(birinchi sinxron ~{first_delay_sec}s)",
            flush=True,
        )
    else:
        print(
            f"telegram_command_bot: auto-push yoqilgan — har {interval_min} daqiqada, "
            f"scanall={'ha' if use_scanall else 'yoq'} → chat {chat_id} (birinchi push ~{first_delay_sec}s)",
            flush=True,
        )
    time.sleep(float(first_delay_sec))
    while True:
        if not _truthy_env("TELEGRAM_AUTO_PUSH_ENABLED", default=False):
            time.sleep(300)
            continue

        if parsed_at:
            hh, mm = parsed_at
            next_utc = _next_scheduled_fire_utc(hh, mm, tz_name)
            sleep_sec = max(15.0, (next_utc - datetime.now(UTC)).total_seconds())
            print(
                f"telegram_command_bot: auto-push jadval — keyingi {next_utc.strftime('%Y-%m-%d %H:%M UTC')} "
                f"(~{int(sleep_sec)}s)",
                flush=True,
            )
            time.sleep(sleep_sec)

        if not scan_lock.acquire(blocking=False):
            print("telegram_command_bot: auto-push — skan band, keyingi safarga qoldirildi", flush=True)
            time.sleep(60)
            continue
        try:
            if parsed_at:
                head = (
                    "<b>Kunlik tayyorlov</b> <i>(NY savdo kuni — "
                    f"{_escape_html(tz_name)} {_escape_html(f'{parsed_at[0]:02d}:{parsed_at[1]:02d}')})</i>"
                )
            else:
                head = "<b>Avtomatik market skani</b> <i>(Babir uslubi)</i>"
            _execute_scan_send_persist(
                token,
                chat_id,
                run_all=use_scanall,
                heading_html=head,
                for_auto_push=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"telegram_command_bot: auto-push xato: {exc}", flush=True)
            try:
                _send_html(
                    token,
                    chat_id,
                    f"<b>Avtomatik skan xato</b>\n<code>{_escape_html(str(exc))[:500]}</code>",
                )
            except Exception:
                pass
        finally:
            scan_lock.release()

        if parsed_at:
            continue
        time.sleep(interval_min * 60)


_help_text = """<b>Mavjud buyruqlar</b>
/start yoki /help — yordam
/scan — to‘liq skan (dashboard bilan bir xil konveyer)
/scanall — kattaroq qamrov (TELEGRAM_MAX_SYMBOLS_ALL dan oladi)
/plan [TICKER] — oxirgi /scan dan professional trade plan (bo‘sh TICKER = birinchi top)
/signals — oxirgi /scan ning qisqa natijasi (agar saqlangan bo‘lsa; worker restart/deploydan keyin yo‘qolishi mumkin)
<i>Telegram (ixtiyoriy .env):</i> <code>TELEGRAM_BOT_REPLY_TOP_N</code> (1…500, sukut 6) — skan/signals “Top”; 
<code>TELEGRAM_BOT_TOP_ROWS</code> (1…500) — <code>last_telegram_scan.json</code>. Render blueprintda majburiy qator yo‘q. 
<code>TELEGRAM_APPEND_FRAMEWORKS</code> (sukut yoqilgan) — xabar oxirida yig‘iladigan analyst / ignition / HASAN qo‘llanmalari.
<i>Menyu:</i> bot ishga tushganda <code>setMyCommands</code> chaqiriladi — chatda <code>/</code> bosganda buyruqlar chiqadi. O‘chirish: <code>TELEGRAM_SKIP_SET_MY_COMMANDS=true</code>.
<i>LLM:</i> <code>LLM_ANALYST_FRAMEWORK_APPEND</code> (sukut yoqilgan) — ChatGPT/DeepSeek system promptiga xuddi shu tuzilma qisqacha qo‘shiladi.
<i>Avtomatik push:</i> <code>TELEGRAM_AUTO_PUSH_ENABLED=true</code> + <code>TELEGRAM_CHAT_ID</code> — har
<code>TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES</code> daqiqada (default 1440 ≈ kuniga 1 marta) yoki
<code>TELEGRAM_AUTO_PUSH_AT=18:30</code> + <code>TELEGRAM_AUTO_PUSH_TZ=Asia/Tashkent</code> bilan NY hafta ichida
shu lokal soatda (bozor ochilishidan oldin tayyorlov) top tickerlar yuboriladi.
<code>TELEGRAM_AUTO_PUSH_PASS_ONLY=false</code> (sukut, Babir) — pass bo‘lmasa ham kuzatuv ro‘yxati (~6–10 ticker).
<code>TELEGRAM_AUTO_PUSH_BABIR_WATCHLIST=true</code> (sukut) — avto-pushda kuzatuv bo‘limi.
<i>Pastki menyu:</i> 📊 Skan, 📋 Signallar va boshqalar — chat pastidagi tugmalar.
/tv [TICKER] — TradingView chart link (misol: <code>/tv AAPL</code> yoki <code>/tv NYSE:IBM</code>)
/status — bot/worker holati va env diagnostika
/risk — paper risk limitlari (tez ko‘rish)
/paper — hozircha stub (Alpaca paper keyin ulanadi)
/backtest [TICKER] — oddiy SMA crossover MVP (yahoo kunlik; misol: <code>/backtest AAPL</code>)
<i>Skalp / day trade:</i> har signalda <b>KIRISH · SL · CHIQISH1/2</b> (<code>trade_levels_line</code>) — AMT yoki strategiya SL/TP; <code>SCALP_DAYTRADE_LEVELS_ENABLED=true</code> (sukut).
<i>AMT scalping:</i> <code>AMT_VWAP_SCALP_ENABLED=true</code> — VAL/POC/VAH + EMA9 BUY (Pine: AMT Scalping &amp; Volume Profile).
<code>TELEGRAM_AMT_BUY_ALERT_SEPARATE=true</code> (sukut) — AMT BUY alohida Telegram xabari.
<code>AMT_RANK_BUY_FIRST=true</code> — Topda BUY yuqoriga.

<i>Ma’lumot:</i> narh/volume va intraday barlar odatda Alpaca → Polygon → Yahoo (yfinance,
kalit shart emas) tartibida tortiladi; Polygon cheklovi bo‘lsa
<code>INTRADAY_YAHOO_BEFORE_POLYGON=true</code> bilan intradayda Yahoo avval sinanadi."""


def _status_html() -> str:
    trading_mode = os.getenv("TRADING_MODE", "paper").strip().lower() or "paper"
    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()
    paper_ok = trading_mode == "paper" and "paper-api.alpaca.markets" in base
    key_ok = bool(os.getenv("ALPACA_API_KEY", "").strip() and os.getenv("ALPACA_SECRET_KEY", "").strip())
    tg_key_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    max_pos = os.getenv("MAX_POSITION_SIZE_USD", "10000").strip()
    max_risk = os.getenv("MAX_RISK_PCT_OF_EQUITY", os.getenv("MAX_RISK_PCT", "1.0")).strip()
    min_rr = os.getenv("MIN_RISK_REWARD_RATIO", "2.0").strip()
    ks = os.getenv("TELEGRAM_SKIP_DELETE_WEBHOOK", "false").strip().lower()
    ap_en = os.getenv("TELEGRAM_AUTO_PUSH_ENABLED", "false").strip().lower()
    ap_iv = os.getenv("TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES", "1440").strip()
    ap_sa = os.getenv("TELEGRAM_AUTO_PUSH_USE_SCANALL", "false").strip().lower()
    ap_at = os.getenv("TELEGRAM_AUTO_PUSH_AT", "").strip()
    ap_tz = os.getenv("TELEGRAM_AUTO_PUSH_TZ", "Asia/Tashkent").strip()
    ap_pass = os.getenv("TELEGRAM_AUTO_PUSH_PASS_ONLY", "false").strip().lower()
    ap_babir = os.getenv("TELEGRAM_AUTO_PUSH_BABIR_WATCHLIST", "true").strip().lower()
    return (
        "<b>Bot status</b>\n"
        f"TRADING_MODE: <code>{_escape_html(trading_mode)}</code>\n"
        f"ALPACA_BASE_URL: <code>{_escape_html(base)}</code>\n"
        f"Paper config: <b>{'OK' if paper_ok else 'CHECK'}</b>\n"
        f"Alpaca keys: <b>{'OK' if key_ok else 'MISSING'}</b>\n"
        f"Telegram token: <b>{'OK' if tg_key_ok else 'MISSING'}</b>\n"
        f"TELEGRAM_AUTO_PUSH_ENABLED: <code>{_escape_html(ap_en)}</code> · interval_min: <code>{_escape_html(ap_iv)}</code> · "
        f"scanall: <code>{_escape_html(ap_sa)}</code>\n"
        f"TELEGRAM_AUTO_PUSH_AT: <code>{_escape_html(ap_at or '—')}</code> · TZ: <code>{_escape_html(ap_tz)}</code>\n"
        f"TELEGRAM_AUTO_PUSH_PASS_ONLY: <code>{_escape_html(ap_pass)}</code> · "
        f"BABIR_WATCHLIST: <code>{_escape_html(ap_babir)}</code>\n"
        f"MAX_POSITION_SIZE_USD: <code>{_escape_html(max_pos)}</code>\n"
        f"MAX_RISK_PCT_OF_EQUITY: <code>{_escape_html(max_risk)}</code>\n"
        f"MIN_RISK_REWARD_RATIO: <code>{_escape_html(min_rr)}</code>\n"
        f"TELEGRAM_SKIP_DELETE_WEBHOOK: <code>{_escape_html(ks)}</code>\n"
    )


def main() -> None:
    ensure_env_file(PROJECT_DIR)
    load_project_env(PROJECT_DIR)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is required.", file=sys.stderr)
        sys.exit(1)

    allowed = _effective_allowed_chat_ids(token)

    skip_wh = os.getenv("TELEGRAM_SKIP_DELETE_WEBHOOK", "").strip().lower() in {"1", "true", "yes", "on"}
    if not skip_wh:
        _delete_webhook_for_long_poll(token)

    _register_bot_menu_commands(token)

    scan_lock = threading.Lock()

    push_chat = _resolve_auto_push_chat_id(allowed)
    if _truthy_env("TELEGRAM_AUTO_PUSH_ENABLED", default=False) and push_chat:
        threading.Thread(
            target=_auto_push_loop,
            args=(token, push_chat, scan_lock),
            daemon=True,
            name="telegram-auto-push",
        ).start()
    elif _truthy_env("TELEGRAM_AUTO_PUSH_ENABLED", default=False):
        print(
            "telegram_command_bot: TELEGRAM_AUTO_PUSH_ENABLED=true lekin push chat id topilmadi "
            "(TELEGRAM_AUTO_PUSH_CHAT_ID yoki TELEGRAM_CHAT_ID / allowlistda bitta chat).",
            flush=True,
        )

    offset: Optional[int] = None
    print("telegram_command_bot: polling...", flush=True)

    while True:
        try:
            params: Dict[str, Any] = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(f"{TG_API}/bot{token}/getUpdates", params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as exc:
            r = getattr(exc, "response", None)
            if r is not None and r.status_code == 409:
                print(
                    "getUpdates 409 Conflict: boshqa getUpdates ishlayotganda webhook yoki token dublikati. "
                    "Render worker / boshqa terminalni to‘xtating; keyin webhook o‘chiriladi va qayta uriniladi.",
                    flush=True,
                )
                _delete_webhook_for_long_poll(token)
                time.sleep(6)
                continue
            print(f"getUpdates error: {exc}", flush=True)
            time.sleep(3)
            continue
        except requests.RequestException as exc:
            print(f"getUpdates error: {exc}", flush=True)
            time.sleep(3)
            continue

        if not data.get("ok"):
            print(f"getUpdates bad: {data}", flush=True)
            time.sleep(3)
            continue

        updates = data.get("result") or []
        if not isinstance(updates, list):
            time.sleep(0.5)
            continue

        for upd in updates:
            offset = int(upd["update_id"]) + 1

            msg = (
                upd.get("message")
                or upd.get("edited_message")
                or upd.get("channel_post")
            )
            if not msg:
                continue
            chat_id = msg.get("chat", {}).get("id")
            if chat_id is None:
                continue
            chat_s = str(chat_id)
            if allowed is not None and chat_s not in allowed:
                print(
                    f"telegram_command_bot: chat_id={chat_s} ruxsatli emas (TELEGRAM_ALLOWED_CHAT_IDS).",
                    flush=True,
                )
                continue

            text = (msg.get("text") or "").strip()
            kb = _reply_keyboard_markup()
            if text in _TEXT_BUTTON_TO_CMD:
                cmd, _remainder = _TEXT_BUTTON_TO_CMD[text]
            else:
                cmd, _remainder = _command_from_text(text)
            cmd = cmd.lower()
            try:
                if cmd in {"", "start", "help"}:
                    _send_html(token, chat_s, _help_text, reply_markup=kb)
                    continue

                if cmd == "status":
                    _send_html(token, chat_s, _status_html(), reply_markup=kb)
                    continue

                if cmd == "risk":
                    risk_msg = (
                        "<b>Risk limitlar</b>\n"
                        f"MAX_POSITION_SIZE_USD: <code>{_escape_html(os.getenv('MAX_POSITION_SIZE_USD', '10000'))}</code>\n"
                        f"MAX_DAILY_LOSS_USD: <code>{_escape_html(os.getenv('MAX_DAILY_LOSS_USD', '50'))}</code>\n"
                        f"MAX_TRADES_PER_DAY: <code>{_escape_html(os.getenv('MAX_TRADES_PER_DAY', '5'))}</code>\n"
                        f"MAX_RISK_PCT_OF_EQUITY: <code>{_escape_html(os.getenv('MAX_RISK_PCT_OF_EQUITY', os.getenv('MAX_RISK_PCT', '1.0')))}</code>\n"
                        f"MIN_RISK_REWARD_RATIO: <code>{_escape_html(os.getenv('MIN_RISK_REWARD_RATIO', '2.0'))}</code>\n"
                    )
                    _send_html(token, chat_s, risk_msg, reply_markup=kb)
                    continue

                if cmd == "signals":
                    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
                    if not path.is_file():
                        _send_html(
                            token,
                            chat_s,
                            "Hali skan yozuvi yo‘q. Avval /scan ishga tushiring.",
                            reply_markup=kb,
                        )
                        continue
                    try:
                        blob = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        _send_html(
                            token,
                            chat_s,
                            "last_telegram_scan.json bo‘sh yoki nosoz.",
                            reply_markup=kb,
                        )
                        continue
                    summary = blob.get("summary") or {}
                    rows = blob.get("top_signals") or []
                    if not isinstance(rows, list):
                        rows = []
                    show_n = _telegram_reply_top_n()
                    header = (
                        f"<b>Oxirgi skan</b> ({blob.get('saved_at_utc', '')})\n"
                        f"Universe: {blob.get('universe_size', '—')} · "
                        f"pass: {summary.get('eligible_signals', '—')} / {summary.get('tickers_scanned', '—')} · "
                        f"paper-ready: {summary.get('paper_ready_signals', '—')}\n"
                    )
                    if rows:
                        msg = header + _build_scan_result_html(
                            rows,
                            summary,
                            top_n=show_n,
                            include_watchlist=True,
                            heading=None,
                            compact=True,
                        )
                    else:
                        msg = header + "— Hali signal yozuvi yo‘q. Avval <code>/scan</code> yuboring.\n"
                    _send_html(token, chat_s, msg, reply_markup=kb)
                    if amt_buy_alert_enabled():
                        amt_saved = blob.get("amt_buy_signals") or []
                        near_saved = (summary.get("amt_near_val_signals") or []) if summary else []
                        if not near_saved and isinstance(summary, dict):
                            near_saved = summary.get("amt_near_val_signals") or []
                        amt_html = build_amt_buy_alert_html(
                            [r for r in amt_saved if isinstance(r, dict)][:_amt_buy_top_n()],
                            summary=summary if isinstance(summary, dict) else None,
                            chart_url_builder=_tradingview_url,
                            near_rows=[r for r in near_saved if isinstance(r, dict)],
                        )
                        _send_html(token, chat_s, amt_html, reply_markup=kb)
                    continue

                if cmd == "plan":
                    sym_f = (_remainder or "").strip()
                    _send_html(token, chat_s, _html_plan_from_last_scan(sym_f), reply_markup=kb)
                    continue

                if cmd == "scanall":
                    if not scan_lock.acquire(blocking=False):
                        _send_html(
                            token,
                            chat_s,
                            "Skan allaqachon ketmoqda, biroz kuting.",
                            reply_markup=kb,
                        )
                        continue
                    try:
                        _execute_scan_send_persist(token, chat_s, run_all=True)
                    finally:
                        scan_lock.release()
                    continue

                if cmd == "scan":
                    if not scan_lock.acquire(blocking=False):
                        _send_html(
                            token,
                            chat_s,
                            "Skan allaqachon ketmoqda, biroz kuting.",
                            reply_markup=kb,
                        )
                        continue
                    try:
                        run_all = cmd == "scanall"
                        _execute_scan_send_persist(token, chat_s, run_all=run_all)
                    finally:
                        scan_lock.release()
                    continue

                if cmd in {"tv", "chart"}:
                    sym_raw = (_remainder or "").strip().upper()
                    if not sym_raw:
                        sym_raw = os.getenv("TELEGRAM_DEFAULT_CHART_SYMBOL", "AAPL").strip().upper()
                    tv_sym = _normalize_tv_symbol(sym_raw)
                    link = _tradingview_url(tv_sym)
                    _send_html(
                        token,
                        chat_s,
                        (
                            f"<b>TradingView chart</b>\n"
                            f"Symbol: <code>{_escape_html(tv_sym)}</code>\n"
                            f"<a href=\"{link}\">Open chart</a>"
                        ),
                        disable_preview=False,
                    )
                    continue

                if cmd == "paper":
                    _send_html(
                        token,
                        chat_s,
                        f"<code>/{cmd}</code> — hozircha keyingi fazada ulanadi.",
                    )
                    continue

                if cmd == "backtest":
                    sym = _backtest_symbol_from_remainder(_remainder)
                    lookback = _env_int_bounded("TELEGRAM_BACKTEST_LOOKBACK_DAYS", 400, 120, 800)
                    fast_bt = _env_int_bounded("TELEGRAM_BACKTEST_FAST_SMA", 10, 2, 200)
                    slow_bt = _env_int_bounded("TELEGRAM_BACKTEST_SLOW_SMA", 30, 3, 400)
                    if slow_bt <= fast_bt:
                        slow_bt = fast_bt + 20
                    closes_bt = daily_closes_yfinance(sym, lookback)
                    if not closes_bt:
                        _send_html(
                            token,
                            chat_s,
                            "<b>Backtest</b>: tarix chiqmadi — tarmoq yoki <code>yfinance</code> ni tekshiring.",
                        )
                        continue
                    res = sma_crossover_long_only_backtest(closes_bt, fast=fast_bt, slow=slow_bt)
                    if not res.get("ok"):
                        _send_html(
                            token,
                            chat_s,
                            f"<b>Backtest</b> <code>{_escape_html(sym)}</code>: ma’lumot yetarli emas "
                            f"(bars={res.get('bars')}, fast/slow={fast_bt}/{slow_bt}).",
                        )
                        continue
                    msg = (
                        f"<b>Backtest MVP</b> <code>{_escape_html(sym)}</code>\n"
                        f"Kunlar: {len(closes_bt)} · SMA {fast_bt}/{slow_bt}\n"
                        f"Strategiya jami: <b>{res.get('strategy_total_return_pct')}%</b> "
                        f"(long barlar: {res.get('bars_in_long')})\n"
                        f"Buy-hold (warmup dan): <b>{res.get('buy_hold_from_warmup_pct')}%</b>\n"
                        f"<i>{_escape_html(res.get('rule'))}</i>"
                    )
                    _send_html(token, chat_s, msg)
                    continue

                _send_html(
                    token,
                    chat_s,
                    "Noma'lum buyruq. /help uchun ro‘yxat.",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"telegram_command_bot command error ({cmd or 'unknown'}): {exc}", flush=True)
                _send_html(
                    token,
                    chat_s,
                    f"<b>Xato</b>: <code>/{_escape_html(cmd or 'unknown')}</code> vaqtida nosozlik bo‘ldi. "
                    "Logni tekshirib, qayta urinib ko‘ring.",
                )


if __name__ == "__main__":
    main()
