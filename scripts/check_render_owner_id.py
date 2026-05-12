#!/usr/bin/env python3
"""Render `/v1/owners` va servislar orqali workspace ID (`tea-...`) ni tekshiradi.

`.env`: RENDER_API_KEY (majburiy), RENDER_OWNER_ID (ixtiyoriy — moslik tekshiriladi).

  python scripts/check_render_owner_id.py
  python scripts/check_render_owner_id.py --debug   # /v1/owners birinchi javob (JSON)
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
from agents.render_api_parse import iter_owner_dicts, iter_service_dicts, next_cursor_from_page  # noqa: E402

API_BASE = "https://api.render.com/v1"


def _owners_first_page_raw(headers: dict[str, str]) -> tuple[Any, int]:
    r = requests.get(
        f"{API_BASE}/owners",
        headers=headers,
        params={"limit": 100},
        timeout=60,
    )
    return r.json(), r.status_code


def _list_all_owners(headers: dict[str, str], first_payload: Any | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    first = True
    for _ in range(50):
        if first and first_payload is not None:
            payload = first_payload
            first = False
        else:
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


def _tea_from_row(row: dict[str, Any]) -> str | None:
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


def _workspace_rows(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for row in rows:
        oid = _tea_from_row(row)
        if not oid:
            continue
        name = str(row.get("name") or row.get("email") or "").strip()
        out.append((oid, name))
    return out


def _summarize_payload(payload: Any, max_len: int = 3500) -> str:
    try:
        import json as _json

        raw = _json.dumps(payload, indent=2, ensure_ascii=False)
    except Exception:
        raw = repr(payload)
    return raw if len(raw) <= max_len else raw[:max_len] + "\n…"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Tekshiruv: Render RENDER_OWNER_ID va /v1/owners")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Birinchi /v1/owners javobining JSON namunasini chiqaradi (maxfiy kalit emas)",
    )
    ns = parser.parse_args()

    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)

    key = os.getenv("RENDER_API_KEY", "").strip()
    configured = os.getenv("RENDER_OWNER_ID", "").strip()

    if not key:
        print(
            "RENDER_API_KEY bo‘sh — `.env` da Render API kaliti kerak.",
            file=sys.stderr,
        )
        return 1

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    print("RENDER_OWNER_ID (.env):", configured if configured else "(qo‘yilmagan)")
    print()

    # --- /v1/owners
    first_owner_payload: Any | None = None
    try:
        raw_page, st = _owners_first_page_raw(headers)
        if st >= 400:
            print(f"GET /v1/owners — HTTP {st}", file=sys.stderr)
            print(_summarize_payload(raw_page, 1200), file=sys.stderr)
            return 2
        first_owner_payload = raw_page
        owner_rows = _list_all_owners(headers, first_payload=first_owner_payload)
    except requests.RequestException as e:
        print("GET /v1/owners — xato:", e, file=sys.stderr)
        if getattr(e, "response", None) is not None:
            r = e.response
            print("  HTTP", getattr(r, "status_code", "?"), file=sys.stderr)
            try:
                print("  ", r.text[:500], file=sys.stderr)
            except Exception:
                pass
        return 2

    if ns.debug and first_owner_payload is not None:
        print("--- --debug: birinchi sahifa /v1/owners (truncated) ---")
        print(_summarize_payload(first_owner_payload))
        print("---")

    workspaces = _workspace_rows(owner_rows)
    print(f"GET /v1/owners — OK, workspace lar (tea-…): {len(workspaces)}")
    for oid, name in workspaces[:30]:
        suffix = f"  — {name}" if name else ""
        print(f"  {oid}{suffix}")
    if len(workspaces) > 30:
        print(f"  … va yana {len(workspaces) - 30} ta")
    print()

    ws_ids = {oid for oid, _ in workspaces}

    # --- /v1/services ichidagi ownerId (qo'shimcha tekshiruv)
    try:
        services = _list_all_services(headers)
    except requests.RequestException as e:
        print("GET /v1/services — xato (ownerId tekshiruvi o'tkazildi):", e, file=sys.stderr)
        services = []

    from_services: set[str] = set()
    for s in services:
        oid = str(s.get("ownerId") or "").strip()
        if oid.startswith("tea-"):
            from_services.add(oid)

    services_count = len(services)
    print(f"GET /v1/services — servislar: {services_count}, noyob ownerId: {len(from_services)} ta")
    if from_services:
        for oid in sorted(from_services)[:15]:
            print(f"  {oid}")
        if len(from_services) > 15:
            print(f"  …")
    elif services_count and not from_services:
        print("  [!] Servislar bor, lekin `ownerId` yo‘q — javob shakli o‘zgargan bo‘lishi mumkin.")
        if ns.debug:
            for s in services[:2]:
                sid = str(s.get("id") or "")
                print("  namuna:", sid, "kalitlar:", sorted(list(s.keys()))[:20])
    print()

    # --- xulosa
    if configured:
        in_owners = configured in ws_ids
        in_services = configured in from_services
        if in_owners and (in_services or not from_services):
            print("[OK] RENDER_OWNER_ID API bilan mos: /v1/owners ro‘yxatida bor.")
            if from_services and in_services:
                print("[OK] Servislarda ham shu ownerId ishlatiladi.")
            return 0
        if in_services and not in_owners:
            print(
                "[!] RENDER_OWNER_ID servislarda bor, lekin /v1/owners parse ro‘yxatida ko‘rinmadi "
                "(kalit scope yoki javob shakli). Odatda ishlatish mumkin.",
            )
            return 0
        if not in_owners and not in_services:
            print(
                "[XATO] RENDER_OWNER_ID API javoblarida topilmadi — ID noto‘g‘ri yoki boshqa hisob.",
                file=sys.stderr,
            )
            return 3
    else:
        if len(workspaces) == 1:
            only = workspaces[0][0]
            print(f"Tavsiya: `.env` ga RENDER_OWNER_ID={only} qo‘ying.")
        elif len(workspaces) > 1:
            print("Bir nechta workspace — Dashboarddan kerakli `tea-...` ni tanlang va RENDER_OWNER_ID qo‘ying.")
        elif from_services and len(from_services) == 1:
            only = next(iter(from_services))
            print(f"Tavsiya (faqat servislardan): RENDER_OWNER_ID={only}")
        else:
            print("Workspace aniqlanmadi — Dashboard → Team settings dan `tea-...` ni qo‘lda kiriting.")
            print()
            print("Mumkin sabablar:")
            print("  • `.env` dagi RENDER_API_KEY boshqa Render hisobiga tegishli (bo‘sh ro‘yxat).")
            print("  • Hisobda hozircha workspace/servis yo‘q yoki Blueprints orqali boshqa joyda.")
            print("  • Yordam:  python scripts\\check_render_owner_id.py --debug")

    if owner_rows and not workspaces:
        print()
        print("[!] /owners javobidan obyektlar ajratildi, lekin `tea-...` id topilmadi.")
        for row in owner_rows[:3]:
            tid = row.get("id") or row.get("ownerId")
            print("  namuna id:", repr(tid), "| kalitlar:", sorted(row.keys())[:14])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
