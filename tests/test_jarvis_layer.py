import pytest

from src.config.settings import JarvisSettings
from src.models.schemas import HalalReport, SignalCandidate
from src.modules.halal_gate import apply_halal_gate


def test_signal_candidate_defaults():
    s = SignalCandidate(symbol="AAPL", entry=100, stop=95, tp1=110, tp2=115, rr=2.0)
    assert s.decision == "NO_SIGNAL"
    assert s.human_confirmation_required is True


@pytest.fixture
def halal_cfg() -> JarvisSettings:
    return JarvisSettings(
        halal_max_debt_ratio=0.30,
        halal_max_impure_rev=0.05,
        halal_max_cash_ratio=0.30,
    )


def test_halal_gate_rejects_non_compliant(halal_cfg: JarvisSettings):
    ok, reasons = apply_halal_gate(
        HalalReport(symbol="X", status="non_compliant", detail="haram"),
        settings=halal_cfg,
    )
    assert ok is False
    assert "NON_COMPLIANT" in reasons[0]


def test_halal_gate_passes_compliant(halal_cfg: JarvisSettings):
    ok, reasons = apply_halal_gate(
        HalalReport(symbol="Y", status="compliant", detail="ok"),
        settings=halal_cfg,
    )
    assert ok is True


def test_halal_gate_debt_ratio(halal_cfg: JarvisSettings):
    ok, reasons = apply_halal_gate(None, {"debt_ratio": 0.9, "impure_revenue_pct": 0.0}, settings=halal_cfg)
    assert ok is False
    assert "Debt" in reasons[0]


def test_halal_gate_cash_ratio(halal_cfg: JarvisSettings):
    ok, reasons = apply_halal_gate(
        None,
        {"debt_ratio": 0.1, "impure_revenue_pct": 0.0, "cash_ratio": 0.5},
        settings=halal_cfg,
    )
    assert ok is False
    assert "Cash" in reasons[0]


def test_halal_gate_questionable_warning(halal_cfg: JarvisSettings):
    ok, reasons = apply_halal_gate(
        HalalReport(symbol="Z", status="questionable", detail="doubt"),
        settings=halal_cfg,
    )
    assert ok is True
    assert any("questionable" in r for r in reasons)
