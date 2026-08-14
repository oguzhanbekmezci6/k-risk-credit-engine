from __future__ import annotations

from app.core.config import MODEL_VERSION
from app.decision.credit import evaluate_credit
from app.decision.economic_profiles import (
    default_customer_annual_nominal_rate,
    default_purpose,
    default_repayment_source,
    economic_profile_for,
)
from app.domain.models import Applicant
from app.infra.db import save_decision
from app.infra.repositories import get_policy

# These legacy client fields are intentionally ignored. Economic/risk operating parameters
# are centrally assigned from the product profile instead of being freely editable by analysts.
_INTERNAL_PROFILE_FIELDS = {
    "funding_cost",
    "funding_method",
    "operating_cost",
    "capital_cost_rate",
    "ead_factor",
    "late_probability",
    "late_loss_rate",
    "recovery_lag_months",
    "bsmv_rate",
    "kkdf_rate",
    "tax_status",
    "tax_note",
    "parameter_status",
    "segment",
}


def make_decision(payload: dict, actor: str) -> dict:
    payload = dict(payload)
    policy = get_policy(payload.pop("policy_id", None))
    signal = payload.pop("information_signal", None)

    for key in _INTERNAL_PROFILE_FIELDS:
        payload.pop(key, None)

    product_type = payload.get("product_type", "ihtiyac")
    housing_bsmv_exempt = bool(payload.get("housing_bsmv_exempt", False))
    profile = economic_profile_for(product_type, housing_bsmv_exempt=housing_bsmv_exempt)
    if payload.get("annual_rate") is None:
        payload["annual_rate"] = default_customer_annual_nominal_rate(product_type, int(payload.get("term_months") or 12))

    payload["loan_purpose"] = (payload.get("loan_purpose") or default_purpose(product_type)).strip()
    payload["repayment_source"] = (payload.get("repayment_source") or default_repayment_source(product_type)).strip()
    payload.update(profile.asdict())

    applicant = Applicant(**payload)
    result = evaluate_credit(applicant, policy, signal=signal if signal is not None else None)
    result["model_version"] = MODEL_VERSION
    result["economic_profile"] = profile.asdict()
    request = {**applicant.asdict(), "policy_id": policy.policy_id, "information_signal": signal}
    result["decision_id"] = save_decision(actor, policy.policy_id, applicant.applicant_id, request, result)
    return result
