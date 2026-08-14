import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = ROOT / "data" / "test_k_risk.db"

# Uygulama modülleri import edilmeden önce güvenli test ortamı sabitlenir.
os.environ["KRISK_MODE"] = "test"
os.environ["KRISK_DB_PATH"] = str(TEST_DB)
os.environ["KRISK_COOKIE_SECURE"] = "false"
os.environ["KRISK_LOGIN_RATE_LIMIT"] = "100"
os.environ["KRISK_GLOBAL_RATE_LIMIT"] = "5000"
os.environ["KRISK_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"

import pytest


@pytest.fixture(scope="session", autouse=True)
def clean_test_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    from app.infra.db import create_user, ensure_schema

    ensure_schema()
    create_user("admin_test", "Q7!mR2#vL9@pT4", "admin", must_change_password=False)
    create_user("risk_test", "Z8@kN3!sP6#uW2", "risk_manager", must_change_password=False)
    create_user("analist_a", "H4#qT9@bV2!mK7", "analyst", must_change_password=False)
    create_user("analist_b", "J6!xC3#nR8@wP5", "analyst", must_change_password=False)
    create_user("lock_test", "L5@vD8!qS2#zM7", "analyst", must_change_password=False)
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()
