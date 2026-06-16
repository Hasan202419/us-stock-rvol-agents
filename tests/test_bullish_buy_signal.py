"""bullish_buy_signal — verdikt mantig'i, pozitsiya o'lchami, hisobot (tarmoqsiz)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.bullish_buy_signal import (
    CRITERIA,
    evaluate_bullish_buy,
    format_bullish_buy_report,
    verdict_badge,
)


class _FakeIgnition:
    """VolumeIgnitionStrategyAgent o'rnida boshqariladigan natija qaytaradi."""

    def __init__(self, *, fails: Optional[List[str]] = None, conf: int = 80) -> None:
        self.fails = fails or []
        self.conf = conf

    def evaluate(self, data: Dict[str, Any], thresholds: Any = None) -> Dict[str, Any]:
        sig = dict(data)
        sig.update(
            {
                "failed_rules": list(self.fails),
                "ignition_continuation_probability": self.conf,
                "ignition_trend_stage": "Ignition",
                "ignition_distance_to_resistance_pct": 2.1,
                "volume_pattern_summary": "3 kun hajm o'sishi; bugun 2.3x 20-kunlik",
                "rvol": 3.0,
                "price": 100.0,
                "stop_suggestion": 95.0,
                "take_profit_suggestion": 112.0,
                "ignition_risk_level": "Controlled",
            }
        )
        return sig


def _signal() -> Dict[str, Any]:
    return {"ticker": "nvda", "price": 100.0, "rvol": 3.0, "candles": [{"t": 1, "c": 100}]}


def test_all_criteria_pass_high_conf_is_buy() -> None:
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=[], conf=85))
    assert res["verdict"] == "BUY"
    assert res["ticker"] == "NVDA"
    assert res["criteria_passed"] == res["criteria_total"] == len(CRITERIA)
    # entry 100, stop 95, target 112 -> R:R = 12/5 = 2.4
    assert res["entry"] == 100.0 and res["stop"] == 95.0 and res["target"] == 112.0
    assert res["rr"] == 2.4


def test_hard_avoid_when_parabolic() -> None:
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=["parabolic"], conf=90))
    assert res["verdict"] == "AVOID"


def test_must_have_rvol_fail_blocks_buy() -> None:
    # RVOL fail -> must-have buzilgan, conf yuqori bo'lsa ham BUY emas
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=["rvol"], conf=85))
    assert res["verdict"] != "BUY"


def test_mid_confidence_is_watch() -> None:
    res = evaluate_bullish_buy(
        _signal(), agent=_FakeIgnition(fails=["atr_rising", "higher_low"], conf=58)
    )
    assert res["verdict"] == "WATCH"


def test_target_floored_above_entry_when_resistance_below() -> None:
    agent = _FakeIgnition(fails=[], conf=80)
    # take_profit (resistance) entry'dan past -> kamida min_rr*risk ga ko'tariladi
    def ev(data, thresholds=None):
        s = _FakeIgnition.evaluate(agent, data, thresholds)
        s["take_profit_suggestion"] = 98.0  # entry 100 dan past
        return s
    agent.evaluate = ev  # type: ignore[method-assign]
    res = evaluate_bullish_buy(_signal(), agent=agent)
    assert res["target"] > res["entry"]
    assert res["rr"] >= 1.5


def test_position_size_respects_risk_and_cap(monkeypatch) -> None:
    monkeypatch.setenv("BUY_EXAMPLE_ACCOUNT_USD", "10000")
    monkeypatch.setenv("MAX_RISK_PCT_OF_EQUITY", "1.0")
    monkeypatch.setenv("MAX_POSITION_SIZE_USD", "100000")
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=[], conf=85))
    # risk_usd = 10000*1% = 100; per-share = 100-95 = 5 -> 20 dona
    assert res["position"]["shares"] == 20
    assert res["position"]["risk_usd"] == 100.0
    assert res["position"]["notional"] == 2000.0


def test_position_size_capped_by_max_notional(monkeypatch) -> None:
    monkeypatch.setenv("BUY_EXAMPLE_ACCOUNT_USD", "1000000")
    monkeypatch.setenv("MAX_RISK_PCT_OF_EQUITY", "1.0")
    monkeypatch.setenv("MAX_POSITION_SIZE_USD", "1000")  # entry 100 -> max 10 dona
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=[], conf=85))
    assert res["position"]["shares"] == 10


def test_report_has_framework_structure() -> None:
    res = evaluate_bullish_buy(_signal(), agent=_FakeIgnition(fails=[], conf=85))
    html = format_bullish_buy_report(res, company="NVIDIA Corp")
    for label in (
        "Ticker:", "Company:", "Reason (Catalyst):", "Technical Setup:",
        "Entry Price:", "Stop Loss:", "Target Price:", "Risk/Reward Ratio:",
        "Position Size Example:", "Execution Plan:", "Final Trade Summary:",
    ):
        assert label in html
    assert "NVIDIA Corp" in html
    assert verdict_badge("BUY") in html
