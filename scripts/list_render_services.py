#!/usr/bin/env python3
"""Render hisobidagi servislar — `srv-...` ID lar (`.env` da RENDER_API_KEY kerak).

Dashboarddagi `ws-...` — Workspace ID; deploy/tirgak uchun **SERVICE** ID `srv-...` kerak.

  python scripts/list_render_services.py
  python scripts/list_render_services.py --name us-stock
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402

LIST_URL = "https://api.render.com/v1/services"


def _iter_service_dicts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("service", "services", "items"):
            block = payload.get(key)
            if isinstance(block, list):
                return [x for x in block if isinstance(x, dict)]
    return []


def main() -> int:
    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)

    parser = argparse.ArgumentParser(description="List Render services (ids like srv-...).")
    parser.add_argument("--name", default="", help="Filter by substring in service name")
    ns = parser.parse_args()

    key = os.getenv("RENDER_API_KEY", "").strip()
    if not key:
        print(
            "RENDER_API_KEY bo‘sh — Render Dashboard → Account Settings → API Keys.\n"
            "`.env`: RENDER_API_KEY=rnd_... (repoga commit qilmang).",
            file=sys.stderr,
        )
        return 1

    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    name_filter = ns.name.strip().lower()
    collected: list[dict[str, str]] = []
    cursor: str | None = None

    try:
        for _ in range(100):
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            response = requests.get(LIST_URL, headers=headers, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
            batch = _iter_service_dicts(payload)

            for item in batch:
                sid = str(item.get("id") or "")
                if not sid.startswith("srv-"):
                    continue
                name = str(item.get("name") or "")
                if name_filter and name_filter not in name.lower():
                    continue
                stype = str(item.get("type") or "")
                collected.append({"id": sid, "name": name, "type": stype})

            next_c: str | None = None
            if isinstance(payload, dict):
                c = payload.get("cursor")
                if isinstance(c, str) and c:
                    next_c = c
            if not next_c or next_c == cursor or not batch:
                break
            cursor = next_c

    except requests.RequestException as exc:
        print(f"API xato: {exc}", file=sys.stderr)
        return 2

    if not collected:
        print("Servis topilmadi (API bo‘sh yoki filtr mos emas).")
        return 0

    print("--- srv-... (RENDER_SERVICE_ID uchun) ---\n")
    for row in sorted(collected, key=lambda r: r["name"].lower()):
        print(f"{row['id']}\t{row['name']}\t{row['type']}")

    print("\n--- `.env` namuna (render.yaml dagi servis nomlari) ---")
    by_name = {r["name"]: r["id"] for r in collected}
    for want in ("us-stock-rvol-dashboard", "us-stock-rvol-telegram-bot"):
        if want in by_name:
            label = "RENDER_SERVICE_ID" if "dashboard" in want else "RENDER_WORKER_SERVICE_ID"
            print(f"{label}={by_name[want]}   # {want}")
    if "us-stock-rvol-dashboard" not in by_name and collected:
        print(f"# Dashboard aniqlanmadi — yuqoridagi ro‘yxatdan mos srv ni tanlang.")
        print(f"RENDER_SERVICE_ID={collected[0]['id']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
