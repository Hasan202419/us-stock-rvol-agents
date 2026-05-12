"""Long-poll Telegram bot: /scan uses agents.scan_pipeline (same path as dashboard)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

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
from agents.simple_backtest_mvp import (  # noqa: E402
    daily_closes_yfinance,
    sma_crossover_long_only_backtest,
)

TG_API = "https://api.telegram.org"
MAX_MESSAGE_LEN = 3800


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


def _send_html(token: str, chat_id: str, text: str, *, disable_preview: bool = True) -> None:
    chunks: List[str] = []
    t = text
    while len(t) > MAX_MESSAGE_LEN:
        chunks.append(t[:MAX_MESSAGE_LEN])
        t = t[MAX_MESSAGE_LEN:]
    if t:
        chunks.append(t)
    for c in chunks:
        try:
            response = requests.post(
                f"{TG_API}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": c,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": disable_preview,
                },
                timeout=30,
            )
            if not response.ok:
                print(f"telegram_command_bot sendMessage error: {response.status_code} {response.text[:300]}", flush=True)
        except requests.RequestException as exc:
            print(f"telegram_command_bot sendMessage request failed: {exc}", flush=True)


def _escape_html(s: Any) -> str:
    text = "" if s is None else str(s)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_signal_line(row: Dict[str, Any]) -> str:
    t = _escape_html(row.get("ticker", "?"))
    score = row.get("score", 0)
    strat = _escape_html(row.get("strategy_name", ""))
    dec = _escape_html(row.get("chatgpt_decision", "") or "—")
    paper_ready = bool(row.get("paper_trade_ready"))
    status = "🟢 READY" if paper_ready else "🟡 WATCH"
    tv = _tradingview_url(t)
    return (
        f"• <code>{t}</code> · {status} · score:{score} · {dec} · {strat} · "
        f"<a href=\"{tv}\">TradingView</a>"
    )


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
    top_n = _env_int_bounded("TELEGRAM_BOT_TOP_ROWS", 6, 5, 25)
    payload = {
        "saved_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "universe_size": universe_size,
        "summary": summary,
        "top_signals": ranked[:top_n],
    }
    path = state_dir / "last_telegram_scan.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _telegram_reply_top_n() -> int:
    return _env_int_bounded("TELEGRAM_BOT_REPLY_TOP_N", 6, 3, 15)


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
) -> None:
    """Skan → state → HTML xabar ( /scan va fon push uchun umumiy yo‘l )."""

    start_msg = "Keng qamrovli skan boshlandi…" if run_all else "Skan boshlandi…"
    if heading_html:
        _send_html(token, chat_s, f"{heading_html}\n{start_msg}")
    else:
        _send_html(token, chat_s, start_msg)

    ctrls = telegram_default_controls()
    if run_all:
        max_all = _env_int_bounded("TELEGRAM_MAX_SYMBOLS_ALL", 1200, 200, 5000)
        ctrls = SidebarControls(
            desk_label=f"{ctrls.desk_label} all-us",
            max_symbols=max_all,
            preset_name=ctrls.preset_name,
            rvol_thresholds=dict(ctrls.rvol_thresholds),
            max_workers=ctrls.max_workers,
            finviz_csv_universe=ctrls.finviz_csv_universe,
        )
    tickers = fetch_universe_for_scan(ctrls)

    prev_alert_on_scan = os.environ.get("TELEGRAM_ALERT_ON_SCAN")
    os.environ["TELEGRAM_ALERT_ON_SCAN"] = "false"
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

    _persist_last_scan(ranked=ranked, summary=summary, universe_size=len(tickers))

    lines = [
        "<b>Skan yakunlandi</b>\n",
        f"Desk: {_escape_html(summary.get('desk_label'))} · ",
        f"Preset: {_escape_html(summary.get('scan_preset'))}\n",
        f"Tickers: {summary.get('tickers_scanned')} · ",
        f"eligible (strategy+AI): {summary.get('eligible_signals')} · ",
        f"paper-ready: {summary.get('paper_ready_signals', '—')}\n",
        "<b>Top</b>\n",
    ]
    top_n = _telegram_reply_top_n()
    for r in ranked[:top_n]:
        lines.append(_format_signal_line(r) + "\n")
    top_failed = summary.get("top_failed_rules") or []
    if top_failed:
        rendered = ", ".join(f"{name}:{count}" for name, count in top_failed[:3])
        lines.append(f"Sabab top-qoidalar: {rendered}\n")
    src_summary = summary.get("provider_source_summary") or {}
    quote_mix = src_summary.get("quote") if isinstance(src_summary, dict) else {}
    if isinstance(quote_mix, dict) and quote_mix:
        mix_txt = ", ".join(f"{k}:{v}" for k, v in list(quote_mix.items())[:3])
        lines.append(f"Quote manbalari: {mix_txt}\n")
    if not ranked:
        lines.append(
            "— Hozircha mos signal yo‘q. Bozor sust bo‘lishi mumkin; keyinroq qayta /scan qiling.\n"
        )
    _send_html(token, chat_s, "".join(lines))


def _auto_push_loop(token: str, chat_id: str, scan_lock: threading.Lock) -> None:
    """Kunlik/interval: bir xil skan natijasini chatga yuborish (Babir uslubi)."""

    interval_min = _env_int_bounded("TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES", 1440, 15, 10080)
    use_scanall = _truthy_env("TELEGRAM_AUTO_PUSH_USE_SCANALL", default=False)
    first_delay_sec = max(30, _env_int_bounded("TELEGRAM_AUTO_PUSH_FIRST_DELAY_SEC", 120, 30, 3600))
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
        if not scan_lock.acquire(blocking=False):
            print("telegram_command_bot: auto-push — skan band, keyingi safarga qoldirildi", flush=True)
            time.sleep(60)
            continue
        try:
            _execute_scan_send_persist(
                token,
                chat_id,
                run_all=use_scanall,
                heading_html="<b>Avtomatik market skani</b> <i>(Babir uslubi)</i>",
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
        time.sleep(interval_min * 60)


_help_text = """<b>Mavjud buyruqlar</b>
/start yoki /help — yordam
/scan — to‘liq skan (dashboard bilan bir xil konveyer)
/scanall — kattaroq qamrov (TELEGRAM_MAX_SYMBOLS_ALL dan oladi)
/signals — oxirgi /scan ning qisqa natijasi (agar saqlangan bo‘lsa; worker restart/deploydan keyin yo‘qolishi mumkin)
<i>Avtomatik push:</i> <code>TELEGRAM_AUTO_PUSH_ENABLED=true</code> + <code>TELEGRAM_CHAT_ID</code> — har
<code>TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES</code> daqiqada (default 1440 ≈ kuniga 1 marta) top ~6 ticker yuboriladi.
/tv [TICKER] — TradingView chart link (misol: <code>/tv AAPL</code> yoki <code>/tv NYSE:IBM</code>)
/status — bot/worker holati va env diagnostika
/risk — paper risk limitlari (tez ko‘rish)
/paper — hozircha stub (Alpaca paper keyin ulanadi)
/backtest [TICKER] — oddiy SMA crossover MVP (yahoo kunlik; misol: <code>/backtest AAPL</code>)

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
    return (
        "<b>Bot status</b>\n"
        f"TRADING_MODE: <code>{_escape_html(trading_mode)}</code>\n"
        f"ALPACA_BASE_URL: <code>{_escape_html(base)}</code>\n"
        f"Paper config: <b>{'OK' if paper_ok else 'CHECK'}</b>\n"
        f"Alpaca keys: <b>{'OK' if key_ok else 'MISSING'}</b>\n"
        f"Telegram token: <b>{'OK' if tg_key_ok else 'MISSING'}</b>\n"
        f"TELEGRAM_AUTO_PUSH_ENABLED: <code>{_escape_html(ap_en)}</code> · interval_min: <code>{_escape_html(ap_iv)}</code> · scanall: <code>{_escape_html(ap_sa)}</code>\n"
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
            cmd, _remainder = _command_from_text(text)
            cmd = cmd.lower()
            try:
                if cmd in {"", "start", "help"}:
                    _send_html(token, chat_s, _help_text)
                    continue

                if cmd == "status":
                    _send_html(token, chat_s, _status_html())
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
                    _send_html(token, chat_s, risk_msg)
                    continue

                if cmd == "signals":
                    path = PROJECT_DIR / "state" / "last_telegram_scan.json"
                    if not path.is_file():
                        _send_html(token, chat_s, "Hali skan yozuvi yo‘q. Avval /scan ishga tushiring.")
                        continue
                    try:
                        blob = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        _send_html(token, chat_s, "last_telegram_scan.json bo‘sh yoki nosoz.")
                        continue
                    summary = blob.get("summary") or {}
                    rows = blob.get("top_signals") or []
                    lines = [
                        f"<b>Oxirgi skan</b> ({blob.get('saved_at_utc', '')})\n",
                        f"Universe: {blob.get('universe_size', '—')} · ",
                        f"Pass+AI: {summary.get('eligible_signals', '—')} / {summary.get('tickers_scanned', '—')} · ",
                        f"paper-ready: {summary.get('paper_ready_signals', '—')}\n",
                        "<b>Top signalar</b>\n",
                    ]
                    show_n = _telegram_reply_top_n()
                    for r in rows[:show_n]:
                        lines.append(_format_signal_line(r) + "\n")
                    if not rows:
                        lines.append("— Hali signal yozuvi yo‘q. Avval <code>/scan</code> yoki <code>/scanall</code> yuboring.\n")
                    _send_html(token, chat_s, "".join(lines))
                    continue

                if cmd in {"scan", "scanall"}:
                    if not scan_lock.acquire(blocking=False):
                        _send_html(token, chat_s, "Skan allaqachon ketmoqda, biroz kuting.")
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
