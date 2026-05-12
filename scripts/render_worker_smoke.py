#!/usr/bin/env python3
"""Render Telegram worker + Telegram API tez tekshiruv (.env dan).

  python scripts/render_worker_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402


def _unwrap_service(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    s = payload.get("service")
    if isinstance(s, dict):
        return s
    sid = str(payload.get("id") or "")
    return payload if sid.startswith("srv-") else {}


def _deploy_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = None
        for key in ("deploys", "items"):
            block = payload.get(key)
            if isinstance(block, list):
                raw = block
                break
        if raw is None:
            return []
    else:
        return []
    out: list[dict[str, Any]] = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        d = x.get("deploy")
        if isinstance(d, dict):
            out.append(d)
        elif str(x.get("id") or "").startswith("dep-"):
            out.append(x)
    return out


def main() -> int:
    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)

    rkey = os.getenv("RENDER_API_KEY", "").strip()
    wsid = os.getenv("RENDER_WORKER_SERVICE_ID", "").strip()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if not rkey:
        print("RENDER_API_KEY yo‘q.", file=sys.stderr)
        return 1
    if not wsid.startswith("srv-"):
        print("RENDER_WORKER_SERVICE_ID `srv-...` emas yoki bo‘sh.", file=sys.stderr)
        return 1

    h = {"Authorization": f"Bearer {rkey}", "Accept": "application/json"}
    base = "https://api.render.com/v1"

    print("--- Render worker ---")
    try:
        r = requests.get(f"{base}/services/{wsid}", headers=h, timeout=45)
        print(f"GET /services/{{id}}  HTTP {r.status_code}")
        if not r.ok:
            print(r.text[:800], file=sys.stderr)
            return 2
        svc = _unwrap_service(r.json())
        print("  name:", svc.get("name"))
        print("  type:", svc.get("type"))
        print("  suspended:", svc.get("suspended"))
        print("  branch:", svc.get("branch"))
    except requests.RequestException as e:
        print("Render xato:", e, file=sys.stderr)
        return 2

    print("\n--- Oxirgi deploy lar ---")
    try:
        r = requests.get(
            f"{base}/services/{wsid}/deploys",
            headers=h,
            params={"limit": 5},
            timeout=45,
        )
        print(f"GET /deploys  HTTP {r.status_code}")
        if r.ok:
            rows = _deploy_rows(r.json())
            for d in rows[:5]:
                did = d.get("id", "")
                st = d.get("status", "")
                finished = d.get("finishedAt") or d.get("updatedAt") or ""
                print(f"  {did}  {st}  {finished}")
            if not rows:
                print("  (deploy ro‘yxati bo‘sh yoki format boshqacha)")
        else:
            print(r.text[:600], file=sys.stderr)
    except requests.RequestException as e:
        print("Deploys xato:", e, file=sys.stderr)

    print("\n--- Telegram ---")
    if not token:
        print("  TELEGRAM_BOT_TOKEN yo‘q — o‘tkazildi.")
        return 0
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
        data = r.json() if r.ok else {}
        ok = data.get("ok")
        me = data.get("result") or {}
        print(f"  getMe  HTTP {r.status_code}  ok={ok}  @{me.get('username', '?')}")
    except requests.RequestException as e:
        print("  getMe xato:", e)
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=20)
        data = r.json() if r.ok else {}
        info = data.get("result") or {}
        url = info.get("url") or ""
        print(f"  getWebhookInfo  HTTP {r.status_code}  url={'(bo‘sh — polling OK)' if not url else url[:60]}")
    except requests.RequestException as e:
        print("  getWebhookInfo xato:", e)

    print("\n[OK] Tekshiruv tugadi — botda /help yuborib ko‘ring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
