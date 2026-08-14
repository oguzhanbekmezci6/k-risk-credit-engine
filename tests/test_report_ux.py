from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def login(client, username, password):
    r = client.post('/api/v4/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return r.json()['csrf_token']


def create_decision(client, csrf, applicant='RAPOR-1'):
    r = client.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json={
        'applicant_id': applicant, 'requested_amount': 1500000, 'term_months': 12, 'pd': .08, 'lgd': .55,
        'annual_rate': .32, 'funding_cost': .18
    })
    assert r.status_code == 200, r.text
    return r.json()['decision_id']


def test_manager_can_download_decision_explainability_pdf():
    with TestClient(app) as c:
        csrf = login(c, 'risk_test', 'Z8@kN3!sP6#uW2')
        did = create_decision(c, csrf)
        r = c.get(f'/api/v4/decision/{did}/report.pdf')
        assert r.status_code == 200, r.text
        assert r.headers['content-type'].startswith('application/pdf')
        assert 'attachment;' in r.headers.get('content-disposition', '')
        assert r.content.startswith(b'%PDF')
        assert len(r.content) > 5000


def test_analyst_cannot_download_manager_report():
    with TestClient(app) as c:
        csrf = login(c, 'analist_a', 'H4#qT9@bV2!mK7')
        did = create_decision(c, csrf, 'RAPOR-ANALIST')
        r = c.get(f'/api/v4/decision/{did}/report.pdf')
        assert r.status_code == 403


def test_money_fields_use_turkish_number_formatting_without_unsafe_dom():
    html = (ROOT/'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'app/static/app.js').read_text(encoding='utf-8')
    assert 'value="150.000"' in html
    assert 'class="money-input"' in html
    assert "toLocaleString('tr-TR'" in js
    assert "1.500.000,50" in js
    assert 'parseMoneyValue' in js and 'formatMoneyInput' in js
    assert 'innerHTML' not in js and 'localStorage' not in js


def test_is_explicitly_contract_and_report_led():
    html = (ROOT/'app/static/index.html').read_text(encoding='utf-8')
    assert 'Kredi sözleşmesini tanımlayın' in html
    assert 'Vade (ay)' in html and 'Geri ödeme yapısı' in html and 'PD ufku' in html
    assert 'Karar Nasıl Alındı?' in (ROOT/'app/static/app.js').read_text(encoding='utf-8')


def test_report_download_is_written_to_audit_log():
    with TestClient(app) as c:
        csrf = login(c, 'risk_test', 'Z8@kN3!sP6#uW2')
        did = create_decision(c, csrf, 'RAPOR-AUDIT')
        assert c.get(f'/api/v4/decision/{did}/report.pdf').status_code == 200
        audit = c.get('/api/v4/governance/audit?limit=20')
        assert audit.status_code == 200
        assert any(x['action'] == 'karar_raporu_indirildi' and x['entity_id'] == did for x in audit.json())


def test_report_does_not_truncate_binding_failures():
    source = Path("app/services/report_service.py").read_text(encoding="utf-8")
    assert 'failed_constraints") or [])[:2]' not in source
