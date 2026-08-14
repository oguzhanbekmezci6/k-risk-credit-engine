from __future__ import annotations

import hmac
import time
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from app.core.config import COOKIE_NAME, SESSION_IDLE_SECONDS
from app.infra.db import connect, revoke_session
from app.infra.security import token_hash

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _session_user(request: Request, csrf_token: str | None, allow_forced_password_change: bool) -> dict[str, Any]:
    raw_session = request.cookies.get(COOKIE_NAME)
    if not raw_session or len(raw_session) > 256:
        raise HTTPException(status_code=401, detail="Oturum gerekli.")

    session_hash = token_hash(raw_session)
    con = connect()
    row = con.execute(
        """
        SELECT s.id_hash,s.username,s.csrf_hash,s.created_at,s.last_seen,s.expires_at,
               u.role,u.is_active,u.must_change_password,u.locked_until
        FROM sessions s
        JOIN users u ON u.username=s.username
        WHERE s.id_hash=?
        """,
        (session_hash,),
    ).fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=401, detail="Oturum geçersiz veya sona ermiş.")

    now_ts = time.time()
    expired = row["expires_at"] <= now_ts or (now_ts - row["last_seen"]) > SESSION_IDLE_SECONDS
    disabled = not bool(row["is_active"])
    if expired or disabled:
        con.execute("DELETE FROM sessions WHERE id_hash=?", (session_hash,))
        con.commit()
        con.close()
        raise HTTPException(status_code=401, detail="Oturum geçersiz veya sona ermiş.")

    if request.method.upper() in UNSAFE_METHODS:
        if not csrf_token or len(csrf_token) > 256 or not hmac.compare_digest(token_hash(csrf_token), row["csrf_hash"]):
            con.close()
            raise HTTPException(status_code=403, detail="CSRF doğrulaması başarısız.")

    con.execute("UPDATE sessions SET last_seen=? WHERE id_hash=?", (now_ts, session_hash))
    con.commit()
    con.close()

    if bool(row["must_change_password"]) and not allow_forced_password_change:
        raise HTTPException(status_code=403, detail="Devam etmek için geçici şifrenizi değiştirmeniz gerekiyor.")

    return {
        "sub": row["username"],
        "username": row["username"],
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
        "session_token": raw_session,
    }


def authenticated_user(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    return _session_user(request, x_csrf_token, allow_forced_password_change=True)


def current_user(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    return _session_user(request, x_csrf_token, allow_forced_password_change=False)


def require(*roles: str):
    def dep(user=Depends(current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz bulunmuyor.")
        return user

    return dep
