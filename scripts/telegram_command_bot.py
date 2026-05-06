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

import requests

# Repo root: …/us-stock-rvol-agents/
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("PROJECT_ROOT", str(PROJECT_DIR))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402
from agents.scan_pipeline import (  # noqa: E402
    _env_int_bounded,
    fetch_universe_for_scan,
    run_scan_market,
    telegram_default_controls,
)
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


def _send_html(token: str, chat_id: str, text: str) -> None:
    chunks: List[str] = []
    t = text
    while len(t) > MAX_MESSAGE_LEN:
        chunks.append(t[:MAX_MESSAGE_LEN])
        t = t[MAX_MESSAGE_LEN:]
    if t:
        chunks.append(t)
    for c in chunks:
        try:
            requests.post(
                f"{TG_API}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": c,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
        except requests.RequestException:
            pass


def _escape_html(s: Any) -> str:
    text = "" if s is None else str(s)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_signal_line(row: Dict[str, Any]) -> str:
    t = _escape_html(row.get("ticker", "?"))
    score = row.get("score", 0)
    strat = _escape_html(row.get("strategy_name", ""))
    dec = _escape_html(row.get("chatgpt_decision", "") or "—")
    return f"• <code>{t}</code> · {score} · {dec} · {strat}"


def _persist_last_scan(
    *,
    ranked: List[Dict[str, Any]],
    summary: Dict[str, Any],
    universe_size: int,
) -> None:
    state_dir = PROJECT_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    top_n = _env_int_bounded("TELEGRAM_BOT_TOP_ROWS", 12, 5, 25)
    payload = {
        "saved_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "universe_size": universe_size,
        "summary": summary,
        "top_signals": ranked[:top_n],
    }
    path = state_dir / "last_telegram_scan.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


_help_text = """<b>Mavjud buyruqlar</b>
/start yoki /help — yordam
/scan — to‘liq skan (dashboard bilan bir xil konveyer)
/signals — oxirgi /scan ning qisqa natijasi (agar saqlangan bo‘lsa)
/paper — hozircha stub (Alpaca paper keyin ulanadi)
/backtest [TICKER] — oddiy SMA crossover MVP (yahoo kunlik; misol: <code>/backtest AAPL</code>)

<i>Ma’lumot:</i> narh/volume va intraday barlar odatda Alpaca → Polygon → Yahoo (yfinance,
kalit shart emas) tartibida tortiladi; Polygon cheklovi bo‘lsa
<code>INTRADAY_YAHOO_BEFORE_POLYGON=true</code> bilan intradayda Yahoo avval sinanadi."""


def main() -> None:
    ensure_env_file(PROJECT_DIR)
    load_project_env(PROJECT_DIR)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is required.", file=sys.stderr)
        sys.exit(1)

    allowed = _parse_allowed_chat_ids()

    skip_wh = os.getenv("TELEGRAM_SKIP_DELETE_WEBHOOK", "").strip().lower() in {"1", "true", "yes", "on"}
    if not skip_wh:
        _delete_webhook_for_long_poll(token)

    scan_lock = threading.Lock()

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
                continue

            text = (msg.get("text") or "").strip()
            cmd, _remainder = _command_from_text(text)
            cmd = cmd.lower()

            if cmd in {"", "start", "help"}:
                _send_html(token, chat_s, _help_text)
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
                    f"Pass+AI: {summary.get('eligible_signals', '—')} / {summary.get('tickers_scanned', '—')}\n",
                ]
                for r in rows[:10]:
                    lines.append(_format_signal_line(r) + "\n")
                _send_html(token, chat_s, "".join(lines))
                continue

            if cmd == "scan":
                if not scan_lock.acquire(blocking=False):
                    _send_html(token, chat_s, "Skan allaqachon ketmoqda, biroz kuting.")
                    continue
                try:
                    _send_html(token, chat_s, "Skan boshlandi…")

                    ctrls = telegram_default_controls()
                    tickers = fetch_universe_for_scan(ctrls)

                    ranked, _views, summary = run_scan_market(
                        tickers,
                        ctrls,
                        repo_root=PROJECT_DIR,
                        progress=None,
                    )

                    _persist_last_scan(
                        ranked=ranked,
                        summary=summary,
                        universe_size=len(tickers),
                    )

                    lines = [
                        "<b>Skan yakunlandi</b>\n",
                        f"Desk: {_escape_html(summary.get('desk_label'))} · ",
                        f"Preset: {_escape_html(summary.get('scan_preset'))}\n",
                        f"Tickers: {summary.get('tickers_scanned')} · ",
                        f"eligible (strategy+AI): {summary.get('eligible_signals')}\n",
                        "<b>Top</b>\n",
                    ]
                    top_n = _env_int_bounded("TELEGRAM_BOT_REPLY_TOP_N", 8, 3, 15)
                    for r in ranked[:top_n]:
                        lines.append(_format_signal_line(r) + "\n")
                    _send_html(token, chat_s, "".join(lines))
                finally:
                    scan_lock.release()
                continue

            if cmd == "paper":
                _send_html(
                    token,
                    chat_s,
                    f"<code>/{cmd}</code> — hozircha keyingi fazada ulanadi.",
                )
                continue

            if cmd == "backtest":
                sym = remainder.strip().upper() or os.getenv("TELEGRAM_BACKTEST_TICKER", "SPY").strip().upper()
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


if __name__ == "__main__":
    main()
