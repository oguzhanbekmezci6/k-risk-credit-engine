from fastapi.testclient import TestClient

from app.decision.banking_policy import housing_ltv_reference, vehicle_loan_reference
from app.decision.economic_profiles import akbank_rate_reference
from app.main import app


def login(client):
    r = client.post('/api/v4/auth/login', json={'username':'admin_test','password':'Q7!mR2#vL9@pT4'})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf_token']}


def test_akbank_public_rate_references_are_monthly_and_term_specific():
    assert akbank_rate_reference('ihtiyac', 24)['monthly_rate'] == .0384
    assert akbank_rate_reference('konut', 120)['monthly_rate'] == .0315
    assert akbank_rate_reference('tasit', 12)['monthly_rate'] == .0375
    assert akbank_rate_reference('tasit', 48)['monthly_rate'] == .0360
    assert akbank_rate_reference('tasit', 49) is None


def test_vehicle_reference_applies_value_ltv_and_term_bands():
    assert vehicle_loan_reference(400_000)['max_loan'] == 280_000
    assert vehicle_loan_reference(400_001)['max_ltv'] == .50
    assert vehicle_loan_reference(800_001)['max_term_months'] == 24
    assert vehicle_loan_reference(1_500_000)['max_loan'] == 300_000
    assert vehicle_loan_reference(2_000_001)['available'] is False


def test_vehicle_application_cannot_bypass_value_and_term_rules():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'VEH-RULE', 'requested_amount':500_000, 'term_months':24,
            'product_type':'tasit', 'repayment_type':'equal_installment',
            'pd':.02, 'lgd':.25, 'annual_rate':.45, 'monthly_net_income':500_000,
            'collateral_value':1_500_000,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        full = next(x for x in body['actions'] if x['factor'] == 1.0)
        codes = {x['code']: x for x in full['banking_checks']['checks']}
        assert codes['AKBANK_VEHICLE_LTV']['status'] == 'FAIL'
        assert codes['AKBANK_VEHICLE_TERM']['status'] == 'FAIL'
        assert body['max_feasible_limit'] == 0


def test_vehicle_application_requires_vehicle_value():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'VEH-MISSING', 'requested_amount':100_000, 'term_months':12,
            'product_type':'tasit', 'pd':.02, 'lgd':.25, 'monthly_net_income':100_000,
        })
        assert r.status_code == 200, r.text
        assert 'taşıt fatura/kasko değeri eksik' in r.json()['request_failures']


def test_other_home_reduces_housing_ltv_by_75_percent():
    first = housing_ltv_reference(1_000_000, 'A', False)
    other = housing_ltv_reference(1_000_000, 'A', True)
    assert first['max_ltv'] == .90
    assert other['max_ltv'] == .225
    assert other['max_loan'] == 225_000


def test_api_without_rate_uses_current_public_reference_default():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'RATE-DEFAULT', 'requested_amount':100_000, 'term_months':12,
            'product_type':'ihtiyac', 'pd':.02, 'lgd':.25, 'monthly_net_income':100_000,
        })
        assert r.status_code == 200, r.text
        assert abs(r.json()['applicant']['annual_rate'] - (.0384 * 12)) < 1e-12


def test_used_vehicle_age_rules_are_binding():
    from app.decision.banking_policy import daily_banking_checks

    too_old = daily_banking_checks(
        product_type='tasit', proposed_limit=100_000, requested_term_months=12,
        collateral_value=400_000, vehicle_is_used=True, vehicle_age_years=11,
        monthly_net_income=100_000, proposed_monthly_payment=5_000,
    )
    assert 'Güncel 2. el taşıt azami yaş sınırı' in too_old['hard_failures']

    age_term = daily_banking_checks(
        product_type='tasit', proposed_limit=100_000, requested_term_months=48,
        collateral_value=400_000, vehicle_is_used=True, vehicle_age_years=9,
        monthly_net_income=100_000, proposed_monthly_payment=5_000,
    )
    assert 'Güncel 2. el taşıt yaş + vade sınırı' in age_term['hard_failures']

    valid = daily_banking_checks(
        product_type='tasit', proposed_limit=100_000, requested_term_months=36,
        collateral_value=400_000, vehicle_is_used=True, vehicle_age_years=9,
        monthly_net_income=100_000, proposed_monthly_payment=5_000,
    )
    assert not any('2. el taşıt' in x for x in valid['hard_failures'])


def test_vehicle_affordability_does_not_invent_need_loan_50_percent_rule():
    from app.decision.banking_policy import daily_banking_checks

    checks = daily_banking_checks(
        product_type='tasit', proposed_limit=100_000, requested_term_months=12,
        collateral_value=400_000, monthly_net_income=100_000,
        proposed_monthly_payment=55_000, internal_max_debt_service_ratio=.60,
    )
    affordability = next(x for x in checks['checks'] if x['code'] == 'INTERNAL_AFFORDABILITY')
    assert affordability['limit'] == .60
    assert affordability['status'] == 'PASS'


def test_housing_age_plus_term_rule_is_binding():
    from app.decision.banking_policy import daily_banking_checks

    too_long = daily_banking_checks(
        product_type='konut', proposed_limit=500_000, requested_term_months=120,
        collateral_value=1_000_000, collateral_energy_class='A', applicant_age_years=65,
        monthly_net_income=100_000, proposed_monthly_payment=10_000,
    )
    assert 'Güncel konut yaş + vade sınırı' in too_long['hard_failures']

    valid = daily_banking_checks(
        product_type='konut', proposed_limit=500_000, requested_term_months=120,
        collateral_value=1_000_000, collateral_energy_class='A', applicant_age_years=60,
        monthly_net_income=100_000, proposed_monthly_payment=10_000,
    )
    assert 'Güncel konut yaş + vade sınırı' not in valid['hard_failures']
