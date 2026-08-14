from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from app.core.config import (
    ACCOUNT_LOCK_SECONDS,
    ACCOUNT_LOCK_THRESHOLD,
    BOOTSTRAP_TOKEN,
    DB_PATH,
    MODE,
    MODEL_VERSION,
    SESSION_ABSOLUTE_SECONDS,
)
from app.infra.security import hash_password, random_token, token_hash
from app.domain.identity import normalize_username


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


DEFAULT_POLICIES = [
    {
        "policy_id": "muhafazakar",
        "name": "Muhafazakâr",
        "version": "9.0",
        "status": "challenger",
        "limit_factors": [0, .25, .50, .75, 1.0],
        "max_pd": .14,
        "max_expected_loss_rate": .10,
        "min_raroc": .12,
        "target_margin_rate": .020,
        "description": "Daha sıkı risk iştahı ile sermayeyi korumaya odaklı strateji.",
        "risk_tolerance_tl": 66666.6667,
        "risk_calibration_status": "pilot",
        "risk_calibration_note": "Başlangıç risk toleransı demo kalibrasyonudur; canlı kullanım öncesi Risk Komitesi/Model Validasyon onayı zorunludur.",
        "capital_method": "analytical_credit_var",
        "capital_confidence": 0.99,
        "capital_model_status": "pilot",
        "max_debt_service_ratio": 0.60,
        "affordability_status": "pilot",
    },
    {
        "policy_id": "dengeli",
        "name": "Dengeli",
        "version": "9.0",
        "status": "active",
        "limit_factors": [0, .25, .50, .75, 1.0],
        "max_pd": .18,
        "max_expected_loss_rate": .17,
        "min_raroc": .08,
        "target_margin_rate": .015,
        "description": "Risk ile ekonomik getiriyi birlikte optimize eden ana strateji.",
        "risk_tolerance_tl": 125000.0,
        "risk_calibration_status": "pilot",
        "risk_calibration_note": "Başlangıç risk toleransı demo kalibrasyonudur; canlı kullanım öncesi Risk Komitesi/Model Validasyon onayı zorunludur.",
        "capital_method": "analytical_credit_var",
        "capital_confidence": 0.99,
        "capital_model_status": "pilot",
        "max_debt_service_ratio": 0.60,
        "affordability_status": "pilot",
    },
    {
        "policy_id": "buyume",
        "name": "Büyüme",
        "version": "9.0",
        "status": "challenger",
        "limit_factors": [0, .25, .50, .75, 1.0],
        "max_pd": .24,
        "max_expected_loss_rate": .22,
        "min_raroc": .05,
        "target_margin_rate": .010,
        "description": "Açık risk sınırları içinde daha yüksek onay oranına odaklı strateji.",
        "risk_tolerance_tl": 333333.3333,
        "risk_calibration_status": "pilot",
        "risk_calibration_note": "Başlangıç risk toleransı demo kalibrasyonudur; canlı kullanım öncesi Risk Komitesi/Model Validasyon onayı zorunludur.",
        "capital_method": "analytical_credit_var",
        "capital_confidence": 0.99,
        "capital_model_status": "pilot",
        "max_debt_service_ratio": 0.60,
        "affordability_status": "pilot",
    },
]


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_user_columns(con: sqlite3.Connection) -> None:
    cols = _column_names(con, "users")
    additions = {
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "must_change_password": "INTEGER NOT NULL DEFAULT 0",
        "failed_attempts": "INTEGER NOT NULL DEFAULT 0",
        "locked_until": "REAL",
        "password_changed_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in cols:
            con.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")


def ensure_schema() -> None:
    con = connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until REAL,
            password_changed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions(
            id_hash TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            csrf_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
        CREATE TABLE IF NOT EXISTS audit_log(
            id TEXT PRIMARY KEY,
            at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decisions(
            id TEXT PRIMARY KEY,
            at TEXT NOT NULL,
            actor TEXT NOT NULL,
            model_version TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            applicant_id TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            override_json TEXT
        );
        CREATE TABLE IF NOT EXISTS policies(
            policy_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    _ensure_user_columns(con)
    con.commit()
    con.close()


def create_user(username: str, password: str, role: str, must_change_password: bool = True) -> dict:
    username = normalize_username(username)
    if role not in {"admin", "risk_manager", "analyst"}:
        raise ValueError("Geçersiz rol.")
    con = connect()
    try:
        con.execute(
            "INSERT INTO users(id,username,password_hash,role,created_at,is_active,must_change_password,failed_attempts,locked_until,password_changed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), username, hash_password(password), role, now(), 1, int(must_change_password), 0, None, None),
        )
        con.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu kullanıcı adı zaten mevcut.") from exc
    finally:
        con.close()
    return {"username": username, "role": role, "must_change_password": bool(must_change_password)}


def user_count() -> int:
    con = connect()
    count = int(con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
    con.close()
    return count


def create_first_admin(username: str, password: str) -> dict:
    """İlk hesabı atomik olarak oluşturur; ikinci bir ilk-kurulum yarışını engeller."""
    username = normalize_username(username)
    password_hash = hash_password(password)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        count = int(con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
        if count != 0:
            con.rollback()
            raise ValueError("İlk kurulum tamamlanmış. Yeni kullanıcıları Yönetici ekranından oluşturun.")
        con.execute(
            "INSERT INTO users(id,username,password_hash,role,created_at,is_active,must_change_password,failed_attempts,locked_until,password_changed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), username, password_hash, "admin", now(), 1, 0, 0, None, now()),
        )
        con.commit()
    finally:
        con.close()
    return {"username": username, "role": "admin", "must_change_password": False}


def list_users() -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT username,role,created_at,is_active,must_change_password,failed_attempts,locked_until FROM users ORDER BY created_at"
    ).fetchall()
    con.close()
    current = time.time()
    return [
        {
            "username": r["username"],
            "role": r["role"],
            "created_at": r["created_at"],
            "is_active": bool(r["is_active"]),
            "must_change_password": bool(r["must_change_password"]),
            "locked": bool(r["locked_until"] and float(r["locked_until"]) > current),
        }
        for r in rows
    ]


def init_db() -> None:
    ensure_schema()
    con = connect()
    for p in DEFAULT_POLICIES:
        if not con.execute("SELECT 1 FROM policies WHERE policy_id=?", (p["policy_id"],)).fetchone():
            con.execute(
                "INSERT INTO policies VALUES(?,?,?,?,?,?,?)",
                (p["policy_id"], p["name"], p["version"], p["status"], json.dumps(p, ensure_ascii=False), now(), now()),
            )
    con.commit()
    current_user_count = int(con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
    con.close()
    if MODE == "production" and current_user_count == 0 and not BOOTSTRAP_TOKEN:
        raise RuntimeError(
            "Üretim modunda ilk hesap oluşturmak için KRISK_BOOTSTRAP_TOKEN zorunludur. "
            "Tek kullanımlık bir kurulum kodu tanımlayıp uygulamayı yeniden başlatın."
        )


def audit(actor: str, action: str, entity_type: str, entity_id: str, payload: dict) -> None:
    safe_actor = (actor or "bilinmiyor")[:64]
    safe_action = (action or "bilinmiyor")[:80]
    safe_type = (entity_type or "bilinmiyor")[:80]
    safe_id = (entity_id or "-")[:128]
    con = connect()
    con.execute(
        "INSERT INTO audit_log VALUES(?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), now(), safe_actor, safe_action, safe_type, safe_id, json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def get_user(username: str):
    con = connect()
    row = con.execute("SELECT * FROM users WHERE username=?", (normalize_username(username),)).fetchone()
    con.close()
    return row


def record_failed_login(username: str) -> None:
    con = connect()
    row = con.execute("SELECT failed_attempts FROM users WHERE username=?", (username,)).fetchone()
    if row:
        attempts = int(row["failed_attempts"]) + 1
        locked_until = time.time() + ACCOUNT_LOCK_SECONDS if attempts >= ACCOUNT_LOCK_THRESHOLD else None
        con.execute("UPDATE users SET failed_attempts=?,locked_until=? WHERE username=?", (attempts, locked_until, username))
        con.commit()
    con.close()


def reset_failed_logins(username: str) -> None:
    con = connect()
    con.execute("UPDATE users SET failed_attempts=0,locked_until=NULL WHERE username=?", (username,))
    con.commit()
    con.close()


def update_password(username: str, new_hash: str, clear_force_change: bool = True) -> None:
    con = connect()
    con.execute(
        "UPDATE users SET password_hash=?,must_change_password=?,failed_attempts=0,locked_until=NULL,password_changed_at=? WHERE username=?",
        (new_hash, 0 if clear_force_change else 1, now(), username),
    )
    con.execute("DELETE FROM sessions WHERE username=?", (username,))
    con.commit()
    con.close()


def create_session(username: str) -> tuple[str, str, float]:
    session_token = random_token(32)
    csrf_token = random_token(32)
    ts = time.time()
    expires = ts + SESSION_ABSOLUTE_SECONDS
    con = connect()
    con.execute(
        "INSERT INTO sessions(id_hash,username,csrf_hash,created_at,last_seen,expires_at) VALUES(?,?,?,?,?,?)",
        (token_hash(session_token), username, token_hash(csrf_token), ts, ts, expires),
    )
    con.commit()
    con.close()
    return session_token, csrf_token, expires


def rotate_csrf(session_token: str) -> str | None:
    csrf = random_token(32)
    con = connect()
    cur = con.execute("UPDATE sessions SET csrf_hash=? WHERE id_hash=?", (token_hash(csrf), token_hash(session_token)))
    con.commit()
    changed = cur.rowcount
    con.close()
    return csrf if changed else None


def revoke_session(session_token: str) -> None:
    con = connect()
    con.execute("DELETE FROM sessions WHERE id_hash=?", (token_hash(session_token),))
    con.commit()
    con.close()


def revoke_all_sessions(username: str) -> None:
    con = connect()
    con.execute("DELETE FROM sessions WHERE username=?", (username,))
    con.commit()
    con.close()


def save_decision(actor: str, policy_id: str, applicant_id: str, request: dict, result: dict) -> str:
    did = str(uuid.uuid4())
    con = connect()
    con.execute(
        "INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)",
        (did, now(), actor, MODEL_VERSION, policy_id, applicant_id, json.dumps(request, ensure_ascii=False), json.dumps(result, ensure_ascii=False), None),
    )
    con.commit()
    con.close()
    audit(actor, "karar_olusturuldu", "karar", did, {"applicant_id": applicant_id, "policy_id": policy_id})
    return did

