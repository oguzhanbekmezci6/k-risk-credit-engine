from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_first_run_allows_user_to_create_own_admin_account(monkeypatch, tmp_path):
    import app.infra.db as db

    fresh_db = tmp_path / "first_setup.db"
    monkeypatch.setattr(db, "DB_PATH", fresh_db)

    with TestClient(app) as c:
        status = c.get('/api/v4/auth/setup-status')
        assert status.status_code == 200
        assert status.json()['needs_setup'] is True
        assert status.json()['can_setup'] is True

        created = c.post('/api/v4/auth/setup', json={
            'username': 'ilk.yonetici',
            'password': 'Guclu!Sifre2026',
            'setup_code': None,
        })
        assert created.status_code == 200, created.text
        body = created.json()
        assert body['username'] == 'ilk.yonetici'
        assert body['role'] == 'admin'
        assert body['must_change_password'] is False
        assert body['csrf_token']
        assert 'httponly' in created.headers.get('set-cookie', '').lower()

        session = c.get('/api/v4/auth/session')
        assert session.status_code == 200
        assert session.json()['username'] == 'ilk.yonetici'

        status2 = c.get('/api/v4/auth/setup-status')
        assert status2.json()['needs_setup'] is False

        second = c.post('/api/v4/auth/setup', json={
            'username': 'ikinci',
            'password': 'Baska!Sifre2026',
        })
        assert second.status_code == 409


def test_first_setup_is_atomic(monkeypatch, tmp_path):
    import app.infra.db as db

    fresh_db = tmp_path / "atomic_setup.db"
    monkeypatch.setattr(db, "DB_PATH", fresh_db)
    db.ensure_schema()
    first = db.create_first_admin('admin.one', 'Atomic!Sifre2026')
    assert first['role'] == 'admin'
    try:
        db.create_first_admin('admin.two', 'Atomic!Sifre2027')
    except ValueError as exc:
        assert 'İlk kurulum tamamlanmış' in str(exc)
    else:
        raise AssertionError('İkinci ilk-yönetici hesabı oluşturulmamalıydı.')


def test_frontend_has_first_account_creation_and_no_bootstrap_file_dependency():
    html = (ROOT / 'app' / 'static' / 'index.html').read_text(encoding='utf-8')
    js = (ROOT / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    run = (ROOT / 'run.py').read_text(encoding='utf-8')
    bat = (ROOT / 'START_K_RISK.bat').read_text(encoding='utf-8')

    assert 'Yönetici hesabı' in html and 'Hesabı Oluştur' in html
    assert 'Hesabı Oluştur' in html
    assert '/auth/setup-status' in js and '/auth/setup' in js
    assert 'ILK_GIRIS_TR.txt' not in html
    assert 'BOOTSTRAP_FILE' not in run
    assert 'ILK_GIRIS_TR.txt' not in bat


def test_admin_can_create_employee_from_governance():
    with TestClient(app) as c:
        login = c.post('/api/v4/auth/login', json={'username': 'admin_test', 'password': 'Q7!mR2#vL9@pT4'})
        assert login.status_code == 200, login.text
        csrf = login.json()['csrf_token']
        username = 'calisan_v41'
        created = c.post('/api/v4/governance/users', headers={'X-CSRF-Token': csrf}, json={
            'username': username,
            'password': 'Calisan!Sifre2026',
            'role': 'analyst',
        })
        # Test DB aynı oturumda başka bir çalıştırmadan bu kullanıcıyı içeriyorsa 422 de kabul etmeyelim;
        # benzersiz isim kullanıldığı için normal sonuç 200 olmalıdır.
        assert created.status_code == 200, created.text
        users = c.get('/api/v4/governance/users')
        assert users.status_code == 200
        assert any(x['username'] == username and x['role'] == 'analyst' for x in users.json())
