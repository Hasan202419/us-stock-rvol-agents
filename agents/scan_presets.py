"""RVOL skan presetlari — dashboard va Telegram bot umumiy."""

from __future__ import annotations

from typing import Dict

SCAN_PRESETS: Dict[str, Dict[str, float]] = {
    "Explorer": {"min_rvol": 1.0, "min_price": 0.5, "min_volume": 80_000, "min_change_percent": -3.0},
    "Balanced": {"min_rvol": 1.35, "min_price": 1.0, "min_volume": 200_000, "min_change_percent": -1.0},
    "Conservative": {"min_rvol": 2.0, "min_price": 1.0, "min_volume": 500_000, "min_change_percent": 0.05},
}
