"""RVOL skan presetlari — dashboard va Telegram bot umumiy."""

from __future__ import annotations

from typing import Dict

SCAN_PRESETS: Dict[str, Dict[str, float]] = {
    "Explorer": {"min_rvol": 1.0, "min_price": 0.5, "min_volume": 80_000, "min_change_percent": -3.0},
    "Balanced": {"min_rvol": 1.35, "min_price": 1.0, "min_volume": 200_000, "min_change_percent": -1.0},
    "Conservative": {"min_rvol": 2.0, "min_price": 1.0, "min_volume": 500_000, "min_change_percent": 0.05},
    # trader2B / qisqa muddat: yumshoqroq filtr, intraday harakat uchun
    "PropScalp": {"min_rvol": 1.15, "min_price": 1.0, "min_volume": 100_000, "min_change_percent": -2.5},
}

# Eski deploy (PropScalp repoda yo‘q) uchun inline zaxira
_PROP_SCALP_THRESHOLDS: Dict[str, float] = dict(SCAN_PRESETS["PropScalp"])


def resolve_scan_preset(name: str, *, default: str = "Explorer") -> tuple[str, Dict[str, float]]:
    """Preset nomini SCAN_PRESETS ga xavfsiz bog‘lash — KeyError bo‘lmasin."""

    want = (name or "").strip()
    if want in SCAN_PRESETS:
        return want, dict(SCAN_PRESETS[want])
    if want.lower() in {"propscalp", "prop_scalp", "prop-scalp"}:
        return "PropScalp", dict(_PROP_SCALP_THRESHOLDS)
    fallback = default if default in SCAN_PRESETS else "Explorer"
    return fallback, dict(SCAN_PRESETS[fallback])
