from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import require
from app.api.schemas import DecisionRequest, OverrideRequest
from app.infra.repositories import get_decision, list_decisions, list_decisions_for_actor, override_decision
from app.infra.db import audit
from app.services.report_service import build_decision_pdf, report_filename
from app.services.decision_service import make_decision

router = APIRouter(prefix="/decision", tags=["Kredi Kararı"])


@router.post("/evaluate", summary="Kredi kararını değerlendir")
def evaluate(req: DecisionRequest, user=Depends(require("admin", "risk_manager", "analyst"))):
    try:
        return make_decision(req.model_dump(), user["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/history", summary="Görülebilir karar geçmişini getir")
def history(limit: int = 50, user=Depends(require("admin", "risk_manager", "analyst"))):
    if user["role"] == "analyst":
        return list_decisions_for_actor(user["sub"], limit)
    return list_decisions(limit)


@router.get("/{decision_id}", summary="Karar kaydını getir")
def read_decision(decision_id: str, user=Depends(require("admin", "risk_manager", "analyst"))):
    result = get_decision(decision_id)
    if not result:
        raise HTTPException(status_code=404, detail="Karar bulunamadı.")
    if user["role"] == "analyst" and result["actor"] != user["sub"]:
        # Nesne varlığını dahi ifşa etme.
        raise HTTPException(status_code=404, detail="Karar bulunamadı.")
    return result


@router.get("/{decision_id}/report.pdf", summary="Karar Nasıl Alındı? PDF raporunu indir")
def decision_report(decision_id: str, user=Depends(require("admin", "risk_manager"))):
    result = get_decision(decision_id)
    if not result:
        raise HTTPException(status_code=404, detail="Karar bulunamadı.")
    try:
        pdf = build_decision_pdf(result, user["sub"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Karar raporu oluşturulamadı.") from exc
    audit(user["sub"], "karar_raporu_indirildi", "karar", decision_id, {"applicant_id": result["applicant_id"]})
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report_filename(result)}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{decision_id}/override", summary="Yetkili insan kararıyla geçersiz kıl")
def manual_override(decision_id: str, req: OverrideRequest, user=Depends(require("admin", "risk_manager"))):
    try:
        return override_decision(user["sub"], decision_id, req.decision, req.limit, req.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
