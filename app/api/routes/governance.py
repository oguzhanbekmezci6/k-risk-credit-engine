from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require
from app.api.schemas import PolicyRequest, UserCreateRequest
from app.core.config import APP_VERSION, MODEL_VERSION
from app.infra.db import audit, create_user, list_users
from app.infra.repositories import activate_policy, list_audit, list_decisions, list_policies, upsert_policy
from app.infra.security import validate_new_password

router = APIRouter(prefix="/governance", tags=["Yönetişim"])


@router.get("/policies", summary="Politikaları listele")
def policies(user=Depends(require("admin", "risk_manager", "analyst"))):
    return list_policies()


@router.post("/policies", summary="Politika kaydet")
def save_policy(req: PolicyRequest, user=Depends(require("admin"))):
    try:
        return upsert_policy(user["sub"], req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/policies/{policy_id}/activate", summary="Politikayı etkinleştir")
def activate(policy_id: str, user=Depends(require("admin"))):
    try:
        return activate_policy(user["sub"], policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/users", summary="Kullanıcı oluştur")
def add_user(req: UserCreateRequest, user=Depends(require("admin"))):
    try:
        validate_new_password(req.password)
        created = create_user(req.username, req.password, req.role, must_change_password=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(user["sub"], "kullanici_olusturuldu", "kullanici", created["username"], {"role": created["role"]})
    return created


@router.get("/users", summary="Kullanıcıları listele")
def users(user=Depends(require("admin"))):
    return list_users()


@router.get("/audit", summary="Denetim kayıtlarını getir")
def audit_log(limit: int = 100, user=Depends(require("admin", "risk_manager"))):
    return list_audit(limit)


@router.get("/decisions", summary="Karar kayıtlarını listele")
def decisions(limit: int = 50, user=Depends(require("admin", "risk_manager"))):
    return list_decisions(limit)


@router.get("/model", summary="Model yönetişimi bilgisini getir")
def model(user=Depends(require("admin", "risk_manager", "analyst"))):
    return {
        "app_version": APP_VERSION,
        "model_version": MODEL_VERSION,
        "status": "değerlendirme",
        "architecture": "deterministik karar bilimi + banka risk politikası sınırları",
        "production_note": "Canlı kredi kullanımı öncesinde kuruma özel validasyon, IAM/SSO entegrasyonu ve kurum güvenlik onayı gerekir.",
    }
