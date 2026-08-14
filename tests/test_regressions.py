from app.decision.credit import evaluate_credit
from app.decision.economic_profiles import economic_profile_for
from app.decision.loan_economics import solve_break_even_annual_rate
from app.domain.models import Applicant, Policy


def policy():
    return Policy(
        policy_id="dengeli", name="Dengeli", version="9.0", status="active",
        risk_aversion=1 / 125000, limit_factors=(0, .25, .50, .75, 1.0),
        max_pd=.18, max_expected_loss_rate=.17, min_raroc=.08,
        target_margin_rate=.015, max_debt_service_ratio=.60,
    )


def applicant(product="ihtiyac", **overrides):
    data = dict(
        applicant_id="REG-001", requested_amount=1_000_000, term_months=12,
        product_type=product, repayment_type="equal_installment",
        pd=.03, pd_basis="annual_12m", lgd=.30, annual_rate=.30,
        monthly_net_income=14_000, existing_monthly_debt_service=0,
        upfront_fee=10_000,
    )
    data.update(economic_profile_for(product).asdict())
    data.update(overrides)
    return Applicant(**data)


def test_dynamic_solver_finds_feasible_limit_missed_by_static_grid():
    result = evaluate_credit(applicant(), policy(), signal=None)
    assert result["decision_label"] == "KISMİ ONAY"
    assert 68_000 < result["max_feasible_limit"] < 70_000
    assert result["recommended_limit"] == result["max_feasible_limit"]


def test_bullet_affordability_uses_peak_payment_not_first_interest_payment():
    result = evaluate_credit(
        applicant(
            repayment_type="bullet", requested_amount=1_000_000,
            monthly_net_income=200_000, annual_rate=.20, pd=.01, lgd=.20,
            upfront_fee=0,
        ),
        policy(), signal=None,
    )
    loan = result["requested_scenario"]["loan_economics"]
    assert loan["max_contractual_payment"] > loan["monthly_payment"] * 20
    assert "kurum borç ödeme kapasitesi sınırı" in result["request_failures"]


def test_housing_requires_collateral_value_for_ltv_control():
    result = evaluate_credit(
        applicant(
            product="konut", requested_amount=1_000_000,
            monthly_net_income=1_000_000, annual_rate=.80,
            pd=.01, lgd=.20, collateral_value=0, upfront_fee=0,
        ),
        policy(), signal=None,
    )
    assert result["decision_label"] == "REDDET"
    assert "konut ekspertiz/teminat değeri eksik" in result["request_failures"]
    assert any(x["code"] == "HOUSING_COLLATERAL_REQUIRED" and x["status"] == "FAIL" for x in result["policy_controls"])


def test_high_pd_is_handled_consistently_with_late_probability_clipping():
    result = evaluate_credit(applicant(pd=.95), policy(), signal=None)
    assert result["application_risk"]["pd_12m"] == .95
    assert result["decision_label"] == "REDDET"


def test_break_even_returns_none_when_search_range_never_reaches_zero_npv():
    rate = solve_break_even_annual_rate(
        principal=1.0, funding_cost=.467, term_months=12,
        repayment_type="equal_installment", pd=.03, pd_basis="annual_12m",
        lgd=.30, ead_factor=1.0, late_probability=.10, late_loss_rate=.04,
        operating_cost=900, upfront_fee=0, capital_cost_rate=.03,
        capital_confidence=.99, capital_model_status="pilot",
        bsmv_rate=.15, kkdf_rate=.15, recovery_lag_months=6,
    )
    assert rate is None


def test_public_funding_proxy_does_not_create_false_hard_rejects():
    result = evaluate_credit(
        applicant(
            applicant_id="DEMO-1950", requested_amount=1_950_000,
            annual_rate=.50, pd=.08, lgd=.55,
            monthly_net_income=50_000, existing_monthly_debt_service=5_000,
            upfront_fee=0,
        ),
        policy(), signal=None,
    )
    assert result["decision_label"] == "KISMİ ONAY"
    assert result["primary_reason"] == "kurum borç ödeme kapasitesi sınırı"
    assert result["request_failures"] == ["kurum borç ödeme kapasitesi sınırı"]
    controls = {c["code"]: c for c in result["policy_controls"]}
    assert controls["POLICY_PRICING_FLOOR"]["status"] == "UYARI"
    assert controls["POLICY_RAROC"]["status"] == "UYARI"
    assert result["selection_mode"] == "max_hard_control_feasible_limit"
