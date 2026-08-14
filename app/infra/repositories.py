from __future__ import annotations

import json

from app.domain.models import Policy
from app.infra.db import audit, connect, now


def _policy_from_config(cfg: dict) -> Policy:
    tolerance = cfg.get("risk_tolerance_tl")
    raw_aversion = cfg.get("risk_aversion")
    if raw_aversion is None and tolerance:
        raw_aversion = 1.0 / float(tolerance)
    if raw_aversion is None:
        raise ValueError("risk_aversion veya risk_tolerance_tl gereklidir.")
    aversion = float(raw_aversion)
    if tolerance is not None and aversion > 0:
        implied = 1.0 / aversion
        if abs(implied - float(tolerance)) > max(1.0, implied * 1e-4):
            raise ValueError("risk_aversion ile risk_tolerance_tl birbiriyle tutarlı olmalıdır.")
    p = Policy(
        policy_id=cfg["policy_id"],
        name=cfg["name"],
        version=cfg["version"],
        status=cfg["status"],
        risk_aversion=aversion,
        limit_factors=tuple(float(x) for x in cfg["limit_factors"]),
        max_pd=float(cfg["max_pd"]),
        max_expected_loss_rate=float(cfg["max_expected_loss_rate"]),
        min_raroc=float(cfg["min_raroc"]),
        target_margin_rate=float(cfg["target_margin_rate"]),
        description=cfg.get("description", ""),
        risk_calibration_status=cfg.get("risk_calibration_status", "pilot"),
        risk_calibration_note=cfg.get("risk_calibration_note", "Demo kalibrasyonu; kurum risk komitesi onayı gerekir."),
        capital_method=cfg.get("capital_method", "analytical_credit_var"),
        capital_confidence=float(cfg.get("capital_confidence", 0.99)),
        capital_model_status=cfg.get("capital_model_status", "pilot"),
        max_debt_service_ratio=float(cfg.get("max_debt_service_ratio", 0.60)),
        affordability_status=cfg.get("affordability_status", "pilot"),
    )
    p.validate()
    return p


def get_policy(policy_id: str | None = None) -> Policy:
    con = connect()
    if policy_id:
        row = con.execute("SELECT config_json FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
    else:
        row = con.execute("SELECT config_json FROM policies WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
    con.close()
    if not row:
        raise KeyError("Politika bulunamadı.")
    return _policy_from_config(json.loads(row["config_json"]))


def list_policies() -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT policy_id,name,version,status,config_json,updated_at FROM policies ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, name"
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        cfg = json.loads(r["config_json"])
        cfg["updated_at"] = r["updated_at"]
        out.append(cfg)
    return out


def upsert_policy(actor: str, cfg: dict) -> dict:
    _policy_from_config(cfg)
    con = connect()
    exists = con.execute("SELECT 1 FROM policies WHERE policy_id=?", (cfg["policy_id"],)).fetchone()
    encoded = json.dumps(cfg, ensure_ascii=False)
    if exists:
        con.execute(
            "UPDATE policies SET name=?,version=?,status=?,config_json=?,updated_at=? WHERE policy_id=?",
            (cfg["name"], cfg["version"], cfg["status"], encoded, now(), cfg["policy_id"]),
        )
    else:
        con.execute(
            "INSERT INTO policies VALUES(?,?,?,?,?,?,?)",
            (cfg["policy_id"], cfg["name"], cfg["version"], cfg["status"], encoded, now(), now()),
        )
    con.commit()
    con.close()
    audit(actor, "politika_kaydedildi", "politika", cfg["policy_id"], {"version": cfg["version"], "status": cfg["status"]})
    return cfg


def activate_policy(actor: str, policy_id: str) -> dict:
    con = connect()
    row = con.execute("SELECT config_json FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
    if not row:
        con.close()
        raise KeyError("Politika bulunamadı.")
    con.execute("UPDATE policies SET status='challenger',updated_at=? WHERE status='active'", (now(),))
    cfg = json.loads(row["config_json"])
    cfg["status"] = "active"
    con.execute(
        "UPDATE policies SET status='active',config_json=?,updated_at=? WHERE policy_id=?",
        (json.dumps(cfg, ensure_ascii=False), now(), policy_id),
    )
    con.commit()
    con.close()
    audit(actor, "politika_etkinlestirildi", "politika", policy_id, {"version": cfg["version"]})
    return cfg


def list_audit(limit: int = 100) -> list[dict]:
    safe_limit = min(max(int(limit), 1), 500)
    con = connect()
    rows = con.execute(
        "SELECT id,at,actor,action,entity_type,entity_id,payload FROM audit_log ORDER BY at DESC LIMIT ?", (safe_limit,)
    ).fetchall()
    con.close()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def list_decisions(limit: int = 50) -> list[dict]:
    safe_limit = min(max(int(limit), 1), 200)
    con = connect()
    rows = con.execute(
        "SELECT id,at,actor,model_version,policy_id,applicant_id,result_json,override_json FROM decisions ORDER BY at DESC LIMIT ?",
        (safe_limit,),
    ).fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "at": r["at"],
            "actor": r["actor"],
            "model_version": r["model_version"],
            "policy_id": r["policy_id"],
            "applicant_id": r["applicant_id"],
            "result": json.loads(r["result_json"]),
            "override": json.loads(r["override_json"]) if r["override_json"] else None,
        }
        for r in rows
    ]


def list_decisions_for_actor(actor: str, limit: int = 50) -> list[dict]:
    safe_limit = min(max(int(limit), 1), 200)
    con = connect()
    rows = con.execute(
        "SELECT id,at,actor,model_version,policy_id,applicant_id,result_json,override_json FROM decisions WHERE actor=? ORDER BY at DESC LIMIT ?",
        (actor, safe_limit),
    ).fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "at": r["at"],
            "actor": r["actor"],
            "model_version": r["model_version"],
            "policy_id": r["policy_id"],
            "applicant_id": r["applicant_id"],
            "result": json.loads(r["result_json"]),
            "override": json.loads(r["override_json"]) if r["override_json"] else None,
        }
        for r in rows
    ]


def get_decision(decision_id: str) -> dict | None:
    if len(decision_id) > 64:
        return None
    con = connect()
    r = con.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
    con.close()
    if not r:
        return None
    return {
        "id": r["id"],
        "at": r["at"],
        "actor": r["actor"],
        "model_version": r["model_version"],
        "policy_id": r["policy_id"],
        "applicant_id": r["applicant_id"],
        "request": json.loads(r["request_json"]),
        "result": json.loads(r["result_json"]),
        "override": json.loads(r["override_json"]) if r["override_json"] else None,
    }


def override_decision(actor: str, decision_id: str, decision: str, limit: float, reason: str) -> dict:
    if decision not in {"ONAY", "REDDET"}:
        raise ValueError("İnsan kararı ONAY veya REDDET olmalıdır.")
    if not 8 <= len(reason.strip()) <= 500:
        raise ValueError("İnsan kararı gerekçesi 8-500 karakter arasında olmalıdır.")
    if not 0 <= float(limit) <= 1_000_000_000:
        raise ValueError("Limit izin verilen aralığın dışında.")
    data = {"actor": actor, "at": now(), "decision": decision, "limit": float(limit), "reason": reason.strip()}
    con = connect()
    row = con.execute("SELECT 1 FROM decisions WHERE id=?", (decision_id,)).fetchone()
    if not row:
        con.close()
        raise KeyError("Karar bulunamadı.")
    con.execute("UPDATE decisions SET override_json=? WHERE id=?", (json.dumps(data, ensure_ascii=False), decision_id))
    con.commit()
    con.close()
    audit(actor, "karar_insan_tarafindan_degistirildi", "karar", decision_id, data)
    return data
