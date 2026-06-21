"""logger.py — skan natijalari va alertlarni CSV ga yozadi.

scan_log.csv  — har skan qatori
alerts_log.csv — yuborilgan Telegram alertlar
"""

from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from . import config

_COLUMNS = [
    "timestamp", "ticker", "mode", "price", "decision", "score", "halal_status",
    "vwap_status", "zone_status", "volume_spike", "entry", "stop", "target1",
    "target2", "rr", "reason",
]


def _path(filename: str) -> str:
    if os.path.isabs(filename):
        return filename
    return str(Path(__file__).resolve().parent / filename)


def _row(signal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "ticker": signal.get("ticker"),
        "mode": signal.get("mode"),
        "price": signal.get("price"),
        "decision": signal.get("decision"),
        "score": signal.get("score"),
        "halal_status": signal.get("halal_status"),
        "vwap_status": signal.get("vwap_status"),
        "zone_status": signal.get("zone_status"),
        "volume_spike": signal.get("volume_spike"),
        "entry": signal.get("entry"),
        "stop": signal.get("stop_loss"),
        "target1": signal.get("target1"),
        "target2": signal.get("target2"),
        "rr": signal.get("risk_reward"),
        "reason": signal.get("reason"),
    }


def _append(filename: str, signal: Dict[str, Any]) -> None:
    path = _path(filename)
    exists = os.path.isfile(path)
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow(_row(signal))
    except OSError as exc:
        print(f"logger: yozib bo'lmadi ({filename}): {exc}", flush=True)


def log_scan(signal: Dict[str, Any]) -> None:
    _append(config.SCAN_LOG_CSV, signal)


def log_alert(signal: Dict[str, Any]) -> None:
    _append(config.ALERTS_LOG_CSV, signal)
