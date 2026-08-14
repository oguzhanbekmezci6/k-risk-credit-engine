import json

from fastapi import APIRouter, Depends

from app.api.deps import require
from app.core.config import APP_VERSION, MODEL_VERSION
from app.infra.db import connect
from app.infra.repositories import get_policy

router = APIRouter(prefix="/overview", tags=["Genel Bakış"])


def _decision_scope(user: dict) -> tuple[str, tuple]:
    if user["role"] == "analyst":
        return " WHERE actor=?", (user["sub"],)
    return "", ()


@router.get("", summary="Genel bakış verisini getir")
def overview(user=Depends(require("admin", "risk_manager", "analyst"))):
    con = connect()
    where, params = _decision_scope(user)

    decisions = con.execute(f"SELECT COUNT(*) n FROM decisions{where}", params).fetchone()["n"]
    approved = con.execute(
        f"SELECT COUNT(*) n FROM decisions{where}{' AND' if where else ' WHERE'} json_extract(result_json,'$.decision')='ONAY'",
        params,
    ).fetchone()["n"]
    rejected = con.execute(
        f"SELECT COUNT(*) n FROM decisions{where}{' AND' if where else ' WHERE'} json_extract(result_json,'$.decision')='REDDET'",
        params,
    ).fetchone()["n"]
    sensitive = con.execute(
        f"SELECT COUNT(*) n FROM decisions{where}{' AND' if where else ' WHERE'} json_extract(result_json,'$.robustness.stable_across_scenarios')=0",
        params,
    ).fetchone()["n"]

    if user["role"] == "analyst":
        recent_rows = con.execute(
            "SELECT id,at,actor,applicant_id,result_json,override_json FROM decisions WHERE actor=? ORDER BY at DESC LIMIT 5",
            (user["sub"],),
        ).fetchall()
    else:
        recent_rows = con.execute(
            "SELECT id,at,actor,applicant_id,result_json,override_json FROM decisions ORDER BY at DESC LIMIT 5"
        ).fetchall()
    con.close()

    policy = get_policy()
    recent = []
    for row in recent_rows:
        result = json.loads(row["result_json"])
        override = json.loads(row["override_json"]) if row["override_json"] else None
        recent.append(
            {
                "id": row["id"],
                "at": row["at"],
                "actor": row["actor"],
                "applicant_id": row["applicant_id"],
                "decision": override["decision"] if override else result.get("decision"),
                "decision_label": override["decision"] if override else result.get("decision_label", result.get("decision")),
                "recommended_limit": override["limit"] if override else result.get("recommended_limit", 0),
                "stable": result.get("robustness", {}).get("stable_across_scenarios"),
                "robustness_label": result.get("robustness", {}).get("label"),
                "policy_name": result.get("policy", {}).get("name", policy.name),
            }
        )

    return {
        "app_version": APP_VERSION,
        "model_version": MODEL_VERSION,
        "active_policy": policy.asdict(),
        "decision_count": decisions,
        "approved_count": approved,
        "rejected_count": rejected,
        "sensitive_count": sensitive,
        "recent_decisions": recent,
    }
