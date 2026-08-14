from pathlib import Path

from fastapi.testclient import TestClient

from app.decision.banking_policy import market_snapshot
from app.decision.loan_economics import build_contractual_schedule, cashflow_economics
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def login(client):
    r = client.post('/api/v4/auth/login', json={'username':'admin_test','password':'Q7!mR2#vL9@pT4'})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf_token']}


def base_payload(**extra):
    p = {
        'applicant_id':'V11-BASE', 'requested_amount':150_000, 'term_months':12,
        'product_type':'ihtiyac', 'repayment_type':'equal_installment',
        'pd':.08, 'pd_basis':'annual_12m', 'lgd':.55,
        'annual_rate':.70, 'monthly_net_income':50_000,
        'existing_monthly_debt_service':5_000,
    }
    p.update(extra)
    return p


def test_consumer_schedule_includes_bsmv_and_kkdf_in_customer_payment():
    old = build_contractual_schedule(150_000, .60, .40, 12, 'equal_installment')
    new = build_contractual_schedule(150_000, .60, .40, 12, 'equal_installment', bsmv_rate=.15, kkdf_rate=.15)
    assert new[0]['payment'] > old[0]['payment']
    assert sum(x['bsmv'] for x in new) > 0
    assert sum(x['kkdf'] for x in new) > 0
    assert abs(sum(x['principal'] for x in new) - 150_000) < .01
    assert abs(new[-1]['closing_balance']) < .01


def test_single_state_model_is_one_source_of_truth_and_workout_funding_is_counted():
    e = cashflow_economics(
        principal=150_000, annual_rate=.70, funding_cost=.467, term_months=12,
        repayment_type='equal_installment', pd=.08, pd_basis='annual_12m', lgd=.55,
        ead_factor=1.0, late_probability=.10, late_loss_rate=.04,
        operating_cost=900, upfront_fee=0, capital_cost_rate=.03,
        capital_confidence=.99, capital_model_status='pilot',
        bsmv_rate=.15, kkdf_rate=.15, recovery_lag_months=6,
        funding_method='TCMB TL mevduat akım faizi bazlı pilot fonlama vekili; gerçek banka FTP değildir',
    )
    assert abs(sum(e['state_probabilities']) - 1.0) < 1e-12
    assert abs(e['expected_npv'] - e['state_expected_profit']) < 1e-10
    assert e['state_model'] == 'mutually_exclusive_good_late_default'
    assert e['expected_workout_funding_cost'] > 0
    assert e['contractual_total_bsmv'] > 0 and e['contractual_total_kkdf'] > 0


def test_api_uses_central_profile_and_ignores_legacy_user_tampering():
    with TestClient(app) as c:
        h = login(c)
        p = base_payload(
            applicant_id='V11-CENTRAL', annual_rate=.75,
            funding_cost=.10, operating_cost=1, capital_cost_rate=0,
            ead_factor=.2, late_probability=0, late_loss_rate=0,
        )
        r = c.post('/api/v4/decision/evaluate', headers=h, json=p)
        assert r.status_code == 200, r.text
        b = r.json()
        a = b['applicant']
        assert abs(a['funding_cost'] - .467) < 1e-12
        assert a['operating_cost'] == 900
        assert abs(a['capital_cost_rate'] - .03) < 1e-12
        assert a['ead_factor'] == 1.0
        assert abs(a['late_probability'] - .10) < 1e-12
        assert abs(a['late_loss_rate'] - .04) < 1e-12
        assert abs(a['bsmv_rate'] - .15) < 1e-12
        assert abs(a['kkdf_rate'] - .15) < 1e-12
        assert a['recovery_lag_months'] == 6
        assert a['parameter_status'] == 'pilot'


def test_affordability_uses_tax_and_fund_inclusive_installment():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json=base_payload(applicant_id='V11-DSR', annual_rate=.75))
        assert r.status_code == 200, r.text
        b = r.json()
        full = next(x for x in b['actions'] if x['factor'] == 1.0)
        check = next(x for x in full['banking_checks']['checks'] if x['code'] == 'AKBANK_RETAIL_AFFORDABILITY')
        expected = (5_000 + full['loan_economics']['monthly_payment']) / 50_000
        assert abs(check['actual'] - expected) < 1e-12
        assert full['loan_economics']['contractual_total_tax_and_fund'] > 0


def test_low_rate_pricing_floor_is_advisory_with_public_funding_proxy():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json=base_payload(applicant_id='V11-FLOOR', annual_rate=.32, monthly_net_income=300_000))
        assert r.status_code == 200, r.text
        b = r.json()
        nonzero = [x for x in b['actions'] if x['factor'] > 0]
        assert nonzero
        assert all('politika fiyat tabanı' not in x['failed_constraints'] for x in nonzero)
        assert any(x['pricing_floor_status'] == 'UYARI' for x in nonzero)
        assert all(x['economic_guardrails_binding'] is False for x in nonzero)
        assert b['selection_mode'] == 'max_hard_control_feasible_limit'


def test_housing_tax_profile_requires_explicit_bsmv_exemption_condition():
    with TestClient(app) as c:
        h = login(c)
        common = dict(
            requested_amount=500_000, term_months=24, product_type='konut', repayment_type='equal_installment',
            pd=.03, pd_basis='annual_12m', lgd=.25, annual_rate=.55,
            monthly_net_income=150_000, collateral_value=1_000_000, collateral_energy_class='A',
        )
        r1 = c.post('/api/v4/decision/evaluate', headers=h, json={'applicant_id':'H-NOEX', **common, 'housing_bsmv_exempt':False})
        r2 = c.post('/api/v4/decision/evaluate', headers=h, json={'applicant_id':'H-EX', **common, 'housing_bsmv_exempt':True})
        assert r1.status_code == 200 and r2.status_code == 200
        a1, a2 = r1.json()['applicant'], r2.json()['applicant']
        assert a1['kkdf_rate'] == 0 and a2['kkdf_rate'] == 0
        assert a1['bsmv_rate'] == .15
        assert a2['bsmv_rate'] == 0


def test_market_snapshot_is_latest_embedded_reference_and_not_named_ftp():
    m = market_snapshot()
    assert m['as_of'] == '2026-07-23'
    assert m['public_lending_reference']['as_of'] == '2026-07-31'
    assert m['tcmb_policy_rate'] == .37
    assert m['funding_proxy']['tl_deposit_rate'] == .467
    assert m['public_lending_reference']['consumer_loan_rate'] == .5691
    assert m['public_lending_reference']['housing_loan_rate'] == .3882
    assert m['public_lending_reference']['vehicle_loan_rate'] == .3883
    assert m['public_lending_reference']['tl_commercial_loan_rate'] == .5248
    assert 'FTP' in m['note'] and 'değildir' in m['note']


def test_ui_removes_internal_parameter_inputs_and_labels_pilot_metrics():
    html = (ROOT/'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'app/static/app.js').read_text(encoding='utf-8')
    for old_id in ['dFunding','dOp','dCapital','dEadFactor','dLate','dLateLoss','dSegment','dPurpose','dRepaymentSource']:
        assert f'id="{old_id}"' not in html
    for text in ['Pilot RAROC', 'BSMV', 'KKDF', 'TCMB politika faizi', 'gerçek FTP değil']:
        assert text in js or text in html
    assert 'LGD’yi otomatik değiştirmez' in html or "LGD'yi otomatik değiştirmez" in html
