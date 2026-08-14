from pathlib import Path

from fastapi.testclient import TestClient

from app.decision.banking_policy import consumer_loan_max_term_months, housing_ltv_reference
from app.decision.loan_economics import annuity_payment, build_contractual_schedule, cashflow_economics, optimum_term_indicator, solve_break_even_annual_rate
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def login(client, username="admin_test", password="Q7!mR2#vL9@pT4"):
    r = client.post('/api/v4/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf_token']}


def test_gecer_2014_payment_examples_are_reproduced():
    assert abs(annuity_payment(100_000, .01, 120) - 1434.71) < .02
    assert abs(annuity_payment(100_000, .01, 60) - 2224.44) < .02
    assert abs(annuity_payment(100_000, .01, 180) - 1200.17) < .02
    assert abs(annuity_payment(100_000, .01, 240) - 1101.09) < .02


def test_gecer_optimum_term_indicator_monthly_one_percent():
    r = optimum_term_indicator(.01)
    assert r['available'] is True
    assert abs(r['months'] - 69.7) < .3
    assert 'önerisi değildir' in r['note']


def test_amortization_schedule_balances_to_zero():
    rows = build_contractual_schedule(100_000, .12, .06, 36, 'equal_installment')
    assert len(rows) == 36
    assert abs(sum(x['principal'] for x in rows) - 100_000) < .01
    assert abs(rows[-1]['closing_balance']) < .01
    assert rows[0]['interest'] > rows[-1]['interest']
    assert rows[0]['principal'] < rows[-1]['principal']


def test_longer_maturity_reduces_payment_but_increases_total_interest():
    short = build_contractual_schedule(100_000, .24, .10, 12, 'equal_installment')
    long = build_contractual_schedule(100_000, .24, .10, 36, 'equal_installment')
    assert long[0]['payment'] < short[0]['payment']
    assert sum(x['interest'] for x in long) > sum(x['interest'] for x in short)


def test_current_consumer_term_reference_thresholds():
    assert consumer_loan_max_term_months(125_000) == 36
    assert consumer_loan_max_term_months(125_001) == 24
    assert consumer_loan_max_term_months(250_000) == 24
    assert consumer_loan_max_term_months(250_001) == 12


def test_housing_ltv_reference_energy_classes():
    assert housing_ltv_reference(5_000_000, 'A')['max_loan'] == 4_500_000
    assert housing_ltv_reference(5_000_000, 'C')['max_loan'] == 4_000_000
    assert housing_ltv_reference(5_000_000, 'other')['max_loan'] == 3_500_000


def test_decision_api_requires_maturity():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'TERM-MISSING', 'requested_amount':100_000, 'pd':.05, 'lgd':.40
        })
        assert r.status_code == 422
        assert 'term_months' in r.text or 'Vade' in r.text


def test_decision_returns_cashflow_market_and_banking_context():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'ECON-36', 'requested_amount':100_000, 'term_months':36,
            'product_type':'ihtiyac', 'repayment_type':'equal_installment',
            'pd':.05, 'pd_basis':'annual_12m', 'lgd':.40,
            'annual_rate':.75, 'funding_cost':.18,
            'monthly_net_income':100_000, 'existing_monthly_debt_service':5_000,
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b['loan_economics']['term_months'] == 36
        assert len(b['loan_economics']['schedule']) == 36
        assert b['loan_economics']['monthly_payment'] > 0
        # V11 merkezi ekonomik profil: istemcinin eski funding_cost alanı bilinçli olarak yok sayılır.
        assert abs(b['applicant']['funding_cost'] - .467) < 1e-12
        assert b['loan_economics']['expected_interest_income'] >= 0
        assert b['market_context']['tcmb_policy_rate'] > 0
        assert b['banking_checks']['checks']
        assert b['economics']['expected_loss'] >= b['economics']['expected_loss_12m']
        assert b['information_value']['action_recommendation'] is None


def test_need_loan_reference_can_make_long_term_action_infeasible():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'BDDK-TERM', 'requested_amount':300_000, 'term_months':24,
            'product_type':'ihtiyac', 'pd':.03, 'lgd':.30,
            'monthly_net_income':200_000,
        })
        assert r.status_code == 200, r.text
        b = r.json()
        full = next(x for x in b['actions'] if x['factor'] == 1.0)
        assert full['feasible'] is False
        assert any('BDDK tüketici kredisi vade sınırı' in x for x in full['failed_constraints'])


def test_affordability_is_labeled_internal_policy_not_regulation():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'DSR-1', 'requested_amount':100_000, 'term_months':12,
            'product_type':'ihtiyac', 'pd':.03, 'lgd':.30,
            'monthly_net_income':10_000, 'existing_monthly_debt_service':8_000,
        })
        assert r.status_code == 200, r.text
        checks = [x for x in r.json()['actions'][-1]['banking_checks']['checks'] if x['code']=='AKBANK_RETAIL_AFFORDABILITY']
        assert checks and 'Güncel' in checks[0]['source']
        assert checks[0]['limit'] == .50
        assert checks[0]['status'] == 'FAIL'


def test_frontend_exposes_contract_fields_and_no_info_buy_recommendation():
    html = (ROOT/'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'app/static/app.js').read_text(encoding='utf-8')
    for token in ['dTerm','dProduct','dRepayment','dPdBasis','dIncome','dExistingDebt','dCollateral']:
        assert token in html
    assert 'Kredi ekonomisi' in js
    assert 'Kararı etkileyen politika kontrolleri' in js
    assert "['Sinyal','Olasılık','Sonsal PD','Kesinlik eşdeğeri']" in js
    assert 'SATIN AL' not in js and 'SATIN_AL' not in js



def _econ(rate=.60, funding=.40, term=24):
    return cashflow_economics(
        principal=100_000, annual_rate=rate, funding_cost=funding, term_months=term,
        repayment_type='equal_installment', pd=.05, pd_basis='annual_12m', lgd=.40,
        ead_factor=1.0, late_probability=.08, late_loss_rate=.03, operating_cost=500,
        upfront_fee=0, capital_cost_rate=.03, capital_confidence=.99, capital_model_status='pilot'
    )


def test_time_value_of_money_is_explicit_in_economic_engine():
    e = _econ()
    assert e['discount_method'] == 'flat_funding_rate_pilot'
    assert abs(e['discount_rate_annual'] - .40) < 1e-12
    assert 'expected_npv' in e and 'lifetime_expected_contribution' in e
    assert e['expected_npv'] != e['lifetime_expected_contribution']


def test_break_even_rate_solves_expected_npv_not_nominal_sum():
    rate = solve_break_even_annual_rate(
        principal=100_000, funding_cost=.40, term_months=24, repayment_type='equal_installment',
        pd=.05, pd_basis='annual_12m', lgd=.40, ead_factor=1.0, late_probability=.08,
        late_loss_rate=.03, operating_cost=500, upfront_fee=0, capital_cost_rate=.03,
        capital_confidence=.99, capital_model_status='pilot'
    )
    e = _econ(rate=rate)
    assert abs(e['expected_npv']) < 2.0


def test_captures_credit_purpose_and_repayment_source_for_audit():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={
            'applicant_id':'PURPOSE-1', 'requested_amount':100_000, 'term_months':12,
            'product_type':'ihtiyac', 'loan_purpose':'eğitim harcaması',
            'repayment_source':'düzenli ücret geliri', 'pd':.03, 'lgd':.30,
            'monthly_net_income':100_000,
        })
        assert r.status_code == 200, r.text
        b = r.json()
        assert b['applicant']['loan_purpose'] == 'eğitim harcaması'
        assert b['applicant']['repayment_source'] == 'düzenli ücret geliri'
        assert 'expected_npv' in b['economics']
