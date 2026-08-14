from pathlib import Path

from app.decision.credit import DEFAULT_SIGNAL, evaluate_credit
from app.domain.models import Applicant, Policy

ROOT = Path(__file__).resolve().parents[1]


def balanced_policy():
    return Policy(
        "dengeli", "Dengeli", "8.0", "active", .000008,
        (0, .25, .50, .75, 1.0), .18, .17, .08, .015,
    )


def demo_information_case():
    return Applicant(
        "DEMO-001", 5_000_000, .06, .20,
        annual_rate=.32, funding_cost=.18, funding_method="approved_internal_ftp", operating_cost=900,
        capital_cost_rate=.03, late_probability=.10, late_loss_rate=.04, parameter_status="approved",
    )


def test_evsi_uses_same_risk_adjusted_decision_criterion():
    r = evaluate_credit(demo_information_case(), balanced_policy(), DEFAULT_SIGNAL)
    info = r["information_value"]
    assert r["recommended_limit"] < r["risk_neutral_limit"]
    assert r["recommended_limit"] in {1_250_000, 2_500_000, 3_750_000}
    assert info["criterion"] == "risk_adjusted_certainty_equivalent"
    assert info["policy_reapplied_after_signal"] is True
    assert info["evsi"] > 1_000
    assert "recommendation" not in info
    assert info["action_recommendation"] is None
    assert info["is_simulation"] is True
    assert info["source_mode"] == "simulation"


def test_red_signal_reapplies_policy_and_rejects_high_posterior_pd():
    r = evaluate_credit(demo_information_case(), balanced_policy(), DEFAULT_SIGNAL)
    red = next(x for x in r["information_value"]["signals"] if x["signal"] == "kırmızı")
    assert red["posterior_pd"] > balanced_policy().max_pd
    assert red["best_action"] == "REDDET"
    assert red["feasible_actions"] == ["REDDET"]
    assert any("PD üst sınırı" in x for x in red["failed_constraints"]["ONAY 25%"])


def test_evsi_never_exceeds_same_criterion_evpi():
    for pd in (.02, .06, .12, .17):
        for lgd in (.20, .45, .70):
            a = Applicant(
                f"GRID-{pd}-{lgd}", 1_500_000, pd, lgd,
                annual_rate=.32, funding_cost=.18, funding_method="approved_internal_ftp", operating_cost=900,
                capital_cost_rate=.03, late_probability=.10, late_loss_rate=.04, parameter_status="approved",
            )
            r = evaluate_credit(a, balanced_policy(), DEFAULT_SIGNAL)
            assert r["information_value"]["evsi"] <= r["decision_science"]["evpi"] + 1e-6


def test_evpi_is_risk_adjusted_and_classical_value_is_kept_separately():
    r = evaluate_credit(demo_information_case(), balanced_policy(), DEFAULT_SIGNAL)
    ds = r["decision_science"]
    assert ds["evpi_method"] == "risk_adjusted_certainty_equivalent"
    assert ds["evpi"] > 0
    assert "classical_risk_neutral_evpi" in ds
    assert ds["evpi"] != ds["classical_risk_neutral_evpi"]


def test_economic_capital_no_longer_uses_legacy_165_proxy():
    r = evaluate_credit(demo_information_case(), balanced_policy(), None)
    econ = r["economics"]
    assert "1,65" not in econ["economic_capital_method"]
    assert "Credit VaR" in econ["economic_capital_method"]
    assert econ["credit_var"] >= econ["expected_loss_12m"]
    schedule = r["loan_economics"]["schedule"]
    first12 = [x["economic_capital"] for x in schedule[:12]]
    assert first12 and abs(econ["economic_capital"] - sum(first12)/len(first12)) < 1e-6


def test_policy_exposes_human_readable_risk_tolerance_and_governance():
    p = balanced_policy().asdict()
    assert abs(p["risk_tolerance_tl"] - 125_000) < 1
    assert p["risk_calibration_status"] == "pilot"
    assert p["capital_model_status"] == "pilot"


def test_report_source_contains_all_decision_inputs_and_governance_fields():
    src = (ROOT / "app" / "services" / "report_service.py").read_text(encoding="utf-8")
    for token in ("ead_factor", "late_probability", "late_loss_rate", "risk_tolerance_tl", "max_pd", "max_expected_loss_rate", "min_raroc"):
        assert token in src


def test_production_fails_closed_until_risk_and_capital_are_approved(monkeypatch):
    import app.decision.credit as credit
    monkeypatch.setattr(credit, "MODE", "production")
    try:
        evaluate_credit(demo_information_case(), balanced_policy(), None)
    except ValueError as exc:
        assert "onaylanmamış" in str(exc)
    else:
        raise AssertionError("Production, pilot kalibrasyonla karar üretmemelidir")


def test_production_allows_explicitly_approved_policy(monkeypatch):
    import app.decision.credit as credit
    monkeypatch.setattr(credit, "MODE", "production")
    p = Policy(
        "dengeli", "Dengeli", "8.0", "active", .000008,
        (0, .25, .50, .75, 1.0), .18, .17, .08, .015,
        risk_calibration_status="approved",
        risk_calibration_note="Risk Komitesi onayı test senaryosu.",
        capital_model_status="approved",
        affordability_status="approved",
    )
    r = evaluate_credit(demo_information_case(), p, None)
    assert r["decision"] in {"ONAY", "REDDET"}
    assert r["policy_governance"]["risk_calibration_status"] == "approved"
    assert r["policy_governance"]["capital_model_status"] == "approved"
