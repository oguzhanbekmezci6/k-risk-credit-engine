from app.decision.credit import evaluate_credit
from app.decision.economic_profiles import economic_profile_for
from app.domain.models import Applicant, Policy


def policy():
    return Policy(
        policy_id="dengeli", name="Dengeli", version="9.0", status="active",
        risk_aversion=1/125000, limit_factors=(0,.25,.50,.75,1.0),
        max_pd=.18, max_expected_loss_rate=.17, min_raroc=.08, target_margin_rate=.015,
        max_debt_service_ratio=.60,
    )


def applicant(**overrides):
    data = dict(
        applicant_id="DEMO-001", requested_amount=1_500_000, term_months=18,
        product_type="ihtiyac", repayment_type="equal_installment",
        pd=.01, pd_basis="annual_12m", lgd=.13, annual_rate=.98,
        monthly_net_income=190_000, existing_monthly_debt_service=5_000,
    )
    data.update(economic_profile_for("ihtiyac").asdict())
    data.update(overrides)
    return Applicant(**data)


def test_finds_dynamic_limit_below_25_percent_grid():
    r = evaluate_credit(applicant(), policy(), signal=None)
    assert r["decision"] == "ONAY"
    assert r["decision_label"] == "KISMİ ONAY"
    assert 0 < r["recommended_limit"] < 1_500_000 * .25
    assert round(r["max_feasible_limit"]) == 250_000
    assert r["primary_reason"] == "BDDK tüketici kredisi vade sınırı"
    assert any(x.get("is_dynamic") for x in r["decision_candidates"])


def test_application_pd_is_not_zeroed_by_reject_action():
    r = evaluate_credit(applicant(), policy(), signal=None)
    assert abs(r["application_risk"]["pd_12m"] - .01) < 1e-9
    assert r["requested_scenario"]["economics"]["expected_loss"] > 0


def test_policy_controls_aggregate_request_failures():
    r = evaluate_credit(applicant(), policy(), signal=None)
    by_name = {x["name"]: x["status"] for x in r["policy_controls"]}
    assert by_name["12 aylık PD üst sınırı"] == "PASS"
    assert by_name["Tüketici kredisi vade sınırı"] == "FAIL"
    assert by_name["Borç ödeme / net gelir"] == "FAIL"


def test_reject_uses_requested_scenario_not_zero_as_application_risk():
    # 48 ay ihtiyaç kredisi: pozitif limit için vade referansı yok; REDDET beklenir.
    r = evaluate_credit(applicant(term_months=48), policy(), signal=None)
    assert r["decision"] == "REDDET"
    assert r["economics"]["applicable"] is False
    assert r["requested_scenario"]["loan_economics"]["monthly_payment"] > 0
    assert r["requested_scenario"]["economics"]["expected_loss"] > 0
    assert r["pricing"]["risk_adjusted_floor_rate"] is None
    assert r["robustness"]["label"] == "TÜM SENARYOLARDA REDDET"


def test_bddk_11152_term_threshold_uses_new_credit_amount_not_existing_balance():
    from app.decision.banking_policy import daily_banking_checks

    result = daily_banking_checks(
        product_type="ihtiyac",
        proposed_limit=120_000,
        requested_term_months=36,
        monthly_net_income=1_000_000,
        existing_monthly_debt_service=0,
        proposed_monthly_payment=1_000,
        internal_max_debt_service_ratio=0.60,
    )
    term = next(x for x in result["checks"] if x["code"] == "BDDK_CONSUMER_TERM")
    assert term["limit"] == 36
    assert term["status"] == "PASS"
