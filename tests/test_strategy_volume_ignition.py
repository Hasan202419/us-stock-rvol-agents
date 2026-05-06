"""Volume ignition scanner — sintetik kunlik tarix bilan."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agents.strategy_volume_ignition import VolumeIgnitionStrategyAgent


def day_ms(day_index: int) -> int:
    eastern = ZoneInfo("America/New_York")
    base = datetime(2024, 1, 2, 16, 0, tzinfo=eastern)
    stamp = base + timedelta(days=day_index)
    return int(stamp.timestamp() * 1000)


def _ideal_candles_rows() -> list[dict]:
    """40 ish kun — past markaz, keyin silliq chiqish va oxirgi 3 kunda keskin hajm."""

    candles: list[dict] = []
    resistance = 52.4

    for i in range(40):
        t = day_ms(i)
        # Konsolidatsiya, keyin sekin o‘sish
        base = 48.2 + i * 0.07
        if i >= 30:
            base += (i - 29) * 0.05

        close = min(base, resistance - 0.15)
        spread = 0.22 + (0.02 * max(0, i - 32))
        lo = close - spread * 0.45
        hi = min(close + spread * 0.55, resistance + 0.02 * (1 if i == 28 else 0))

        v = 320_000 + i * 4_000
        if i >= 37:
            v += (i - 36) * 220_000

        candles.append({"t": t, "o": close - 0.02, "h": hi, "l": lo, "c": close, "v": float(v)})

    return candles


def test_volume_ignition_passes_with_synthetic_tape(monkeypatch) -> None:
    monkeypatch.setenv("IGNITION_MIN_AVG_VOLUME", "80000")
    monkeypatch.setenv("IGNITION_MIN_RVOL", "2")
    monkeypatch.setenv("IGNITION_VOL_VS_20D_AVG", "2")
    monkeypatch.setenv("MIN_PRICE", "1")
    monkeypatch.setenv("MIN_CHANGE_PERCENT", "-5")

    candles = _ideal_candles_rows()
    last = candles[-1]
    prior_mean = sum(float(b["v"]) for b in candles[-21:-1]) / 20.0
    vol_today = max(float(last["v"]) * 2.4, prior_mean * 2.15)

    payload = {
        "ticker": "IGN1",
        "price": float(last["c"]),
        "change_percent": 0.6,
        "volume": vol_today,
        "avg_volume": 1_200_000.0,
        "rvol": 2.6,
        "candles": candles,
        "data_delay": "test",
        "updated_time": "now",
    }

    agent = VolumeIgnitionStrategyAgent()
    out = agent.evaluate(payload, None)

    assert out["strategy_name"] == "volume_ignition_scan"
    assert out.get("volume_pattern_summary")
    assert out.get("ignition_professional_outline")
    if not out["strategy_pass"]:
        pytest.fail(f"Kutilgan pass; failed_rules={out.get('failed_rules')}")


def test_volume_ignition_fails_on_low_rvol(monkeypatch) -> None:
    monkeypatch.setenv("IGNITION_MIN_AVG_VOLUME", "80000")
    monkeypatch.setenv("IGNITION_MIN_RVOL", "2")

    candles = _ideal_candles_rows()
    last = candles[-1]
    prior_mean = sum(float(b["v"]) for b in candles[-21:-1]) / 20.0

    payload = {
        "ticker": "IGN2",
        "price": float(last["c"]),
        "change_percent": 0.5,
        "volume": prior_mean * 2.1,
        "avg_volume": 2_000_000.0,
        "rvol": 1.1,
        "candles": candles,
        "data_delay": "test",
        "updated_time": "now",
    }

    out = VolumeIgnitionStrategyAgent().evaluate(payload, None)

    assert out["strategy_pass"] is False
    assert "rvol" in out["failed_rules"]


def test_volume_ignition_short_history_fails(monkeypatch) -> None:
    monkeypatch.setenv("IGNITION_MIN_AVG_VOLUME", "1000")
    monkeypatch.setenv("IGNITION_MIN_RVOL", "1")

    payload = {
        "ticker": "IGN3",
        "price": 10.0,
        "change_percent": 1.0,
        "volume": 5_000_000.0,
        "avg_volume": 2_000_000.0,
        "rvol": 3.0,
        "candles": [],
        "data_delay": "test",
        "updated_time": "now",
    }

    out = VolumeIgnitionStrategyAgent().evaluate(payload, None)
    assert out["strategy_pass"] is False
    assert "bars_history" in out["failed_rules"]
