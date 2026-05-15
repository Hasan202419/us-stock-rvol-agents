#!/usr/bin/env python3
"""Loyiha sog‘lig‘i: importlar, asosiy modullar, testlar (qisqa)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULES = [
    "agents.scan_pipeline",
    "agents.trade_plan_format",
    "agents.mtf_snapshot",
    "agents.amt_vwap_scalp",
    "agents.scalp_daytrade_levels",
    "agents.chatgpt_analyst_agent",
]

REQUIRED_FILES = [
    "dashboard.py",
    "render.yaml",
    "agents/mtf_snapshot.py",
    "agents/amt_vwap_scalp.py",
    "agents/scalp_daytrade_levels.py",
]


def main() -> int:
    print(f"Root: {ROOT}\n")
    missing = [p for p in REQUIRED_FILES if not (ROOT / p).is_file()]
    if missing:
        print("MISSING files (push/deploy xato beradi):")
        for p in missing:
            print(f"  - {p}")
    else:
        print("OK: barcha kerakli fayllar mavjud.")

    print("\nImport tekshiruvi:")
    failed = 0
    for mod in MODULES:
        try:
            __import__(mod)
            print(f"  OK  {mod}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {mod}: {type(exc).__name__}: {exc}")

    print("\nTrade plan fallback (NameError yo‘qligi):")
    try:
        from agents.trade_plan_format import deterministic_trade_plan_from_signal

        deterministic_trade_plan_from_signal({"ticker": "T", "price": 1.0}, lang="en")
        deterministic_trade_plan_from_signal(
            {"ticker": "T", "price": 10.0, "trade_levels_ok": True, "trade_entry_price": 10.0,
             "trade_stop_loss": 9.5, "trade_tp1": 10.5},
            lang="uz",
        )
        print("  OK  deterministic_trade_plan_from_signal")
    except Exception as exc:
        failed += 1
        print(f"  FAIL {type(exc).__name__}: {exc}")

    print("\nPytest (ixtiyoriy, ~1 daqiqa):")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tail = (r.stdout or r.stderr or "").strip().splitlines()[-3:]
    for line in tail:
        print(f"  {line}")
    if r.returncode != 0:
        failed += 1
        print(f"  exit code {r.returncode}")

    print()
    if failed:
        print(f"XULOSA: {failed} ta muammo — tuzatib, keyin GitHub push + Render deploy.")
        return 1
    print("XULOSA: kod bazasi import/test bo‘yicha yaxshi. Render xato bo‘lsa → Environment / Logs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
