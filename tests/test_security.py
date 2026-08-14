from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def login(client, username, password):
    r = client.post('/api/v4/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return r.json()['csrf_token']


def test_science_requires_authentication():
    with TestClient(app) as c:
        r = c.post('/api/v4/science/bayes/binomial', json={'alpha': 2, 'beta': 18, 'successes': 3, 'failures': 47})
        assert r.status_code == 401


def test_csrf_required_for_state_change():
    with TestClient(app) as c:
        csrf = login(c, 'admin_test', 'Q7!mR2#vL9@pT4')
        body = {'alpha': 2, 'beta': 18, 'successes': 3, 'failures': 47}
        assert c.post('/api/v4/science/bayes/binomial', json=body).status_code == 403
        assert c.post('/api/v4/science/bayes/binomial', headers={'X-CSRF-Token': csrf}, json=body).status_code == 200


def test_analyst_cannot_read_another_analysts_decision():
    with TestClient(app) as c1:
        csrf = login(c1, 'analist_a', 'H4#qT9@bV2!mK7')
        r = c1.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json={'applicant_id':'OWN-1','requested_amount':100000,'term_months':12,'pd':.08,'lgd':.50})
        assert r.status_code == 200
        did = r.json()['decision_id']
    with TestClient(app) as c2:
        login(c2, 'analist_b', 'J6!xC3#nR8@wP5')
        assert c2.get(f'/api/v4/decision/{did}').status_code == 404


def test_stored_xss_payload_rejected_and_frontend_has_no_dangerous_sinks():
    js = (ROOT / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in js
    assert 'localStorage' not in js
    assert 'sessionStorage' not in js
    with TestClient(app) as c:
        csrf = login(c, 'analist_a', 'H4#qT9@bV2!mK7')
        payload = {
            'applicant_id':'XSS-1','requested_amount':100000,'term_months':12,'pd':.08,'lgd':.50,
            'information_signal': {
                'name':'<img src=x onerror=alert(1)>','cost':10,
                'signal_names':['a','b','c'],
                'signal_given_state':[[.8,.1,.1],[.2,.6,.2],[.1,.2,.7]]
            }
        }
        assert c.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json=payload).status_code == 422


def test_logout_revokes_server_side_session():
    with TestClient(app) as c:
        csrf = login(c, 'risk_test', 'Z8@kN3!sP6#uW2')
        assert c.post('/api/v4/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert c.get('/api/v4/auth/session').status_code == 401


def test_security_headers_present():
    with TestClient(app) as c:
        r = c.get('/')
        assert r.headers['x-content-type-options'] == 'nosniff'
        assert r.headers['x-frame-options'] == 'DENY'
        assert "default-src 'self'" in r.headers['content-security-policy']
        assert r.headers['referrer-policy'] == 'no-referrer'


def test_numeric_and_matrix_bounds():
    with TestClient(app) as c:
        csrf = login(c, 'admin_test', 'Q7!mR2#vL9@pT4')
        huge = c.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json={'applicant_id':'BIG-1','requested_amount':10**15,'term_months':12,'pd':.08,'lgd':.5})
        assert huge.status_code == 422
        matrix = {'actions':[f'A{i}' for i in range(21)], 'states':['s'], 'payoffs':[[1] for _ in range(21)], 'probabilities':[1]}
        assert c.post('/api/v4/science/matrix', headers={'X-CSRF-Token': csrf}, json=matrix).status_code == 422


def test_account_lockout_after_repeated_failures():
    with TestClient(app) as c:
        for _ in range(5):
            c.post('/api/v4/auth/login', json={'username':'lock_test','password':'Yanlis-Sifre!123'})
        r = c.post('/api/v4/auth/login', json={'username':'lock_test','password':'L5@vD8!qS2#zM7'})
        assert r.status_code == 429


def test_no_production_default_credentials_or_secret_key_fallback():
    source = '\n'.join(p.read_text(encoding='utf-8', errors='ignore') for p in (ROOT/'app').rglob('*.py'))
    for forbidden in ['Risk!' + '2026', 'Analyst!' + '2026', 'local-demo-secret-' + 'change-before-production', 'SECRET' + '_KEY']:
        assert forbidden not in source


def test_container_runs_non_root():
    dockerfile = (ROOT/'Dockerfile').read_text(encoding='utf-8')
    assert 'USER 10001:10001' in dockerfile
    compose = (ROOT/'docker-compose.yml').read_text(encoding='utf-8')
    assert 'no-new-privileges:true' in compose and 'cap_drop:' in compose


def test_security_critical_dependencies_are_pinned_to_current_hardened_release_line():
    req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'fastapi==0.141.1' in req
    assert 'starlette==1.4.1' in req
    assert 'python-multipart' not in req
    assert 'reportlab==4.4.9' in req


def test_runtime_dependency_guard_has_secure_minimums():
    source = (ROOT / 'app' / 'core' / 'dependency_guard.py').read_text(encoding='utf-8')
    assert '"fastapi": (0, 141, 1)' in source
    assert '"starlette": (1, 4, 1)' in source
    assert '"python-multipart"' not in source
    assert '"reportlab": (4, 4, 9)' in source


def test_runtime_dependency_guard_rejects_old_starlette(monkeypatch):
    from app.core import dependency_guard as guard

    versions = {
        'fastapi': '0.141.1',
        'starlette': '0.50.0',
        'reportlab': '4.4.9',
    }
    monkeypatch.setattr(guard, 'version', lambda package: versions[package])
    try:
        guard.verify_runtime_dependencies()
    except RuntimeError as exc:
        assert 'starlette 0.50.0 < 1.4.1' in str(exc)
    else:
        raise AssertionError('Eski Starlette sürümü reddedilmeliydi.')


def test_runtime_dependency_guard_accepts_hardened_versions(monkeypatch):
    from app.core import dependency_guard as guard

    versions = {
        'fastapi': '0.141.1',
        'starlette': '1.4.1',
        'reportlab': '4.4.9',
    }
    monkeypatch.setattr(guard, 'version', lambda package: versions[package])
    guard.verify_runtime_dependencies()


def test_analyst_cannot_use_advanced_science():
    with TestClient(app) as c:
        csrf = login(c, 'analist_a', 'H4#qT9@bV2!mK7')
        s = c.post('/api/v4/science/bayes/binomial', headers={'X-CSRF-Token': csrf}, json={'alpha':2,'beta':18,'successes':3,'failures':47})
        assert s.status_code == 403


def test_frontend_v6_is_guided_corporate_turkish_burgundy_brass_and_safe():
    html = (ROOT / 'app' / 'static' / 'index.html').read_text(encoding='utf-8')
    js = (ROOT / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    css = (ROOT / 'app' / 'static' / 'styles.css').read_text(encoding='utf-8')
    assert 'Kredi Kararı' in html and 'Başvurular' in html and 'Karar Nasıl Alındı?' in js
    assert '--kr-red:#960000' in css and '--kr-deep:#4c0000' in css
    assert 'innerHTML' not in js and 'localStorage' not in js and 'sessionStorage' not in js
    assert "const API = '/api/v4'" in js


def test_decision_history_is_owner_scoped_for_analyst():
    with TestClient(app) as c1:
        csrf = login(c1, 'analist_a', 'H4#qT9@bV2!mK7')
        c1.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json={'applicant_id':'HIST-A','requested_amount':100000,'term_months':12,'pd':.08,'lgd':.5})
    with TestClient(app) as c2:
        csrf = login(c2, 'analist_b', 'J6!xC3#nR8@wP5')
        c2.post('/api/v4/decision/evaluate', headers={'X-CSRF-Token': csrf}, json={'applicant_id':'HIST-B','requested_amount':100000,'term_months':12,'pd':.08,'lgd':.5})
        rows = c2.get('/api/v4/decision/history').json()
        assert rows and all(x['actor'] == 'analist_b' for x in rows)
        assert not any(x['applicant_id'] == 'HIST-A' for x in rows)
