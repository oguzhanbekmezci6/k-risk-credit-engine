from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_turkish_username_first_setup_and_login(monkeypatch, tmp_path):
    import app.infra.db as db

    fresh_db = tmp_path / "v42_turkish_login.db"
    monkeypatch.setattr(db, "DB_PATH", fresh_db)

    with TestClient(app) as client:
        status = client.get("/api/v4/auth/setup-status")
        assert status.status_code == 200
        assert status.json()["needs_setup"] is True

        created = client.post(
            "/api/v4/auth/setup",
            json={"username": "Oğuzhan", "password": "Guclu!Sifre2026", "setup_code": None},
        )
        assert created.status_code == 200, created.text
        assert created.json()["username"] == "oğuzhan"

        csrf = created.json()["csrf_token"]
        logout = client.post("/api/v4/auth/logout", headers={"X-CSRF-Token": csrf})
        assert logout.status_code == 200, logout.text

        login = client.post(
            "/api/v4/auth/login",
            json={"username": "OĞUZHAN", "password": "Guclu!Sifre2026"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["username"] == "oğuzhan"
        session = client.get("/api/v4/auth/session")
        assert session.status_code == 200
        assert session.json()["username"] == "oğuzhan"


def test_validation_errors_are_plain_turkish_strings(monkeypatch, tmp_path):
    import app.infra.db as db

    fresh_db = tmp_path / "v42_validation.db"
    monkeypatch.setattr(db, "DB_PATH", fresh_db)

    with TestClient(app) as client:
        response = client.post(
            "/api/v4/auth/setup",
            json={"username": "a", "password": "x", "setup_code": None},
        )
        assert response.status_code == 422
        detail = response.json().get("detail")
        assert isinstance(detail, str)
        assert "object Object" not in detail
        assert "Kullanıcı adı" in detail or "Şifre" in detail


def test_frontend_never_stringifies_fastapi_error_object():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "readableApiError" in js
    assert "Array.isArray(detail)" in js
    assert "[object Object]" not in js
    assert "authLoadingView" in html
    assert "app.js?v=14.1.2" in html
    assert "styles.css?v=14.1.2" in html


def test_uses_separate_demo_database_and_cookie():
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "14.1.2"' in config
    assert "k_risk.db" in config
    assert "k_risk_oturum" in config
