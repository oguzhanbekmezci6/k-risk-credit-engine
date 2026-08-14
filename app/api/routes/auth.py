from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import authenticated_user
from app.api.schemas import FirstAdminSetupRequest, LoginRequest, PasswordChangeRequest
from app.core.config import BOOTSTRAP_TOKEN, COOKIE_NAME, COOKIE_SECURE, MODE, SESSION_ABSOLUTE_SECONDS
from app.infra.db import (
    audit,
    create_first_admin,
    create_session,
    get_user,
    record_failed_login,
    reset_failed_logins,
    revoke_session,
    rotate_csrf,
    update_password,
    user_count,
)
from app.infra.security import hash_password, needs_password_rehash, random_token, validate_new_password, verify_password
from app.domain.identity import normalize_username

router = APIRouter(prefix="/auth", tags=["Kimlik Doğrulama"])
_DUMMY_HASH = hash_password(random_token(24))


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=SESSION_ABSOLUTE_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


@router.get("/setup-status", summary="İlk kurulum durumunu getir")
def setup_status():
    needs_setup = user_count() == 0
    return {
        "needs_setup": needs_setup,
        "can_setup": bool(needs_setup and (MODE != "production" or BOOTSTRAP_TOKEN)),
        "requires_setup_code": bool(needs_setup and MODE == "production"),
    }


@router.post("/setup", summary="İlk yönetici hesabını oluştur")
def setup_first_admin(req: FirstAdminSetupRequest, response: Response, request: Request):
    if user_count() != 0:
        raise HTTPException(status_code=409, detail="İlk kurulum tamamlanmış. Giriş yapın veya yöneticinizden kullanıcı hesabı isteyin.")

    if MODE == "production":
        supplied = (req.setup_code or "").strip()
        if not BOOTSTRAP_TOKEN or not supplied or not hmac.compare_digest(supplied, BOOTSTRAP_TOKEN):
            raise HTTPException(status_code=403, detail="Kurulum kodu geçersiz.")
    elif MODE == "demo":
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="Demo ilk kurulumu yalnızca bu bilgisayardan yapılabilir.")

    try:
        validate_new_password(req.password)
        created = create_first_admin(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session_token, csrf_token, _ = create_session(created["username"])
    _set_session_cookie(response, session_token)
    audit(created["username"], "ilk_yonetici_hesabi_olusturuldu", "kullanici", created["username"], {"role": "admin"})
    return {
        "username": created["username"],
        "role": "admin",
        "must_change_password": False,
        "csrf_token": csrf_token,
    }


@router.post("/login", summary="Oturum aç")
def login(req: LoginRequest, response: Response):
    username = normalize_username(req.username)
    row = get_user(username)
    stored_hash = row["password_hash"] if row else _DUMMY_HASH
    password_ok = verify_password(req.password, stored_hash)

    if row and row["locked_until"] and float(row["locked_until"]) > time.time():
        audit(username, "giris_kilitli_hesap", "oturum", username, {})
        raise HTTPException(status_code=429, detail="Giriş geçici olarak sınırlandı. Daha sonra tekrar deneyin.")

    if not row or not password_ok or not bool(row["is_active"]):
        if row:
            record_failed_login(username)
        audit(username, "basarisiz_giris", "oturum", username, {})
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")

    reset_failed_logins(username)
    if needs_password_rehash(row["password_hash"]):
        update_password(username, hash_password(req.password), clear_force_change=not bool(row["must_change_password"]))

    session_token, csrf_token, _ = create_session(username)
    _set_session_cookie(response, session_token)
    audit(username, "giris_basarili", "oturum", username, {"role": row["role"]})
    return {
        "username": username,
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
        "csrf_token": csrf_token,
    }


@router.get("/session", summary="Aktif oturumu doğrula")
def session(user=Depends(authenticated_user)):
    csrf_token = rotate_csrf(user["session_token"])
    if not csrf_token:
        raise HTTPException(status_code=401, detail="Oturum geçersiz veya sona ermiş.")
    return {
        "username": user["username"],
        "role": user["role"],
        "must_change_password": user["must_change_password"],
        "csrf_token": csrf_token,
    }


@router.post("/change-password", summary="Şifre değiştir")
def change_password(req: PasswordChangeRequest, response: Response, user=Depends(authenticated_user)):
    row = get_user(user["username"])
    if not row or not verify_password(req.current_password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Mevcut şifre doğrulanamadı.")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=422, detail="Yeni şifre mevcut şifre ile aynı olamaz.")
    try:
        validate_new_password(req.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    update_password(user["username"], hash_password(req.new_password), clear_force_change=True)
    session_token, csrf_token, _ = create_session(user["username"])
    _set_session_cookie(response, session_token)
    audit(user["username"], "sifre_degistirildi", "kullanici", user["username"], {})
    return {"ok": True, "csrf_token": csrf_token, "must_change_password": False}


@router.post("/logout", summary="Oturumu kapat")
def logout(response: Response, user=Depends(authenticated_user)):
    revoke_session(user["session_token"])
    response.delete_cookie(COOKIE_NAME, path="/", secure=COOKIE_SECURE, samesite="strict")
    audit(user["username"], "oturum_kapatildi", "oturum", user["username"], {})
    return {"ok": True}
