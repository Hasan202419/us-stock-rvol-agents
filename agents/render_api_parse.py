"""Render REST API javoblarida wrapper qatorlari: `{cursor, owner}` va `{cursor, service}`.

Hujjatlashmagan tuzilma yangilanishlarida ham ishlashi uchun asosiy mapperlar shu yerda."""

from __future__ import annotations

from typing import Any


def unwrap_owner_row(item: Any) -> dict[str, Any] | None:
    """Bitta `/v1/owners` elementidan haqiqiy owner dict ni ajratadi."""

    if not isinstance(item, dict):
        return None
    sub = item.get("owner")
    if isinstance(sub, dict):
        return sub
    oid = str(item.get("id") or item.get("ownerId") or "").strip()
    if oid.startswith("tea-"):
        return item
    return None


def unwrap_service_row(item: Any) -> dict[str, Any] | None:
    """Bitta `/v1/services` elementidan haqiqiy service dict ni ajratadi."""

    if not isinstance(item, dict):
        return None
    sub = item.get("service")
    if isinstance(sub, dict):
        return sub
    sid = str(item.get("id") or "").strip()
    if sid.startswith("srv-"):
        return item
    return None


def next_cursor_from_page(payload: Any) -> str | None:
    """Paginatsiya: javob `{"cursor": "..."}` yoki oxirgi `[{ "cursor", ... }]` da bo'lishi mumkin."""

    if isinstance(payload, dict):
        c = payload.get("cursor")
        if isinstance(c, str) and c:
            return c
        return None
    if isinstance(payload, list) and payload:
        last = payload[-1]
        if isinstance(last, dict):
            c = last.get("cursor")
            if isinstance(c, str) and c:
                return c
    return None


def iter_owner_dicts(payload: Any) -> list[dict[str, Any]]:
    """GET /v1/owners sahifa JSON idan barcha owner obyektlarini chiqaradi."""

    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for x in payload:
            u = unwrap_owner_row(x)
            if u:
                rows.append(u)
        return rows
    if isinstance(payload, dict):
        lone = payload.get("owner")
        if isinstance(lone, dict):
            return [lone]
        if isinstance(lone, list) and lone:
            rows_l = [unwrap_owner_row(x) for x in lone]
            got = [u for u in rows_l if u is not None]
            if got:
                return got
        for key in ("owners", "items", "results", "workspaces", "data"):
            block = payload.get(key)
            if not isinstance(block, list) or not block:
                continue
            rows = []
            for item in block:
                u = unwrap_owner_row(item)
                if u:
                    rows.append(u)
                elif isinstance(item, dict):
                    sub = item.get("owner")
                    if isinstance(sub, list):
                        for y in sub:
                            u2 = unwrap_owner_row(y) if isinstance(y, dict) else None
                            if u2:
                                rows.append(u2)
            if rows:
                return rows
    return []


def iter_service_dicts(payload: Any) -> list[dict[str, Any]]:
    """GET /v1/services sahifa JSON idan barcha service obyektlarini chiqaradi."""

    if isinstance(payload, list):
        return [u for u in (unwrap_service_row(x) for x in payload) if u is not None]
    if isinstance(payload, dict):
        srv = payload.get("service")
        if isinstance(srv, dict):
            return [srv]
        for key in ("services", "items", "data"):
            block = payload.get(key)
            if not isinstance(block, list) or not block:
                continue
            rows = [u for u in (unwrap_service_row(x) for x in block) if u is not None]
            if rows:
                return rows
    return []
