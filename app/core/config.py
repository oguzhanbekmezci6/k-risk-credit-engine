from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "K-Risk"
APP_VERSION = "14.1.2"
MODEL_VERSION = "credit-cashflow-risk-14.1.2"
DEFAULT_POLICY_VERSION = "dengeli-9.0"
API_PREFIX = "/api/v4"


def _env(name: str, default: str) -> str:
    return os.getenv(f"KRISK_{name}", default)


MODE = _env("MODE", "production").strip().lower()
if MODE not in {"demo", "production", "test"}:
    raise RuntimeError("KRISK_MODE yalnızca demo, production veya test olabilir.")

DB_PATH = Path(_env("DB_PATH", str(DATA_DIR / "k_risk.db")))
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8765"))

SESSION_IDLE_SECONDS = int(_env("SESSION_IDLE", "1800"))
SESSION_ABSOLUTE_SECONDS = int(_env("SESSION_ABSOLUTE", "28800"))
COOKIE_NAME = _env("COOKIE_NAME", "__Host-k-risk-oturum" if MODE == "production" else "k_risk_oturum")
COOKIE_SECURE = _env("COOKIE_SECURE", "true" if MODE == "production" else "false").lower() == "true"
DOCS_ENABLED = _env("DOCS_ENABLED", "false" if MODE == "production" else "true").lower() == "true"

MAX_JSON_BYTES = int(_env("MAX_JSON_BYTES", str(2 * 1024 * 1024)))

LOGIN_RATE_LIMIT = int(_env("LOGIN_RATE_LIMIT", "8"))
LOGIN_RATE_WINDOW_SECONDS = int(_env("LOGIN_RATE_WINDOW", "300"))
GLOBAL_RATE_LIMIT = int(_env("GLOBAL_RATE_LIMIT", "300"))
GLOBAL_RATE_WINDOW_SECONDS = int(_env("GLOBAL_RATE_WINDOW", "60"))

ACCOUNT_LOCK_THRESHOLD = int(_env("ACCOUNT_LOCK_THRESHOLD", "5"))
ACCOUNT_LOCK_SECONDS = int(_env("ACCOUNT_LOCK_SECONDS", "900"))

ALLOWED_ORIGINS = tuple(x.strip() for x in _env("ALLOWED_ORIGINS", "").split(",") if x.strip())
TRUSTED_HOSTS = tuple(x.strip() for x in _env("TRUSTED_HOSTS", "127.0.0.1,localhost,testserver").split(",") if x.strip())

BOOTSTRAP_TOKEN = _env("BOOTSTRAP_TOKEN", "").strip()

if SESSION_IDLE_SECONDS <= 0 or SESSION_ABSOLUTE_SECONDS <= 0 or SESSION_IDLE_SECONDS > SESSION_ABSOLUTE_SECONDS:
    raise RuntimeError("Oturum zaman aşımı değerleri geçersiz.")
if MODE == "production" and not COOKIE_SECURE:
    raise RuntimeError("Üretim modunda KRISK_COOKIE_SECURE=true zorunludur.")
if "*" in ALLOWED_ORIGINS:
    raise RuntimeError("Kimlik bilgisi taşıyan CORS yapılandırmasında '*' origin kullanılamaz.")
if MODE == "production" and "*" in TRUSTED_HOSTS:
    raise RuntimeError("Üretim modunda joker trusted host kullanılamaz.")
