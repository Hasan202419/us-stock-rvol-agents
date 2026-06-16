"""Long-poll Telegram bot: /scan uses agents.scan_pipeline (same path as dashboard)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

# Repo root: …/us-stock-rvol-agents/
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("PROJECT_ROOT", str(PROJECT_DIR))

from agents.bootstrap_env import (  # noqa: E402
    alpaca_credentials_ok,
    alpaca_credentials_source_hint,
    ensure_env_file,
    load_project_env,
)
from agents.prop_scalp_rank import (  # noqa: E402
    filter_prop_scalp_candidates,
    rank_for_prop_scalp,
)
from agents.trade_actionable import (  # noqa: E402
    action_badge,
    classify_trade_action,
    partition_by_action,
)
from agents.telegram_paper_trade import (  # noqa: E402
    execute_paper_trade,
    format_paper_result_html,
    load_last_scan_signals,
    paper_help_html,
    paper_trading_enabled,
    pick_paper_signal,
    run_quick_paper_scan,
)
from agents.scan_pipeline import (  # noqa: E402
    SidebarControls,
    _env_int_bounded,
    fetch_trader2b_universe_for_scan,
    fetch_universe_for_scan,
    run_scan_market,
    telegram_default_controls,
    telegram_trader2b_controls,
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
    daily_candles_yfinance,
    daily_closes_yfinance,
    sma_crossover_long_only_backtest,
)
from agents.backtest_engine import (  # noqa: E402
    build_default_grid,
    replay_strategy,
    summarize,
    sweep_thresholds,
)
from agents.ibkr_market_data import fetch_ibkr_daily_candles, ibkr_enabled  # noqa: E402
from agents.signal_chart import chart_caption, render_signal_chart  # noqa: E402
from agents.bullish_buy_signal import (  # noqa: E402
    evaluate_bullish_buy,
    format_bullish_buy_report,
)

TG_API = "https://api.telegram.org"
MAX_MESSAGE_LEN = 3800

# Pastki menyu tugmalari (ReplyKeyboardMarkup)
BTN_SCAN = "📊 Skan"
BTN_SCAN2B = "⚡ 2B Skan"
BTN_SIGNALS = "📋 Signallar"
BTN_PLAN = "📝 Plan"
BTN_STATUS = "⚙️ Holat"
BTN_HELP = "❓ Yordam"
BTN_RISK = "🛡 Risk"

_TEXT_BUTTON_TO_CMD: Dict[str, tuple[str, str]] = {
    BTN_SCAN: ("scan", ""),
    BTN_SCAN2B: ("scan2b", ""),
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
        {"command": "scan2b", "description": "Trader2B ro‘yxati · 1m/5m/1H qisqa muddat"},
        {"command": "signals", "description": "Oxirgi /scan qisqa natijasi"},
        {"command": "plan", "description": "Trade plan: /plan yoki /plan AAPL"},
        {"command": "tv", "description": "TradingView link: /tv AAPL"},
        {"command": "chart", "description": "Chizilgan grafik rasm: /chart AAPL (Entry/SL/TP + zonalar)"},
        {"command": "status", "description": "Bot, Alpaca, avto-push holati"},
        {"command": "risk", "description": "Paper risk limitlari"},
        {"command": "buy", "description": "BUY signal: /buy AAPL — aniq SOTIB OL/KUTING/O‘TKAZ + savdo rejasi"},
        {"command": "paper", "description": "Alpaca paper buyurtma"},
        {"command": "backtest", "description": "Strategiya backtest: /backtest TSLA (sma|rvol|ignition|gap)"},
        {"command": "discover", "description": "Eng yaxshi sozlamani izlash (sweep)"},
        {"command": "scalp", "description": "Skalp/day-trade skaner (yfinance) — RVOL + gap + TradingView"},
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
    # Birinchi token = ticker; qolgan (masalan "sma"/"rvol") rejim.
    first = remainder.strip().split()[0] if remainder.strip() else ""
    return first.upper() or os.getenv("TELEGRAM_BACKTEST_TICKER", "SPY").strip().upper()


def _backtest_mode_from_remainder(remainder: str) -> str:
    """Remainder tokenlaridan rejim: sma | rvol | volume_ignition (default env)."""

    tokens = [t.lower() for t in remainder.strip().split()[1:]]
    if "sma" in tokens:
        return "sma"
    if "rvol" in tokens:
        return "rvol"
    if any(t in {"ignition", "volume_ignition"} for t in tokens):
        return "volume_ignition"
    if any(t in {"gap", "gapgo", "gap_go", "gap_and_go"} for t in tokens):
        return "gap_go"
    return os.getenv("TELEGRAM_BACKTEST_STRATEGY", "volume_ignition").strip().lower()


def _load_backtest_candles(symbol: str, days: int) -> list:
    """IBKR yoqilgan bo‘lsa undan, aks holda yfinance’dan kunlik OHLCV."""

    if ibkr_enabled():
        candles = fetch_ibkr_daily_candles(symbol, days=days)
        if candles:
            return candles
    return daily_candles_yfinance(symbol, days)


def _format_strategy_backtest_html(symbol: str, strategy: str, bars: int, horizon: int, summary: Dict[str, Any]) -> str:
    """replay+summarize natijasini HTML hisobot qiladi."""

    if summary.get("trades", 0) == 0:
        return (
            f"<b>Backtest</b> <code>{_escape_html(symbol)}</code> · {_escape_html(strategy)}\n"
            f"Barlar: {bars} · gorizont: {horizon}\n"
            f"<i>Signal topilmadi — thresholdlar qattiq yoki tarix qisqa.</i>"
        )
    lines = [
        f"<b>Backtest</b> <code>{_escape_html(symbol)}</code> · {_escape_html(strategy)}",
        f"Barlar: {bars} · gorizont: {horizon} bar",
        f"Signallar: <b>{summary['trades']}</b> · Win-rate: <b>{summary['win_rate_pct']}%</b>",
        f"O‘rtacha R: <b>{summary['avg_r']}</b> · Expectancy: <b>{summary['expectancy_r']}R</b>",
        f"O‘rtacha qaytish: {summary['avg_return_pct']}%",
    ]
    by_stage = summary.get("by_stage") or {}
    if by_stage:
        seg = " · ".join(f"{_escape_html(k)}: {v['win_rate_pct']}% ({v['n']})" for k, v in by_stage.items())
        lines.append(f"Bosqich: {seg}")
    by_prob = summary.get("by_probability") or {}
    if by_prob:
        seg = " · ".join(f"{_escape_html(k)}: {v['win_rate_pct']}% ({v['n']})" for k, v in by_prob.items())
        lines.append(f"Davom ehtimoli: {seg}")
    lines.append("<i>O‘tmish natija — kelajak kafolati emas.</i>")
    return "\n".join(lines)


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
            [{"text": BTN_SCAN}, {"text": BTN_SCAN2B}],
            [{"text": BTN_SIGNALS}, {"text": BTN_PLAN}],
            [{"text": BTN_STATUS}, {"text": BTN_RISK}],
            [{"text": BTN_HELP}],
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


def _send_photo(
    token: str,
    chat_id: str,
    png: bytes,
    caption: str,
    *,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Telegram sendPhoto (multipart). Caption ≤1024 belgi. Muvaffaqiyatda True."""

    data: Dict[str, Any] = {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(
            f"{TG_API}/bot{token}/sendPhoto",
            data=data,
            files={"photo": ("signal.png", png, "image/png")},
            timeout=60,
        )
        if not r.ok:
            print(f"telegram_command_bot sendPhoto error: {r.status_code} {r.text[:300]}", flush=True)
        return r.ok
    except requests.RequestException as exc:
        print(f"telegram_command_bot sendPhoto failed: {exc}", flush=True)
        return False


def _load_chart_candles(row: Dict[str, Any], ticker: str) -> List[Dict[str, Any]]:
    """Grafik uchun candles: avval saqlangan signaldan, bo'lmasa jonli MarketData (Render)."""

    candles = row.get("candles") if isinstance(row, dict) else None
    if isinstance(candles, list) and len(candles) >= 2:
        return candles
    try:
        from agents.market_data_agent import MarketDataAgent

        rec = MarketDataAgent().fetch_market_data(ticker)
        fetched = rec.get("candles") if isinstance(rec, dict) else None
        return fetched if isinstance(fetched, list) else []
    except Exception as exc:  # noqa: BLE001
        print(f"telegram_command_bot chart candles fetch error: {exc}", flush=True)
        return []


def _signal_row_for_ticker(ticker: str) -> Dict[str, Any]:
    """Oxirgi skandan ticker bo'yicha signal qatori (yo'q bo'lsa minimal stub)."""

    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
    if path.is_file():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            rows = blob.get("top_signals") or []
            if isinstance(rows, list):
                want = ticker.strip().upper()
                for r in rows:
                    if isinstance(r, dict) and str(r.get("ticker", "")).upper() == want:
                        return r
        except json.JSONDecodeError:
            pass
    return {"ticker": ticker.strip().upper()}


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
    # Watchlist / paper-ready holatlar action_badge umumiy "O'TKAZ"idan ustun: watchlist
    # qatori kuzatuv, paper-ready esa eng kuchli signal sifatida ko'rsatiladi.
    if row.get("watchlist_only"):
        return "🟡 KUZATUV"
    if bool(row.get("paper_trade_ready")):
        return "🟢 PAPER"
    clear = _truthy_env("TELEGRAM_CLEAR_TRADE_LABELS", default=True)
    if clear:
        badge = action_badge(row)
        if badge in {"✅ KIRISH", "⏳ KUTING", "⛔ O‘TKAZ"}:
            return badge
    aligned = int(row.get("mtf_alignment_count") or 0)
    total = int(row.get("mtf_alignment_total") or 0)
    if total >= 2 and aligned == total:
        return "⚡ MTF↑"
    if bool(row.get("amt_buy_signal")) or row.get("babir_amt_card"):
        return "🟢 AMT BUY"
    if row.get("babir_amt_near"):
        return "🟡 AMT VAL"
    regime = str(row.get("market_regime") or "").upper()
    if regime == "NEWS_LOCK":
        return "⛔ NEWS_LOCK"
    if regime == "RISK_OFF":
        return "🔴 RISK_OFF"
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

    act, act_reason = classify_trade_action(row)
    lines_out = [
        f"<b>{t}</b> · {badge} · skor {score}{rvol_txt}",
        f"<i>{_escape_html(act_reason)}</i>",
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


def _build_action_focused_html(
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    *,
    top_n: int,
    heading: Optional[str],
    compact: bool,
) -> str:
    """Trader2B: avval ✅ KIRISH, keyin ⏳ KUTING — savdoga aniq yo‘riqnoma."""

    enter, wait, _skip = partition_by_action(ranked)
    lines: List[str] = []
    if heading:
        lines.append(f"<b>{heading}</b>\n")
    if not compact:
        regime = str(summary.get("market_regime") or "").strip()
        if regime:
            lines.append(f"Bozor: <b>{_escape_html(regime)}</b> · ")
        lines.append(
            f"✅ Kirish: <b>{len(enter)}</b> · ⏳ Kutish: <b>{len(wait)}</b>\n"
            "<i>Faqat ✅ KIRISH — KIRISH/SL/CHIQISH1/2 to‘liq; AMT BUY yoki R:R mos.</i>\n"
        )
        shield_line = str(summary.get("market_shield_summary_line") or "").strip()
        if shield_line:
            lines.append(f"<i>{_escape_html(shield_line)}</i>\n")
    lines.append(_format_market_clock_footer())

    if enter:
        lines.append(f"<b>✅ Savdoga kirish ({min(len(enter), top_n)})</b>\n")
        for r in enter[:top_n]:
            lines_out = _format_signal_line(r)
            lines.append(lines_out + "\n\n")
    else:
        lines.append(
            "<b>✅ Hozir aniq kirish yo‘q</b>\n"
            "Bozor sharoiti yoki setup tayyor emas. ⏳ KUTING ro‘yxatini kuzating.\n\n"
        )

    if wait:
        wait_n = min(len(wait), max(3, top_n // 2))
        lines.append(f"<b>⏳ Kutish ({wait_n})</b> <i>— hali kirmang</i>\n")
        for r in wait[:wait_n]:
            lines.append(_format_signal_line(r) + "\n\n")

    return "".join(lines)


def _build_scan_result_html(
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    *,
    top_n: int,
    include_watchlist: bool = True,
    heading: Optional[str] = "Skan yakunlandi",
    compact: bool = False,
    action_focused: bool = False,
) -> str:
    if action_focused:
        return _build_action_focused_html(ranked, summary, top_n=top_n, heading=heading, compact=compact)

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
        lines.append("<b>Kuzatuv ro‘yxati</b> <i>(signal emas)</i>\n")
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


@contextmanager
def _prop_scan_env() -> Iterator[None]:
    """trader2B skan: 1m / 5m / 1H MTF + AMT scalping."""

    overrides = {
        "MTF_SNAPSHOT_ENABLED": "true",
        "MTF_TIMEFRAMES": os.getenv("TRADER2B_MTF_TIMEFRAMES", "1,5,60").strip() or "1,5,60",
        "MTF_SNAPSHOT_STRATEGY_PASS_ONLY": os.getenv("TRADER2B_MTF_PASS_ONLY", "false").strip() or "false",
        "INTRADAY_TIMEFRAME_MINUTES": os.getenv("TRADER2B_INTRADAY_TF", "5").strip() or "5",
        "AMT_TIMEFRAME_MINUTES": os.getenv("TRADER2B_AMT_TF", "5").strip() or "5",
        "AMT_VWAP_SCALP_ENABLED": "true",
        "SCALP_DAYTRADE_LEVELS_ENABLED": "true",
        "TRADE_ACTIONABLE_REQUIRE_MTF_FULL": "true",
        "TRADER2B_ACTIONABLE_ONLY": "true",
        "TELEGRAM_CLEAR_TRADE_LABELS": "true",
        "INTRADAY_YAHOO_BEFORE_POLYGON": "false",
        "TELEGRAM_INTRADAY_YAHOO_FIRST": "false",
    }
    saved: dict[str, str | None] = {}
    for key, val in overrides.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = val
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _persist_last_scan(
    *,
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    universe_size: int,
    scan_type: str = "default",
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
        "scan_type": scan_type,
        "universe_size": universe_size,
        "summary": summary,
        "top_signals": ranked[:top_n],
        "amt_buy_signals": amt_persist[:amt_cap],
    }
    path = state_dir / "last_telegram_scan.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    if scan_type == "trader2b":
        (state_dir / "last_trader2b_scan.json").write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _telegram_reply_top_n() -> int:
    return _env_int_bounded("TELEGRAM_BOT_REPLY_TOP_N", 20, 1, 500)


def _amt_buy_top_n() -> int:
    return _env_int_bounded("TELEGRAM_AMT_BUY_TOP_N", 20, 1, 50)


def _scan_chart_top_n() -> int:
    """Skan natijasiga avtomatik biriktiriladigan grafik soni (0 = o‘chiq, sukut)."""

    return _env_int_bounded("TELEGRAM_SCAN_CHART_TOP_N", 0, 0, 10)


def _chartable_top_signals(ranked: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    """Grafik chizishga yaroqli top signallar: pass (kuzatuv emas) + candles bor, skor bo‘yicha."""

    if top_n <= 0:
        return []
    out: List[Dict[str, Any]] = []
    for r in ranked:
        if not isinstance(r, dict) or r.get("watchlist_only"):
            continue
        if not r.get("strategy_pass") and not r.get("paper_trade_ready"):
            continue
        candles = r.get("candles")
        if not (isinstance(candles, list) and len(candles) >= 2):
            continue
        out.append(r)
    out.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    return out[:top_n]


def _send_top_signal_charts(token: str, chat_s: str, ranked: List[Dict[str, Any]], kb: Dict[str, Any]) -> None:
    """Skandan keyin top signallarga chizilgan grafik rasm (TELEGRAM_SCAN_CHART_TOP_N>0)."""

    rows = _chartable_top_signals(ranked, _scan_chart_top_n())
    for r in rows:
        sym = str(r.get("ticker") or "?").upper()
        try:
            png = render_signal_chart(r, r.get("candles"))
            if not png:
                continue
            caption = f"{chart_caption(r)}\n<a href=\"{_tradingview_url(sym)}\">TradingView</a>"
            _send_photo(token, chat_s, png, caption, reply_markup=kb)
        except Exception as exc:  # noqa: BLE001
            print(f"telegram_command_bot scan-chart error ({sym}): {exc}", flush=True)


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


def _start_scan_background(
    token: str,
    chat_s: str,
    scan_lock: threading.Lock,
    *,
    run_all: bool,
    scan_mode: str = "default",
) -> bool:
    """Skanni fon threadida ishga tushiradi — long-poll boshqa tugmalarni bloklamasligi uchun."""

    if not scan_lock.acquire(blocking=False):
        return False
    kb = _reply_keyboard_markup()
    if scan_mode == "trader2b":
        label = "Trader2B · 1m/5m/1H"
    else:
        label = "Keng skan" if run_all else "Skan"
    _send_html(
        token,
        chat_s,
        f"⏳ <b>{label}</b> boshlandi — boshqa tugmalar ishlaydi; natija tayyor bo‘lganda keladi.",
        reply_markup=kb,
    )

    def _worker() -> None:
        try:
            _execute_scan_send_persist(token, chat_s, run_all=run_all, scan_mode=scan_mode)
        except Exception as exc:  # noqa: BLE001
            print(f"telegram_command_bot scan worker error: {exc}", flush=True)
            _send_html(
                token,
                chat_s,
                f"<b>Skan xato</b>\n<code>{_escape_html(str(exc))[:500]}</code>",
                reply_markup=kb,
            )
        finally:
            scan_lock.release()

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"tg-scan-{'all' if run_all else 'std'}-{chat_s}",
    ).start()
    return True


def _execute_scan_send_persist(
    token: str,
    chat_s: str,
    *,
    run_all: bool,
    heading_html: str = "",
    for_auto_push: bool = False,
    scan_mode: str = "default",
) -> None:
    """Skan → state → HTML xabar ( /scan va fon push uchun umumiy yo‘l )."""

    kb = _reply_keyboard_markup()
    is_trader2b = scan_mode == "trader2b"
    if is_trader2b:
        ctrls = telegram_trader2b_controls()
        tickers = fetch_trader2b_universe_for_scan(ctrls)
    else:
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
    if is_trader2b:
        tfs = os.getenv("TRADER2B_MTF_TIMEFRAMES", "1,5,60").strip() or "1,5,60"
        start_msg = (
            f"<b>Trader2B</b> skan… <b>{n_tickers}</b> ticker "
            f"(<a href=\"https://trader2b.com/get-funded/symbols/\">Toro ro‘yxati</a>) · "
            f"MTF <code>{_escape_html(tfs)}</code> · qisqa muddat signallar."
        )
    elif run_all:
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
    scan_ctx = _prop_scan_env() if is_trader2b else nullcontext()
    try:
        with scan_ctx:
            ranked, _views, summary = run_scan_market(
                tickers,
                ctrls,
                repo_root=PROJECT_DIR,
                progress=None,
            )
        if is_trader2b and ranked:
            min_mtf = _env_int_bounded("TRADER2B_MIN_MTF_ALIGNED", 2, 1, 3)
            ranked = filter_prop_scalp_candidates(ranked, min_mtf_aligned=min_mtf)
            ranked = rank_for_prop_scalp(ranked)
            summary = dict(summary)
            summary["scan_type"] = "trader2b"
            summary["trader2b_mtf"] = os.getenv("TRADER2B_MTF_TIMEFRAMES", "1,5,60")
        if not ranked and is_trader2b:
            explorer_ctrls = SidebarControls(
                desk_label=ctrls.desk_label,
                max_symbols=ctrls.max_symbols,
                preset_name="Explorer",
                rvol_thresholds=dict(SCAN_PRESETS["Explorer"]),
                max_workers=ctrls.max_workers,
                finviz_csv_universe=False,
            )
            with _prop_scan_env():
                ranked, _views, summary = run_scan_market(
                    tickers,
                    explorer_ctrls,
                    repo_root=PROJECT_DIR,
                    progress=None,
                )
            if ranked:
                min_mtf = _env_int_bounded("TRADER2B_MIN_MTF_ALIGNED", 2, 1, 3)
                ranked = rank_for_prop_scalp(filter_prop_scalp_candidates(ranked, min_mtf_aligned=min_mtf))
        elif not ranked and ctrls.preset_name != "Explorer":
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

    _persist_last_scan(
        ranked=ranked,
        summary=summary,
        universe_size=len(tickers),
        scan_type="trader2b" if is_trader2b else "default",
    )

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

    if is_trader2b and not for_auto_push:
        include_watchlist = False
        scan_heading = "Trader2B · aniq signallar (1m/5m/1H)"
    elif for_auto_push and babir_watchlist:
        include_watchlist = True
        scan_heading = "Babir market skani"
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
        action_focused=is_trader2b and not for_auto_push,
    )
    _send_html(token, chat_s, body, reply_markup=kb)

    # Ixtiyoriy: top signallarga chizilgan grafik (TELEGRAM_SCAN_CHART_TOP_N>0)
    _send_top_signal_charts(token, chat_s, ranked, kb)

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
    use_trader2b_push = _truthy_env("TELEGRAM_AUTO_PUSH_USE_TRADER2B", default=True)
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
            if use_trader2b_push and not use_scanall:
                _execute_scan_send_persist(
                    token,
                    chat_id,
                    run_all=False,
                    heading_html=head,
                    for_auto_push=True,
                    scan_mode="trader2b",
                )
            else:
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
/scan2b — <a href="https://trader2b.com/get-funded/symbols/">Trader2B</a> Toro ro‘yxati · 1m/5m/1H MTF · qisqa muddat (AAPL TSLA PLTR ORCL va boshqalar)
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
/chart [TICKER] — <b>chizilgan grafik rasm</b>: svecha + hajm + Entry/SL/TP + qo‘llab-quvvatlash/qarshilik zonalari (oxirgi skan darajalaridan)
<i>Avto-grafik:</i> <code>TELEGRAM_SCAN_CHART_TOP_N=3</code> (0=o‘chiq, sukut) — har <code>/scan</code> dan keyin top signallarга chizilgan grafik rasm avtomatik biriktiriladi.
<i>Avto-grafik:</i> <code>TELEGRAM_SCAN_CHART_TOP_N=3</code> (sukut 0=o‘chiq, 0…10) — har <code>/scan</code> dan keyin top signallarga grafik rasm avtomatik biriktiriladi.
/status — bot/worker holati va env diagnostika
/risk — paper risk limitlari (tez ko‘rish)
/buy [TICKER] — <b>aniq BUY signal</b>: 🟢 SOTIB OL / 🟡 KUTING / 🔴 O‘TKAZ + ishonch% + professional savdo rejasi (Entry/SL/Target/R:R/pozitsiya). <code>/buy AAPL</code> yoki <code>/buy</code> (eng yaxshi BUY) — hajmga asoslangan (volume ignition) mezonlar.
/paper — Alpaca paper buyurtma (oxirgi skan yoki <code>/paper scan</code>)
/paper AAPL — ticker bo‘yicha · <code>/paper go</code> — eng yaxshi paper-ready
/paper preview [TICKER] — <i>sinov</i>: sizing + risk + R:R ko‘rsatiladi, Alpaca'ga yuborilmaydi
/scalp [TICKER ...] — <b>skalp/day-trade skaner</b>: yfinance orqali RVOL + gap + momentum bo'yicha top nomzodlar · har birida Entry/SL/TP + <a href="https://www.tradingview.com/chart/">TradingView</a> havolasi. Ixtiyoriy: <code>/scalp AAPL NVDA AMD</code> (maxsus tickers). Env: <code>SCALP_UNIVERSE</code>, <code>SCALP_SCREEN_TOP_N</code> (sukut 8), <code>SCALP_MIN_RVOL</code> (sukut 1.5).
/backtest [TICKER] [sma|rvol|ignition|gap] — strategiya backtest (yahoo/IBKR kunlik; misol: <code>/backtest NVDA gap</code> — Gap-and-Go)
<i>Skalp / day trade:</i> har signalda <b>KIRISH · SL · CHIQISH1/2</b> (<code>trade_levels_line</code>) — AMT yoki strategiya SL/TP; <code>SCALP_DAYTRADE_LEVELS_ENABLED=true</code> (sukut).
<i>AMT scalping:</i> <code>AMT_VWAP_SCALP_ENABLED=true</code> — VAL/POC/VAH + EMA9 BUY (Pine: AMT Scalping &amp; Volume Profile).
<code>TELEGRAM_AMT_BUY_ALERT_SEPARATE=true</code> (sukut) — AMT BUY alohida Telegram xabari.
<code>AMT_RANK_BUY_FIRST=true</code> — Topda BUY yuqoriga.

<i>Ma’lumot:</i> narh/volume va intraday barlar odatda Alpaca → Polygon → Yahoo (yfinance,
kalit shart emas) tartibida tortiladi; Polygon cheklovi bo‘lsa
<code>INTRADAY_YAHOO_BEFORE_POLYGON=true</code> bilan intradayda Yahoo avval sinanadi."""


def _status_html() -> str:
    from agents.ibkr_market_data import ibkr_status_line

    trading_mode = os.getenv("TRADING_MODE", "paper").strip().lower() or "paper"
    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()
    paper_ok = trading_mode == "paper" and "paper-api.alpaca.markets" in base
    key_ok = alpaca_credentials_ok()
    key_hint = alpaca_credentials_source_hint()
    tg_key_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    poly_ok = bool(os.getenv("POLYGON_API_KEY", "").strip() or os.getenv("MASSIVE_API_KEY", "").strip())
    yahoo_on = os.getenv("YAHOO_FINANCE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    prov = os.getenv("MARKET_DATA_PROVIDER_PRIORITY", "polygon,alpaca,yahoo").strip()
    max_pos = os.getenv("MAX_POSITION_SIZE_USD", "10000").strip()
    max_risk = os.getenv("MAX_RISK_PCT_OF_EQUITY", os.getenv("MAX_RISK_PCT", "1.0")).strip()
    min_rr = os.getenv("MIN_RISK_REWARD_RATIO", "2.0").strip()
    ks = os.getenv("TELEGRAM_SKIP_DELETE_WEBHOOK", "false").strip().lower()
    ap_en = os.getenv("TELEGRAM_AUTO_PUSH_ENABLED", "false").strip().lower()
    ap_iv = os.getenv("TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES", "1440").strip()
    ap_sa = os.getenv("TELEGRAM_AUTO_PUSH_USE_SCANALL", "false").strip().lower()
    ap_2b = os.getenv("TELEGRAM_AUTO_PUSH_USE_TRADER2B", "true").strip().lower()
    ap_at = os.getenv("TELEGRAM_AUTO_PUSH_AT", "").strip()
    ap_tz = os.getenv("TELEGRAM_AUTO_PUSH_TZ", "Asia/Tashkent").strip()
    ap_pass = os.getenv("TELEGRAM_AUTO_PUSH_PASS_ONLY", "false").strip().lower()
    ap_babir = os.getenv("TELEGRAM_AUTO_PUSH_BABIR_WATCHLIST", "true").strip().lower()
    return (
        "<b>Bot status</b>\n"
        f"TRADING_MODE: <code>{_escape_html(trading_mode)}</code>\n"
        f"ALPACA_BASE_URL: <code>{_escape_html(base)}</code>\n"
        f"Paper config: <b>{'OK' if paper_ok else 'CHECK'}</b>\n"
        f"Alpaca keys: <b>{'OK' if key_ok else 'MISSING'}</b>"
        f" <i>({_escape_html(key_hint)})</i>\n"
        f"Polygon/Massive: <b>{'OK' if poly_ok else '—'}</b> · Yahoo: <b>{'ON' if yahoo_on else 'OFF'}</b>\n"
        f"Data providers: <code>{_escape_html(prov or 'default')}</code>\n"
        f"{ibkr_status_line()}\n"
        f"Telegram token: <b>{'OK' if tg_key_ok else 'MISSING'}</b>\n"
        f"TELEGRAM_AUTO_PUSH_ENABLED: <code>{_escape_html(ap_en)}</code> · interval_min: <code>{_escape_html(ap_iv)}</code> · "
        f"scanall: <code>{_escape_html(ap_sa)}</code> · trader2b push: <code>{_escape_html(ap_2b)}</code>\n"
        f"TELEGRAM_AUTO_PUSH_AT: <code>{_escape_html(ap_at or '—')}</code> · TZ: <code>{_escape_html(ap_tz)}</code>\n"
        f"TELEGRAM_AUTO_PUSH_PASS_ONLY: <code>{_escape_html(ap_pass)}</code> · "
        f"BABIR_WATCHLIST: <code>{_escape_html(ap_babir)}</code>\n"
        f"MAX_POSITION_SIZE_USD: <code>{_escape_html(max_pos)}</code>\n"
        f"MAX_RISK_PCT_OF_EQUITY: <code>{_escape_html(max_risk)}</code>\n"
        f"MIN_RISK_REWARD_RATIO: <code>{_escape_html(min_rr)}</code>\n"
        f"TELEGRAM_SKIP_DELETE_WEBHOOK: <code>{_escape_html(ks)}</code>\n"
    )


def _buy_signal_for_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """BUY baholash uchun signal: oxirgi skandan yoki jonli MarketData+RVOL (Render)."""

    want = ticker.strip().upper()
    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
    if path.is_file():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            rows = blob.get("top_signals") or []
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and str(r.get("ticker", "")).upper() == want:
                        if isinstance(r.get("candles"), list) and len(r["candles"]) >= 2:
                            return r
        except json.JSONDecodeError:
            pass
    try:
        from agents.market_data_agent import MarketDataAgent
        from agents.rvol_agent import RVOLAgent

        rec = MarketDataAgent().fetch_market_data(want)
        if not isinstance(rec, dict) or not rec.get("candles"):
            return None
        rec.setdefault("ticker", want)
        return RVOLAgent().calculate(rec)
    except Exception as exc:  # noqa: BLE001
        print(f"telegram_command_bot buy signal fetch error ({want}): {exc}", flush=True)
        return None


def _dispatch_buy_command(token: str, chat_s: str, remainder: str, kb: Dict[str, Any]) -> None:
    """/buy [TICKER] — qatʼiy BUY/WATCH/AVOID verdikti + professional savdo rejasi."""

    sub = (remainder or "").strip()

    def _finish_for(sig: Dict[str, Any]) -> None:
        res = evaluate_bullish_buy(sig)
        company = str(sig.get("company_name") or sig.get("company") or "")
        _send_html(token, chat_s, format_bullish_buy_report(res, company=company), reply_markup=kb)
        try:
            png = render_signal_chart(res.get("_signal") or sig, (res.get("_signal") or sig).get("candles"))
            if png:
                _send_photo(token, chat_s, png, f"{res['ticker']} · {res['verdict']}", reply_markup=kb)
        except Exception as exc:  # noqa: BLE001
            print(f"telegram_command_bot buy chart error: {exc}", flush=True)

    if sub and sub.lower() not in {"go", "top", "best"}:
        ticker = sub.split()[0].upper()
        _send_html(token, chat_s, f"⏳ BUY tahlil: <code>{_escape_html(ticker)}</code>…", reply_markup=kb)

        def _worker(t: str = ticker) -> None:
            sig = _buy_signal_for_ticker(t)
            if not sig:
                _send_html(
                    token,
                    chat_s,
                    f"<code>{_escape_html(t)}</code> uchun maʼlumot yoʻq — avval <code>/scan</code> "
                    "yoki manba ulanishini tekshiring.",
                    reply_markup=kb,
                )
                return
            _finish_for(sig)

        threading.Thread(target=_worker, daemon=True, name=f"tg-buy-{ticker}").start()
        return

    # Tickersiz: oxirgi skandagi eng yaxshi BUY ni topamiz.
    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
    rows: List[Dict[str, Any]] = []
    if path.is_file():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            raw = blob.get("top_signals") or []
            rows = [r for r in raw if isinstance(r, dict)]
        except json.JSONDecodeError:
            rows = []
    if not rows:
        _send_html(
            token,
            chat_s,
            "Oxirgi skan yoʻq. <code>/scan</code> yoki <code>/buy AAPL</code> yuboring.",
            reply_markup=kb,
        )
        return

    _send_html(token, chat_s, "⏳ Eng yaxshi BUY signal izlanmoqda…", reply_markup=kb)

    def _worker_top() -> None:
        scored = []
        for r in rows:
            if not (isinstance(r.get("candles"), list) and len(r["candles"]) >= 2):
                continue
            res = evaluate_bullish_buy(r)
            scored.append((res, r))
        buys = [(res, r) for res, r in scored if res["verdict"] == "BUY"]
        buys.sort(key=lambda x: x[0]["confidence"], reverse=True)
        if buys:
            _finish_for(buys[0][1])
            return
        if scored:
            scored.sort(key=lambda x: x[0]["confidence"], reverse=True)
            _send_html(
                token,
                chat_s,
                "Aniq <b>BUY</b> yoʻq — eng kuchli nomzod (KUTING):",
                reply_markup=kb,
            )
            _finish_for(scored[0][1])
            return
        _send_html(token, chat_s, "Grafik/candles bor signal topilmadi. Avval <code>/scan</code>.", reply_markup=kb)

    threading.Thread(target=_worker_top, daemon=True, name="tg-buy-top").start()


def _dispatch_paper_command(token: str, chat_s: str, remainder: str, kb: Dict[str, Any]) -> None:
    if not paper_trading_enabled():
        _send_html(
            token,
            chat_s,
            "<b>Paper savdo</b> o‘chirilgan: <code>TELEGRAM_PAPER_TRADING_ENABLED=false</code>",
            reply_markup=kb,
        )
        return
    if not alpaca_credentials_ok():
        _send_html(
            token,
            chat_s,
            "<b>Paper savdo</b>: Alpaca kalitlari yo‘q — Render/.env da <code>ALPACA_API_KEY</code> + secret.",
            reply_markup=kb,
        )
        return

    raw = (remainder or "").strip()
    sub = raw.lower()
    if sub in {"help", "?"}:
        _send_html(token, chat_s, paper_help_html(), reply_markup=kb)
        return

    # preview/dry: sizing+risk hisoblanadi, lekin Alpaca'ga yuborilmaydi.
    dry_run = False
    tokens = raw.split()
    if tokens and tokens[0].lower() in {"preview", "dry", "dryrun"}:
        dry_run = True
        raw = " ".join(tokens[1:]).strip()
        sub = raw.lower()

    def _finish(result: Dict[str, Any]) -> None:
        _send_html(token, chat_s, format_paper_result_html(result), reply_markup=kb)

    def _worker_scan() -> None:
        try:
            ranked, summary = run_quick_paper_scan(PROJECT_DIR)
            sig = pick_paper_signal(ranked)
            if not sig:
                pr = int(summary.get("paper_ready_signals") or 0)
                _send_html(
                    token,
                    chat_s,
                    (
                        "<b>Paper skan</b> tugadi — paper-ready signal yo‘q.\n"
                        f"Tekshirildi: {summary.get('tickers_scanned', '—')} · paper-ready: {pr}\n"
                        "Keyinroq <code>/scan</code> yoki boshqa ticker sinab ko‘ring."
                    ),
                    reply_markup=kb,
                )
                return
            _finish(execute_paper_trade(sig, repo_root=PROJECT_DIR, dry_run=dry_run))
        except Exception as exc:
            _send_html(
                token,
                chat_s,
                f"<b>Paper savdo</b> xato: <code>{_escape_html(str(exc)[:400])}</code>",
                reply_markup=kb,
            )

    if sub == "scan":
        _send_html(token, chat_s, "⏳ Qisqa skan + paper buyurtma (agar tayyor bo‘lsa)…", reply_markup=kb)
        threading.Thread(target=_worker_scan, daemon=True, name="tg-paper-scan").start()
        return

    if sub in {"", "go", "trade", "buy"}:
        sub = "go"

    ticker: str | None = None
    if sub not in {"go", "trade", "buy"}:
        ticker = sub.upper()

    state_path = PROJECT_DIR / "state" / "last_telegram_scan.json"
    rows, _summary = load_last_scan_signals(state_path)
    if not rows:
        _send_html(
            token,
            chat_s,
            "Oxirgi skan yo‘q. Avval <code>/scan</code> yoki <code>/paper scan</code> yuboring.",
            reply_markup=kb,
        )
        return

    sig = pick_paper_signal(rows, ticker=ticker)
    if not sig:
        if ticker:
            msg = f"<code>{_escape_html(ticker)}</code> oxirgi skanda paper-ready emas."
        else:
            msg = "Oxirgi skanda paper-ready signal yo‘q. <code>/paper scan</code> yoki yangi <code>/scan</code>."
        _send_html(token, chat_s, msg, reply_markup=kb)
        return

    sym = str(sig.get("ticker") or ticker or "?").upper()
    label = "Paper sinov (dry-run)" if dry_run else "Paper buyurtma"
    _send_html(token, chat_s, f"⏳ {label}: <code>{_escape_html(sym)}</code>…", reply_markup=kb)

    def _worker_trade() -> None:
        try:
            _finish(execute_paper_trade(sig, repo_root=PROJECT_DIR, dry_run=dry_run))
        except Exception as exc:
            _send_html(
                token,
                chat_s,
                f"<b>Paper savdo</b> xato: <code>{_escape_html(str(exc)[:400])}</code>",
                reply_markup=kb,
            )

    threading.Thread(target=_worker_trade, daemon=True, name=f"tg-paper-{sym}").start()


def _dispatch_scalp_command(token: str, chat_s: str, remainder: str, kb: Dict[str, Any]) -> None:
    """/scalp [TICKER ...] — yfinance RVOL+gap screener, TradingView havolasi bilan."""
    from agents.yfinance_screener import format_scalp_html, screen_scalp_candidates

    tickers_override: Optional[List[str]] = None
    if remainder.strip():
        tickers_override = [t.strip().upper() for t in remainder.strip().split() if t.strip()]

    top_n = _env_int_bounded("SCALP_SCREEN_TOP_N", 8, 1, 20)
    try:
        min_rvol = max(0.5, float(os.getenv("SCALP_MIN_RVOL", "1.5")))
    except ValueError:
        min_rvol = 1.5
    try:
        min_price = max(1.0, float(os.getenv("SCALP_MIN_PRICE", "5.0")))
    except ValueError:
        min_price = 5.0

    what = f"({len(tickers_override)} ticker)" if tickers_override else "(yfinance universe)"
    _send_html(token, chat_s, f"⏳ Skalp skaner ishlamoqda {what}…", reply_markup=kb)

    def _scalp_worker() -> None:
        try:
            candidates = screen_scalp_candidates(
                universe=tickers_override,
                min_rvol=min_rvol,
                min_price=min_price,
                top_n=top_n,
                delay_sec=0.15,
            )
            _send_html(
                token,
                chat_s,
                format_scalp_html(candidates),
                reply_markup=kb,
                disable_preview=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"telegram_command_bot scalp_worker error: {exc}", flush=True)
            _send_html(
                token,
                chat_s,
                f"<b>Skalp xato</b>: <code>{_escape_html(str(exc)[:300])}</code>",
                reply_markup=kb,
            )

    threading.Thread(target=_scalp_worker, daemon=True, name="tg-scalp").start()


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
                cq = upd.get("callback_query")
                if cq:
                    print(
                        "telegram_command_bot: callback_query e’tiborsiz qoldirildi "
                        "(inline tugmalar hozircha qo‘llab-quvvatlanmaydi).",
                        flush=True,
                    )
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

                if cmd in {"scan", "scanall", "scan2b"}:
                    if not _start_scan_background(
                        token,
                        chat_s,
                        scan_lock,
                        run_all=(cmd == "scanall"),
                        scan_mode="trader2b" if cmd == "scan2b" else "default",
                    ):
                        _send_html(
                            token,
                            chat_s,
                            "Skan allaqachon ketmoqda (avto-push yoki oldingi skan). "
                            "Tugaguncha kuting yoki /status tekshiring.",
                            reply_markup=kb,
                        )
                    continue

                if cmd == "tv":
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

                if cmd == "chart":
                    sym_raw = (_remainder or "").strip().upper()
                    if not sym_raw:
                        sym_raw = os.getenv("TELEGRAM_DEFAULT_CHART_SYMBOL", "AAPL").strip().upper()
                    sym_chart = sym_raw.split(":", 1)[-1]  # NASDAQ:AAPL -> AAPL
                    _send_html(
                        token,
                        chat_s,
                        f"⏳ Grafik chizilmoqda: <code>{_escape_html(sym_chart)}</code>…",
                        reply_markup=kb,
                    )

                    def _chart_worker(sym: str = sym_chart) -> None:
                        link = _tradingview_url(sym)
                        try:
                            row = _signal_row_for_ticker(sym)
                            candles = _load_chart_candles(row, sym)
                            png = render_signal_chart(row, candles)
                            if png:
                                caption = (
                                    f"{chart_caption(row)}\n<a href=\"{link}\">TradingView</a>"
                                )
                                if _send_photo(token, chat_s, png, caption, reply_markup=kb):
                                    return
                            _send_html(
                                token,
                                chat_s,
                                (
                                    f"<b>Grafik</b> <code>{_escape_html(sym)}</code> — rasm uchun ma'lumot yo‘q "
                                    f"(avval <code>/scan</code> yoki manba ulanishini tekshiring).\n"
                                    f"<a href=\"{link}\">TradingView</a>"
                                ),
                                disable_preview=False,
                                reply_markup=kb,
                            )
                        except Exception as exc:  # noqa: BLE001
                            print(f"telegram_command_bot chart worker error: {exc}", flush=True)
                            _send_html(
                                token,
                                chat_s,
                                f"<b>Grafik xato</b>: <code>{_escape_html(str(exc)[:300])}</code>\n"
                                f"<a href=\"{link}\">TradingView</a>",
                                disable_preview=False,
                                reply_markup=kb,
                            )

                    threading.Thread(target=_chart_worker, daemon=True, name=f"tg-chart-{sym_chart}").start()
                    continue

                if cmd == "buy":
                    _dispatch_buy_command(token, chat_s, _remainder, kb)
                    continue

                if cmd == "paper":
                    _dispatch_paper_command(token, chat_s, _remainder, kb)
                    continue

                if cmd == "backtest":
                    sym_bt = _backtest_symbol_from_remainder(_remainder)
                    mode_bt = _backtest_mode_from_remainder(_remainder)
                    lookback = _env_int_bounded("TELEGRAM_BACKTEST_LOOKBACK_DAYS", 400, 120, 800)
                    horizon_bt = _env_int_bounded("BACKTEST_HORIZON_BARS", 10, 2, 60)

                    def _backtest_worker() -> None:
                        if mode_bt == "sma":
                            fast_bt = _env_int_bounded("TELEGRAM_BACKTEST_FAST_SMA", 10, 2, 200)
                            slow_bt = _env_int_bounded("TELEGRAM_BACKTEST_SLOW_SMA", 30, 3, 400)
                            if slow_bt <= fast_bt:
                                slow_bt = fast_bt + 20
                            closes_bt = daily_closes_yfinance(sym_bt, lookback)
                            if not closes_bt:
                                _send_html(token, chat_s, "<b>Backtest</b>: tarix chiqmadi.", reply_markup=kb)
                                return
                            res = sma_crossover_long_only_backtest(closes_bt, fast=fast_bt, slow=slow_bt)
                            if not res.get("ok"):
                                _send_html(
                                    token,
                                    chat_s,
                                    f"<b>Backtest</b> <code>{_escape_html(sym_bt)}</code>: ma’lumot yetarli emas.",
                                    reply_markup=kb,
                                )
                                return
                            out = (
                                f"<b>Backtest MVP (SMA)</b> <code>{_escape_html(sym_bt)}</code>\n"
                                f"Kunlar: {len(closes_bt)} · SMA {fast_bt}/{slow_bt}\n"
                                f"Strategiya jami: <b>{res.get('strategy_total_return_pct')}%</b> "
                                f"(long barlar: {res.get('bars_in_long')})\n"
                                f"Buy-hold: <b>{res.get('buy_hold_from_warmup_pct')}%</b>"
                            )
                            _send_html(token, chat_s, out, reply_markup=kb)
                            return

                        candles_bt = _load_backtest_candles(sym_bt, lookback)
                        if not candles_bt:
                            _send_html(
                                token,
                                chat_s,
                                "<b>Backtest</b>: tarix chiqmadi — IBKR Gateway yoki <code>yfinance</code> ni tekshiring.",
                                reply_markup=kb,
                            )
                            return
                        avg_win = _env_int_bounded("BACKTEST_AVG_VOL_WINDOW", 20, 5, 60)
                        trades_bt = replay_strategy(
                            candles_bt, mode_bt, ticker=sym_bt, horizon=horizon_bt, avg_window=avg_win
                        )
                        summary_bt = summarize(trades_bt)
                        _send_html(
                            token,
                            chat_s,
                            _format_strategy_backtest_html(sym_bt, mode_bt, len(candles_bt), horizon_bt, summary_bt),
                            reply_markup=kb,
                        )

                    _send_html(
                        token,
                        chat_s,
                        f"⏳ Backtest <code>{_escape_html(sym_bt)}</code> · {_escape_html(mode_bt)} hisoblanmoqda…",
                        reply_markup=kb,
                    )
                    threading.Thread(
                        target=_backtest_worker,
                        daemon=True,
                        name=f"tg-backtest-{sym_bt}",
                    ).start()
                    continue

                if cmd == "discover":
                    strat_disc = os.getenv("TELEGRAM_BACKTEST_STRATEGY", "volume_ignition").strip().lower()
                    lookback_d = _env_int_bounded("TELEGRAM_BACKTEST_LOOKBACK_DAYS", 400, 120, 800)
                    horizon_d = _env_int_bounded("BACKTEST_HORIZON_BARS", 10, 2, 60)
                    raw_tickers = os.getenv("BACKTEST_SWEEP_TICKERS", "AAPL,NVDA,TSLA,AMD,MSFT").strip()
                    tickers_d = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()][:12]

                    def _discover_worker() -> None:
                        candles_by: Dict[str, Any] = {}
                        for sym in tickers_d:
                            c = _load_backtest_candles(sym, lookback_d)
                            if c:
                                candles_by[sym] = c
                        if not candles_by:
                            _send_html(token, chat_s, "<b>Discover</b>: tarix chiqmadi.", reply_markup=kb)
                            return
                        grid = build_default_grid(strat_disc)
                        ranked = sweep_thresholds(
                            candles_by, grid, strategy_mode=strat_disc, horizon=horizon_d
                        )
                        lines = [
                            f"<b>Strategiya izlash</b> · {_escape_html(strat_disc)}",
                            f"Tickerlar: {len(candles_by)} · kombinatsiya: {len(grid)}",
                            "",
                            "<b>Top 3 sozlama (expectancy):</b>",
                        ]
                        for idx, r in enumerate(ranked[:3], start=1):
                            params = " ".join(f"{k}={v}" for k, v in (r.get("params") or {}).items())
                            lines.append(
                                f"{idx}) <code>{_escape_html(params)}</code> — "
                                f"exp <b>{r.get('expectancy_r')}R</b>, win {r.get('win_rate_pct')}%, "
                                f"n={r.get('trades')}"
                            )
                        lines.append("")
                        lines.append("<i>Eng yaxshisini .env ga qo‘ying. O‘tmish — kafolat emas.</i>")
                        _send_html(token, chat_s, "\n".join(lines), reply_markup=kb)

                    _send_html(token, chat_s, "⏳ Strategiya izlanmoqda (sweep)…", reply_markup=kb)
                    threading.Thread(target=_discover_worker, daemon=True, name="tg-discover").start()
                    continue

                if cmd == "scalp":
                    _dispatch_scalp_command(token, chat_s, _remainder, kb)
                    continue

                _send_html(
                    token,
                    chat_s,
                    "Noma’lum buyruq. /help uchun ro’yxat.",
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
