from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def login(client: TestClient, username="admin_test", password="Q7!mR2#vL9@pT4"):
    r = client.post('/api/v4/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert 'access_token' not in body
    return {'X-CSRF-Token': body['csrf_token']}


def test_health_and_cookie_login():
    with TestClient(app) as c:
        assert c.get('/api/health').json() == {'status': 'ok'}
        r = c.post('/api/v4/auth/login', json={'username': 'admin_test', 'password': 'Q7!mR2#vL9@pT4'})
        assert r.status_code == 200
        cookie = r.headers.get('set-cookie', '').lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        assert 'access_token' not in r.json()


def test_decision_api_and_audit():
    with TestClient(app) as c:
        h = login(c)
        r = c.post('/api/v4/decision/evaluate', headers=h, json={'applicant_id': 'API-1', 'requested_amount': 150000, 'term_months': 12, 'pd': .08, 'lgd': .55})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['decision_id']
        assert body['decision'] in {'ONAY', 'REDDET'}
        g = c.get('/api/v4/governance/audit?limit=5')
        assert g.status_code == 200 and len(g.json()) >= 1



def test_risk_endpoints():
    with TestClient(app) as c:
        h = login(c, 'risk_test', 'Z8@kN3!sP6#uW2')
        ead = c.post('/api/v4/risk/ead', headers=h, json={'drawn_amount':300000,'undrawn_amount':200000,'ccf':.5})
        assert ead.status_code == 200, ead.text
        assert ead.json()['ead'] == 400000
        single = c.post('/api/v4/risk/single', headers=h, json={'exposure':{'exposure_id':'RISK-1','pd':.08,'lgd':.5,'ead':400000,'sector':'bireysel'},'confidence':.99})
        assert single.status_code == 200, single.text
        assert single.json()['expected_loss'] == 16000
        portfolio = c.post('/api/v4/risk/portfolio', headers=h, json={
            'exposures':[
                {'exposure_id':'P1','pd':.05,'lgd':.45,'ead':200000,'sector':'bireysel'},
                {'exposure_id':'P2','pd':.09,'lgd':.55,'ead':150000,'sector':'kobi'}
            ],
            'correlation':.15,'confidence':.999,'simulations':1200,'seed':42,'run_monte_carlo':True
        })
        assert portfolio.status_code == 200, portfolio.text
        assert portfolio.json()['analytic']['count'] == 2


def test_custom_stress_and_role_guard():
    payload = {
        'exposures':[{'exposure_id':'P1','pd':.08,'lgd':.5,'ead':100000,'sector':'x'}],
        'scenarios':[
            {'name':'Baz','pd_multiplier':1,'lgd_multiplier':1,'ead_multiplier':1},
            {'name':'TestDaralma','pd_multiplier':1.8,'lgd_multiplier':1.2,'ead_multiplier':1.05}
        ],
        'correlation':.15,'confidence':.999
    }
    with TestClient(app) as c:
        unauth = c.post('/api/v4/risk/single', json={'exposure':{'exposure_id':'X','pd':.05,'lgd':.5,'ead':100000,'sector':'x'},'confidence':.99})
        assert unauth.status_code in {401, 403}

    with TestClient(app) as c:
        analyst = login(c, 'analist_a', 'H4#qT9@bV2!mK7')
        forbidden = c.post('/api/v4/risk/portfolio', headers=analyst, json={'exposures':payload['exposures'],'correlation':.15,'confidence':.999,'simulations':1200,'seed':42,'run_monte_carlo':False})
        assert forbidden.status_code == 403

    with TestClient(app) as c:
        h = login(c, 'risk_test', 'Z8@kN3!sP6#uW2')
        r = c.post('/api/v4/risk/stress', headers=h, json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['worst_scenario'] == 'TestDaralma'
        assert body['results'][1]['expected_loss'] > body['results'][0]['expected_loss']
