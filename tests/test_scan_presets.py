"""scan_presets — PropScalp xavfsiz resolve."""

from __future__ import annotations

from agents.scan_presets import SCAN_PRESETS, resolve_scan_preset


def test_resolve_propscalp_when_missing_from_dict() -> None:
    saved = SCAN_PRESETS.pop("PropScalp", None)
    try:
        name, th = resolve_scan_preset("PropScalp", default="Explorer")
        assert name == "PropScalp"
        assert th["min_rvol"] == 1.15
    finally:
        if saved is not None:
            SCAN_PRESETS["PropScalp"] = saved


def test_resolve_unknown_falls_back_explorer() -> None:
    name, th = resolve_scan_preset("NoSuchPreset", default="Explorer")
    assert name == "Explorer"
    assert th == SCAN_PRESETS["Explorer"]
