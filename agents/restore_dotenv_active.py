"""`.env` aktiv qatorlari: takrorlarni bosqarish hamda `# KEY=value` izohidan to‘ldirish."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from agents.bootstrap_env import (
    _COMMENT_LINE,
    _PROMOTE_FROM_COMMENT_IF_EMPTY,
)


_ACTIVE_ASSIGN = re.compile(r"^(\s*)([A-Za-z_]\w*)=(.*)$")


def scratch_value_tail(tail: str) -> str:
    return tail.split("#", 1)[0].strip().strip('"').strip("'")


def comment_defaults(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        m = _COMMENT_LINE.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k not in _PROMOTE_FROM_COMMENT_IF_EMPTY:
            continue
        if not v or v in {"...", '""', "''"}:
            continue
        out[k] = v
    return out


def active_assignments(lines: list[str]) -> list[tuple[int, str, str, str]]:
    out: list[tuple[int, str, str, str]] = []
    for i, raw in enumerate(lines):
        s = raw.rstrip("\r\n")
        stripped = s.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _ACTIVE_ASSIGN.match(s)
        if not m:
            continue
        indent, key, tail = m.group(1), m.group(2), m.group(3)
        out.append((i, indent, key, tail))
    return out


def build_merge(defs: dict[str, str], actives: list[tuple[int, str, str, str]]) -> tuple[dict[str, str], set[str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for _, _ind, key, tail in actives:
        buckets[key].append(scratch_value_tail(tail))

    merged: dict[str, str] = {}
    dups: set[str] = set()
    for key, vals in buckets.items():
        if len(vals) > 1:
            dups.add(key)
        merged[key] = next((x for x in reversed(vals) if x), "") or ""

    for key, v in defs.items():
        if not merged.get(key, "").strip() and v:
            merged[key] = v

    return merged, dups


def rebuild_lines(lines: list[str], merged: dict[str, str]) -> tuple[list[str], int]:
    actives = active_assignments(lines)
    emitted: set[str] = set()
    out: list[str] = []
    removed = 0
    active_keys = {k for _, _, k, __ in actives}

    for raw in lines:
        s = raw.rstrip("\r\n")
        stripped = s.strip()
        if not stripped or stripped.startswith("#"):
            out.append(s)
            continue
        m = _ACTIVE_ASSIGN.match(s)
        if not m:
            out.append(s)
            continue
        indent, key, _tail = m.group(1), m.group(2), m.group(3)
        if key not in active_keys:
            out.append(s)
            continue
        if key not in merged:
            out.append(s)
            continue
        if key in emitted:
            removed += 1
            continue
        emitted.add(key)
        out.append(f"{indent}{key}={merged[key]}")

    for key in sorted(merged.keys()):
        vv = merged.get(key, "").strip()
        if key in emitted:
            continue
        if vv:
            out.append(f"{key}={merged[key]}")

    return out, removed


def restore_env_file(project_root: Path, dry_run: bool = False, backup: bool = True) -> tuple[int, str]:
    """Nol = OK. Qaytariladi: exit_code, stdout/human-message."""

    env_path = project_root / ".env"
    if not env_path.is_file():
        return (1, f"Mavjud emas: {env_path}")

    raw_before = env_path.read_bytes()
    lines_list = raw_before.decode("utf-8-sig").splitlines()

    defs = comment_defaults(lines_list)
    act = active_assignments(lines_list)
    merged_map, duplicates = build_merge(defs, act)
    rebuilt, removed = rebuild_lines(lines_list, merged_map)

    if dry_run:
        return (
            0,
            "dry-run: takrorlar — "
            + (", ".join(sorted(duplicates)) if duplicates else "yo‘q")
            + f"; aktiv takror chiqarish: ~{removed}; satrlar {len(lines_list)} → {len(rebuilt)}.",
        )

    if backup:
        env_path.with_suffix(env_path.suffix + ".bak").write_bytes(raw_before)

    env_path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8", newline="\n")

    dup_msg = ", ".join(sorted(duplicates)) or "yo‘q"
    msg = (
        f"OK: {env_path} yangilandi. Chiqarilgan takror aktiv: {removed}. Takrorlangan kalitlar: {dup_msg}."
        + (f" Zaxira: {env_path.with_suffix(env_path.suffix + '.bak')}" if backup else "")
        + " Keyin: har bir kalit faqat bitta qatorda; tekshirish: python scripts/check_apis.py"
    )
    return (0, msg)

