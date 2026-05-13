#!/usr/bin/env python3
"""`us-stock-rvol-telegram-bot` Background Worker ni Render da yaratish / env ni sinxronlash.

Talablar (`.env` da):
  RENDER_API_KEY=rnd_...
  `load_project_env` Telegram + AI + market uchun kerak bo'lgan kalitlarni yuklaydi.

Ishlatish:

  python scripts/ensure_render_telegram_worker.py           # mavjud bo'lsa env yangilash (+ lokal `.env` ga OWNER/WORKER_ID)
  python scripts/ensure_render_telegram_worker.py --dry-run # faqat tekshirish
  python scripts/ensure_render_telegram_worker.py --no-local-env-write  # faqat Render env; `.env` faylni tegmasin

Servis mavjud bo'lmasa, POST /v1/services bilan `background_worker` yaratadi va keyin
PUT /v1/services/{id}/env-vars (JSON massiv: `key` / `value`) bilan `.env` dagi ishchi kalitlarni yozadi.

Kalit qiymatlari stdout ga chiqmaydi (faqat status).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402
from agents.render_api_parse import iter_owner_dicts, iter_service_dicts, next_cursor_from_page  # noqa: E402

API_BASE = "https://api.render.com/v1"
REPO = "https://github.com/Hasan202419/us-stock-rvol-agents"
SERVICE_NAME = "us-stock-rvol-telegram-bot"


# render.yaml (worker) va skan pipeline uchun kerak bo'lgan o'zgaruvchilar bo'yicha to'plam.
_WORKER_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "POLYGON_API_KEY",
    "MASSIVE_API_KEY",
    "YAHOO_FINANCE_ENABLED",
    "INTRADAY_YAHOO_BEFORE_POLYGON",
    "ALPHA_VANTAGE_API_KEY",
    "ALPHA_VANTAGE_ENABLED",
    "OPENAI_ANALYSIS_MAX_RETRIES",
    "OPENAI_ANALYSIS_RETRY_BASE_SEC",
    "FINNHUB_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_BASE_URL",
    "ALPACA_DATA_FEED",
    "TRADING_MODE",
    "DATA_DELAY_MINUTES",
    "MARKET_DATA_PROVIDER_PRIORITY",
    "MARKET_HTTP_MAX_RETRIES",
    "MARKET_HTTP_BACKOFF_BASE_SEC",
    "STRATEGY_MODE",
    "SCAN_AI_INCLUDE_FAILS",
    "ANALYST_TRADE_PLAN_ENABLED",
    "ANALYST_TRADE_PLAN_LANG",
    "SCAN_MAX_WORKERS",
    "INTRADAY_TIMEFRAME_MINUTES",
    "INTRADAY_LOOKBACK_DAYS",
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "TELEGRAM_ALERT_ON_SCAN",
    "TELEGRAM_ALERT_TOP_N",
    "TELEGRAM_ALERTS_ENABLED",
    "TELEGRAM_BOT_REPLY_TOP_N",
    "TELEGRAM_BOT_TOP_ROWS",
    "TELEGRAM_AUTO_PUSH_ENABLED",
    "TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES",
    "TELEGRAM_AUTO_PUSH_CHAT_ID",
    "TELEGRAM_AUTO_PUSH_USE_SCANALL",
    "TELEGRAM_AUTO_PUSH_FIRST_DELAY_SEC",
    "TELEGRAM_AUTO_PUSH_AT",
    "TELEGRAM_AUTO_PUSH_TZ",
    "SCAN_EMPTY_WATCHLIST_TOP_N",
    "SCAN_SHOW_WATCHLIST_ON_EMPTY",
    "TELEGRAM_SCAN_PRESET",
    "TELEGRAM_FORCE_EXPLORER",
    "TELEGRAM_MAX_SYMBOLS",
    "TELEGRAM_MAX_SYMBOLS_ALL",
    "TELEGRAM_DESK_LABEL",
    "TELEGRAM_USE_FINVIZ_CSV",
    "TELEGRAM_SKIP_DELETE_WEBHOOK",
    "AI_PROVIDER",
    "FMP_API_KEY",
    "NEWSAPI_KEY",
    "ZOYA_API_KEY",
    "ZOYA_ENABLED",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "FINVIZ_ELITE_AUTH",
    "FINVIZ_ELITE_EXPORT_QUERY",
    "FINVIZ_ELITE_EXPORT_BASE",
    "FETCH_UNIVERSE_FINVIZ_FIRST",
    "HALAL_MAX_DEBT_RATIO",
    "HALAL_MAX_IMPURE_REV",
    "HALAL_MAX_CASH_RATIO",
    "PROP_FIRM_NAME",
    "PROP_PLAN_ADVANCED_USD",
    "PROP_BUYING_POWER_USD",
    "PROP_PROFIT_TARGET_USD",
    "PROP_PROFIT_TARGET_PCT",
    "PROP_DAILY_MAX_LOSS_USD",
    "PROP_MAX_DRAWDOWN_USD",
    "PROP_MAX_DRAWDOWN_PCT",
    "PROP_CONSISTENCY_MIN_PCT",
    "PROP_MIN_ROUND_TRADES",
)


def _list_all_services(headers: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(50):
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{API_BASE}/services", headers=headers, params=params, timeout=60)
        r.raise_for_status()
        payload = r.json()
        batch = iter_service_dicts(payload)
        out.extend(batch)
        next_c = next_cursor_from_page(payload)
        if not next_c or next_c == cursor or not batch:
            break
        cursor = next_c
    return out


def _find_worker(services: list[dict[str, Any]]) -> dict[str, Any] | None:
    for s in services:
        if str(s.get("type") or "") != "background_worker":
            continue
        if str(s.get("name") or "") != SERVICE_NAME:
            continue
        if str(s.get("repo") or "").rstrip("/") != REPO.rstrip("/"):
            continue
        return s
    return None


def _list_all_owners(headers: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(50):
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{API_BASE}/owners", headers=headers, params=params, timeout=60)
        r.raise_for_status()
        payload = r.json()
        batch = iter_owner_dicts(payload)
        out.extend(batch)
        next_c = next_cursor_from_page(payload)
        if not next_c or next_c == cursor or not batch:
            break
        cursor = next_c
    return out


def _workspace_id_from_owner_row(row: dict[str, Any]) -> str | None:
    for key in ("id", "ownerId"):
        oid = str(row.get(key) or "").strip()
        if oid.startswith("tea-"):
            return oid
    ws = row.get("workspace")
    if isinstance(ws, dict):
        for key in ("id", "ownerId"):
            oid = str(ws.get(key) or "").strip()
            if oid.startswith("tea-"):
                return oid
    return None


def _upsert_dotenv_scalar(env_path: Path, key: str, value: str) -> bool:
    """`KEY=value` ni `.env` da qatori topilsa yangilaydi, bo'lmasa fayl oxiriga qo'shadi."""

    if value == "":
        return False
    if not env_path.is_file():
        return False
    try:
        raw = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return False
    line_re = re.compile(rf"^\s*{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}\n"
    if line_re.search(raw):
        updated = line_re.sub(new_line.rstrip("\n"), raw, count=1)
    else:
        sep = "" if raw.endswith("\n") or raw == "" else "\n"
        block = f"{sep}# set by scripts/ensure_render_telegram_worker.py\n{new_line}"
        updated = raw + block
    try:
        env_path.write_text(updated, encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True


def _resolve_owner_id(headers: dict[str, str], services: list[dict[str, Any]]) -> str | None:
    explicit = os.getenv("RENDER_OWNER_ID", "").strip()
    if explicit:
        return explicit
    for s in services:
        oid = str(s.get("ownerId") or "").strip()
        if oid.startswith("tea-"):
            return oid
    try:
        owners = _list_all_owners(headers)
    except requests.RequestException:
        owners = []
    if len(owners) == 1:
        got = _workspace_id_from_owner_row(owners[0])
        if got:
            return got
    for row in owners:
        got = _workspace_id_from_owner_row(row)
        if got:
            return got
    return None


def _build_add_env() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    py_ver = os.getenv("PYTHON_VERSION", "").strip() or "3.12.8"
    rows.append({"key": "PYTHON_VERSION", "value": py_ver})
    for key in _WORKER_ENV_KEYS:
        raw = os.getenv(key)
        if raw is None:
            continue
        val = str(raw).strip()
        if val == "":
            continue
        rows.append({"key": key, "value": val})

    # Worker skan rejimi uchun qat'iy override: lokal `.env`da eski qiymat bo'lsa ham Renderda Explorer ishlasin.
    forced_defaults = {
        "TELEGRAM_SCAN_PRESET": "Explorer",
        "TELEGRAM_FORCE_EXPLORER": "true",
        "TELEGRAM_MAX_SYMBOLS": "0",
        "TELEGRAM_MAX_SYMBOLS_ALL": "0",
        "MARKET_DATA_PROVIDER_PRIORITY": "polygon,alpaca,yahoo,finnhub,alpha_vantage",
        # Finviz filter tor bo'lib qolsa universe 3-4 tickerga tushib ketmasligi uchun default o'chiriladi.
        "FETCH_UNIVERSE_FINVIZ_FIRST": "false",
        "TELEGRAM_USE_FINVIZ_CSV": "false",
        "SCAN_RELAX_ON_EMPTY": "true",
        "TELEGRAM_BOT_REPLY_TOP_N": "10",
        "TELEGRAM_BOT_TOP_ROWS": "10",
        "TELEGRAM_ALERT_TOP_N": "10",
        "SCAN_EMPTY_WATCHLIST_TOP_N": "10",
        # Babir uslubi: worker fonida muntazam skan + ~6 ta ticker (chat: TELEGRAM_CHAT_ID yoki TELEGRAM_AUTO_PUSH_CHAT_ID .env dan).
        "TELEGRAM_AUTO_PUSH_ENABLED": "true",
        "TELEGRAM_AUTO_PUSH_INTERVAL_MINUTES": "1440",
        "TELEGRAM_AUTO_PUSH_FIRST_DELAY_SEC": "120",
        "TELEGRAM_AUTO_PUSH_USE_SCANALL": "true",
        "SCAN_MAX_WORKERS": "12",
    }
    rows_by_key: dict[str, dict[str, str]] = {r["key"]: r for r in rows}
    for k, v in forced_defaults.items():
        rows_by_key[k] = {"key": k, "value": v}
    rows = list(rows_by_key.values())
    return rows


def _patch_env(service_id: str, headers: dict[str, str], dry_run: bool) -> None:
    add = _build_add_env()
    if not add:
        print("env-vars: `.env` da worker uchun yoziladigan kalitlar yo'q.")
        return
    if dry_run:
        print(f"env-vars (--dry-run): {len(add)} ta kalit yuborilardi.")
        return
    url = f"{API_BASE}/services/{service_id}/env-vars"
    r = requests.put(url, headers={**headers, "Content-Type": "application/json"}, json=add, timeout=120)
    if r.status_code >= 400:
        wrapped = [{"key": row["key"], "value": row["value"]} for row in add]
        payload_alt = {"envVars": wrapped}
        r2 = requests.put(url, headers={**headers, "Content-Type": "application/json"}, json=payload_alt, timeout=120)
        if r2.status_code < 400:
            print(f"env-vars: PUT ok (envVars obl) — {len(add)} kalit.")
            return
        try:
            err = r.json()
        except Exception:
            err = r.text[:1200]
        print(f"env-vars PUT xato http {r.status_code}: {err}", file=sys.stderr)
        raise SystemExit(3)
    print(f"env-vars: PUT ok — {len(add)} kalit yozildi/yangilandi.")


def _create_worker(owner_id: str, headers: dict[str, str], dry_run: bool) -> str:
    payload: dict[str, Any] = {
        "type": "background_worker",
        "name": SERVICE_NAME,
        "ownerId": owner_id,
        "repo": REPO,
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "python",
            "runtime": "python",
            "plan": "starter",
            "region": "oregon",
            "envSpecificDetails": {
                "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
                "startCommand": "python scripts/telegram_command_bot.py",
            },
        },
    }
    if dry_run:
        print("--dry-run: worker yaratilardi (POST /v1/services).")
        return "dry-run-srv"
    r = requests.post(
        f"{API_BASE}/services",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if r.status_code not in (200, 201):
        try:
            err = r.json()
        except Exception:
            err = r.text[:2000]
        print(f"POST /services xato http {r.status_code}: {err}", file=sys.stderr)
        raise SystemExit(4)
    data = r.json()
    sid = str(data.get("id") or data.get("service", {}).get("id") or "")
    if not sid.startswith("srv-"):
        print(f"Javobda service id topilmadi: {json.dumps(data)[:500]}", file=sys.stderr)
        raise SystemExit(5)
    print(f"worker yaratildi: {sid}")
    return sid


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Render Telegram background worker exists and env is synced.")
    parser.add_argument("--dry-run", action="store_true", help="Create/env patch qilmasin")
    parser.add_argument(
        "--no-local-env-write",
        action="store_true",
        help="`.env` ga RENDER_OWNER_ID / RENDER_WORKER_SERVICE_ID yozmasin (faqat stdout)",
    )
    ns = parser.parse_args()

    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)
    env_path = _PROJECT_ROOT / ".env"
    had_explicit_owner = bool(os.getenv("RENDER_OWNER_ID", "").strip())

    key = os.getenv("RENDER_API_KEY", "").strip()
    if not key:
        print("RENDER_API_KEY bo'sh — `.env` da Render API kalitini qo'ying.", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    services = _list_all_services(headers)
    worker = _find_worker(services)
    owner = _resolve_owner_id(headers, services)
    if not owner:
        print(
            "ownerId aniqlanmadi:\n"
            "  • `.env` ga qo‘ying: RENDER_OWNER_ID=tea-... (Dashboard → Team → Settings → Workspace ID)\n"
            "  • yoki Render API `/v1/owners` javobiga qarab avto-topish muvaffaqiyatsiz (kalit ruhsati / tarmoq).",
            file=sys.stderr,
        )
        return 2

    if worker:
        sid = str(worker["id"])
        print(f"mavjud worker: {sid} ({SERVICE_NAME})")
        _patch_env(sid, headers, ns.dry_run)
        if not ns.dry_run and not ns.no_local_env_write:
            if not had_explicit_owner and _upsert_dotenv_scalar(env_path, "RENDER_OWNER_ID", owner):
                os.environ["RENDER_OWNER_ID"] = owner
                print("lokal `.env`: RENDER_OWNER_ID API dan yozildi.")
            if _upsert_dotenv_scalar(env_path, "RENDER_WORKER_SERVICE_ID", sid):
                os.environ["RENDER_WORKER_SERVICE_ID"] = sid
                print("lokal `.env`: RENDER_WORKER_SERVICE_ID yangilandi.")
        print("")
        print("--- xulosa ---")
        print(f"RENDER_WORKER_SERVICE_ID={sid}")
        return 0

    print(f"worker topilmadi — yaratiladi: {SERVICE_NAME}")
    sid_new = _create_worker(owner, headers, ns.dry_run)
    if not ns.dry_run:
        _patch_env(sid_new, headers, dry_run=False)
        if not ns.no_local_env_write:
            if not had_explicit_owner and _upsert_dotenv_scalar(env_path, "RENDER_OWNER_ID", owner):
                os.environ["RENDER_OWNER_ID"] = owner
                print("lokal `.env`: RENDER_OWNER_ID API dan yozildi.")
            if _upsert_dotenv_scalar(env_path, "RENDER_WORKER_SERVICE_ID", sid_new):
                os.environ["RENDER_WORKER_SERVICE_ID"] = sid_new
                print("lokal `.env`: RENDER_WORKER_SERVICE_ID yangilandi.")
    print("")
    print("--- xulosa ---")
    print(f"RENDER_WORKER_SERVICE_ID={sid_new}")
    deploy_url = (
        "https://dashboard.render.com/worker/"
        + (sid_new if sid_new.startswith("srv-") else "")
    )
    if sid_new.startswith("srv-"):
        print(f"Dashboard: {deploy_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
