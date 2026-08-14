from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.config import MODE
from app.core.formatting import tr_money, tr_number, tr_percent_ratio
from app.decision.capital import analytical_credit_var_capital
from app.decision.banking_policy import (
    daily_banking_checks,
    effective_debt_service_ratio_limit,
    housing_ltv_reference,
    market_snapshot,
    vehicle_loan_reference,
)
from app.decision.loan_economics import cashflow_economics, horizon_pd, solve_break_even_annual_rate, twelve_month_pd
from app.decision.science import (
    certainty_equivalent,
    decision_analysis,
    evaluate_actions,
    normalize_probabilities,
    utility,
)
from app.domain.models import Applicant, Policy

STATES = ("ödeyen", "gecikmiş", "temerrüt")
DEFAULT_SIGNAL = {
    "name": "Varsayımsal ek bilgi sinyali (simülasyon)",
    "source_mode": "simulation",
    "source_note": "Gerçek kredi bürosu verisi değildir; örnek olabilirlik matrisiyle yalnız bilgi değeri hesaplanır.",
    "cost": 350.0,
    "signal_names": ["yeşil", "sarı", "kırmızı"],
    "signal_given_state": [[0.78, 0.18, 0.04], [0.30, 0.52, 0.18], [0.08, 0.27, 0.65]],
}


@dataclass(frozen=True)
class Scenario:
    name: str
    pd_mult: float = 1.0
    lgd_mult: float = 1.0
    funding_add: float = 0.0


SCENARIOS = (
    Scenario("baz"),
    Scenario("yavaslama", 1.45, 1.10, .015),
    Scenario("agir_stres", 2.20, 1.25, .035),
)


def _policy_governance(policy: Policy) -> dict:
    return {
        "risk_calibration_status": policy.risk_calibration_status,
        "risk_calibration_note": policy.risk_calibration_note,
        "risk_tolerance_tl": (1.0 / policy.risk_aversion) if policy.risk_aversion > 0 else None,
        "capital_method": policy.capital_method,
        "capital_confidence": policy.capital_confidence,
        "capital_model_status": policy.capital_model_status,
        "max_debt_service_ratio": policy.max_debt_service_ratio,
        "affordability_status": policy.affordability_status,
    }


def _enforce_production_governance(policy: Policy) -> None:
    """Production'da kalibrasyonsuz parametrelerin sessizce karar vermesini engeller."""
    if MODE != "production":
        return
    if policy.risk_calibration_status != "approved":
        raise ValueError(
            "Aktif politikanın risk toleransı kurum tarafından onaylanmamış. "
            "Production kredi kararı için risk_calibration_status=approved zorunludur."
        )
    if policy.capital_model_status != "approved":
        raise ValueError(
            "Aktif politikanın ekonomik sermaye yöntemi kurum tarafından onaylanmamış. "
            "Production kredi kararı için capital_model_status=approved zorunludur."
        )
    if policy.affordability_status != "approved":
        raise ValueError(
            "Aktif politikanın ödeme gücü eşiği kurum tarafından onaylanmamış. "
            "Production kredi kararı için affordability_status=approved zorunludur."
        )


def _base_probabilities(a: Applicant, scenario: Scenario) -> list[float]:
    input_pd = min(.999, max(1e-6, a.pd * scenario.pd_mult))
    term_default, _ = horizon_pd(input_pd, a.pd_basis, a.term_months)
    late = min(.95, a.late_probability)
    if term_default + late >= .999:
        late = max(0.0, .999 - term_default)
    good = max(0.0, 1.0 - term_default - late)
    return [good, late, term_default]


def state_economics(
    a: Applicant,
    limit: float,
    scenario: Scenario,
    state_probabilities: Sequence[float] | None = None,
    policy: Policy | None = None,
) -> dict:
    probs = normalize_probabilities(state_probabilities or _base_probabilities(a, scenario))
    good, late, term_pd = probs
    lgd = min(1.0, max(0.0, a.lgd * scenario.lgd_mult))
    confidence = policy.capital_confidence if policy else .99
    cap_status = policy.capital_model_status if policy else "pilot"
    if limit <= 0:
        return {
            "limit": 0.0,
            "probabilities": probs,
            "payoffs": [0.0, 0.0, 0.0],
            "expected_profit": 0.0,
            "cashflow_expected_contribution": 0.0,
            "expected_npv": 0.0,
            "expected_npv_12m": 0.0,
            "expected_loss": 0.0,
            "expected_loss_12m": 0.0,
            "expected_loss_rate": 0.0,
            "expected_loss_rate_12m": 0.0,
            "unexpected_loss": 0.0,
            "recovery_rate": 1.0 - lgd,
            "credit_var": 0.0,
            "economic_capital": 0.0,
            "economic_capital_method": "Uygulanmaz (REDDET)",
            "economic_capital_confidence": confidence,
            "capital_model_status": cap_status,
            "raroc": 0.0,
            "break_even_rate": 0.0,
            "posterior_pd": term_pd,
            "posterior_pd_12m": twelve_month_pd(term_pd, "lifetime", a.term_months),
            "posterior_late_probability": late,
            "loan_economics": {"term_months": a.term_months, "schedule": [], "monthly_payment": 0.0},
            "banking_checks": {"checks": [], "hard_failures": [], "debt_service_ratio": None},
        }

    funding = a.funding_cost + scenario.funding_add
    # Posterior/stres olasılıkları kredi vadesi ufkuna aittir; nakit akış motoruna lifetime PD olarak verilir.
    econ = cashflow_economics(
        principal=limit,
        annual_rate=a.annual_rate,
        funding_cost=funding,
        term_months=a.term_months,
        repayment_type=a.repayment_type,
        pd=term_pd,
        pd_basis="lifetime",
        lgd=lgd,
        ead_factor=a.ead_factor,
        late_probability=late,
        late_loss_rate=a.late_loss_rate,
        operating_cost=a.operating_cost,
        upfront_fee=a.upfront_fee,
        capital_cost_rate=a.capital_cost_rate,
        capital_confidence=confidence,
        capital_model_status=cap_status,
        bsmv_rate=a.bsmv_rate,
        kkdf_rate=a.kkdf_rate,
        recovery_lag_months=a.recovery_lag_months,
        funding_method=a.funding_method,
    )
    pd_12m = econ["pd_12m_for_capital"]
    ead0 = limit * a.ead_factor
    cap = analytical_credit_var_capital(pd_12m, lgd, ead0, confidence, cap_status)
    checks = daily_banking_checks(
        product_type=a.product_type,
        proposed_limit=limit,
        requested_term_months=a.term_months,
        collateral_value=a.collateral_value,
        collateral_energy_class=a.collateral_energy_class,
        housing_has_other_home=a.housing_has_other_home,
        applicant_age_years=a.applicant_age_years,
        vehicle_is_used=a.vehicle_is_used,
        vehicle_age_years=a.vehicle_age_years,
        monthly_net_income=a.monthly_net_income,
        existing_monthly_debt_service=a.existing_monthly_debt_service,
        proposed_monthly_payment=econ.get("max_contractual_payment", econ["monthly_payment"]),
        internal_max_debt_service_ratio=policy.max_debt_service_ratio if policy else .60,
    )
    break_even = None
    return {
        "limit": limit,
        "probabilities": probs,
        "payoffs": econ["state_payoffs"],
        "expected_profit": econ["state_expected_profit"],
        "cashflow_expected_contribution": econ["lifetime_expected_contribution"],
        "expected_npv": econ["expected_npv"],
        "expected_npv_12m": econ["expected_npv_12m"],
        "expected_loss": econ["expected_loss_lifetime"],
        "expected_loss_12m": econ["expected_loss_12m"],
        "expected_loss_rate": econ["expected_loss_lifetime"] / max(ead0, 1.0),
        "expected_loss_rate_12m": econ["expected_loss_12m"] / max(ead0, 1.0),
        "unexpected_loss": cap.unexpected_loss,
        "recovery_rate": 1.0 - lgd,
        "credit_var": cap.credit_var,
        "economic_capital": econ["average_economic_capital_12m"],
        "economic_capital_method": "K-Risk pilot 12 aylık analitik Credit VaR − EL sermaye profili",
        "economic_capital_confidence": confidence,
        "capital_model_status": cap_status,
        "raroc": max(-10.0, min(10.0, econ["annualized_raroc"])),
        "break_even_rate": break_even,
        "posterior_pd": term_pd,
        "posterior_pd_12m": pd_12m,
        "posterior_late_probability": late,
        "effective_lgd": lgd,
        "loan_economics": econ,
        "banking_checks": checks,
    }


def _apply_policy_constraints(action: dict, policy: Policy, *, economic_guardrails_binding: bool) -> dict:
    factor = action["factor"]
    feasible = True
    failed: list[str] = []
    advisory: list[str] = []
    if factor > 0 and action["posterior_pd_12m"] > policy.max_pd:
        feasible = False
        failed.append("12 aylık PD üst sınırı")
    if factor > 0 and action["expected_loss_rate_12m"] > policy.max_expected_loss_rate:
        feasible = False
        failed.append("12 aylık beklenen kayıp oranı üst sınırı")

    raroc_fail = factor > 0 and action["raroc"] < policy.min_raroc
    if raroc_fail:
        if economic_guardrails_binding:
            feasible = False
            failed.append("asgari RAROC")
        else:
            advisory.append("pilot RAROC eşiğinin altında")

    floor = action.get("pricing_floor_rate") if factor > 0 else 0.0
    floor_fail = factor > 0 and (floor is None or action.get("current_rate", 0.0) + 1e-12 < floor)
    if floor_fail:
        label = "fiyat tabanı hesaplanamadı" if floor is None else "pilot fiyat tabanının altında"
        if economic_guardrails_binding:
            feasible = False
            failed.append("politika fiyat tabanı hesaplanamadı" if floor is None else "politika fiyat tabanı")
        else:
            advisory.append(label)

    if factor > 0 and action.get("banking_checks", {}).get("hard_failures"):
        feasible = False
        failed.extend(action["banking_checks"]["hard_failures"])
    action["feasible"] = feasible
    action["failed_constraints"] = list(dict.fromkeys(failed))
    action["advisory_findings"] = list(dict.fromkeys(advisory))
    action["economic_guardrails_binding"] = bool(economic_guardrails_binding)
    if factor == 0:
        action["pricing_floor_status"] = "UYGULANMAZ"
    elif floor is None:
        action["pricing_floor_status"] = "FAIL" if economic_guardrails_binding else "UYARI"
    elif action.get("current_rate", 0.0) + 1e-12 >= floor:
        action["pricing_floor_status"] = "PASS"
    else:
        action["pricing_floor_status"] = "FAIL" if economic_guardrails_binding else "UYARI"
    action["raroc_status"] = "PASS" if not raroc_fail else ("FAIL" if economic_guardrails_binding else "UYARI")
    return action


def _action_for_limit(
    a: Applicant,
    policy: Policy,
    probabilities: Sequence[float],
    scenario: Scenario,
    limit: float,
    *,
    factor: float | None = None,
    label: str | None = None,
    is_dynamic: bool = False,
) -> dict:
    """Tek bir limit için ekonomi ve politika sonucunu üretir."""
    limit = max(0.0, min(float(limit), float(a.requested_amount)))
    if factor is None:
        factor = (limit / a.requested_amount) if a.requested_amount > 0 else 0.0
    e = state_economics(a, limit, scenario, probabilities, policy)
    e["factor"] = float(factor)
    e["action"] = label or ("REDDET" if limit <= 0 else f"ONAY {factor:.0%}")
    e["current_rate"] = a.annual_rate
    e["is_dynamic"] = bool(is_dynamic)
    if limit > 0:
        e["break_even_rate"] = solve_break_even_annual_rate(
            principal=e["limit"],
            funding_cost=a.funding_cost + scenario.funding_add,
            term_months=a.term_months,
            repayment_type=a.repayment_type,
            pd=e["posterior_pd"],
            pd_basis="lifetime",
            lgd=e.get("effective_lgd", a.lgd),
            ead_factor=a.ead_factor,
            late_probability=e["posterior_late_probability"],
            late_loss_rate=a.late_loss_rate,
            operating_cost=a.operating_cost,
            upfront_fee=a.upfront_fee,
            capital_cost_rate=a.capital_cost_rate,
            capital_confidence=policy.capital_confidence,
            capital_model_status=policy.capital_model_status,
            bsmv_rate=a.bsmv_rate,
            kkdf_rate=a.kkdf_rate,
            recovery_lag_months=a.recovery_lag_months,
            funding_method=a.funding_method,
        )
        e["pricing_floor_rate"] = None if e["break_even_rate"] is None else max(e["break_even_rate"] + policy.target_margin_rate, 0.0)
    else:
        e["break_even_rate"] = 0.0
        e["pricing_floor_rate"] = 0.0
    # The embedded economic profile uses a public TCMB deposit-rate proxy, not a real
    # bank treasury FTP. Until centrally approved economics/FTP are connected, RAROC
    # and pricing-floor results remain advisory and must not create false credit rejects.
    funding_method_lc = (a.funding_method or "").lower()
    economic_guardrails_binding = (
        a.parameter_status == "approved"
        and "proxy" not in funding_method_lc
        and "vekil" not in funding_method_lc
        and "değildir" not in funding_method_lc
    )
    return _apply_policy_constraints(e, policy, economic_guardrails_binding=economic_guardrails_binding)


def _dynamic_limit_upper_bound(a: Applicant, policy: Policy, requested_action: dict) -> tuple[float, list[str]]:
    requested = max(0.0, float(a.requested_amount))
    upper = requested
    binding: list[str] = []
    if requested <= 0:
        return 0.0, binding

    if a.product_type == "ihtiyac":
        if a.term_months > 36:
            return 0.0, ["BDDK tüketici kredisi vade sınırı"]
        if a.term_months > 24:
            upper = min(upper, 125_000.0)
            binding.append("BDDK tüketici kredisi vade sınırı")
        elif a.term_months > 12:
            upper = min(upper, 250_000.0)
            binding.append("BDDK tüketici kredisi vade sınırı")

    if a.product_type == "tasit":
        if a.collateral_value <= 0:
            return 0.0, ["taşıt fatura/kasko değeri eksik"]
        ref = vehicle_loan_reference(a.collateral_value)
        if not ref.get("available"):
            return 0.0, ["Güncel standart taşıt kredisi araç değer bandı"]
        if a.term_months > int(ref["max_term_months"]):
            return 0.0, ["Güncel taşıt azami vade sınırı"]
        if a.vehicle_is_used:
            if a.vehicle_age_years <= 0:
                return 0.0, ["2. el taşıt yaşı eksik"]
            if a.vehicle_age_years > 10:
                return 0.0, ["Güncel 2. el taşıt azami yaş sınırı"]
            if a.vehicle_age_years * 12 + a.term_months > 144:
                return 0.0, ["Güncel 2. el taşıt yaş + vade sınırı"]
        max_loan = float(ref["max_loan"])
        if max_loan < upper:
            upper = max(0.0, max_loan)
            binding.append("Güncel taşıt kredi/değer sınırı")

    if a.product_type == "konut":
        if a.applicant_age_years <= 0:
            return 0.0, ["konut başvuran yaşı eksik"]
        if a.applicant_age_years * 12 + a.term_months > 70 * 12:
            return 0.0, ["Güncel konut yaş + vade sınırı"]
        if a.term_months > 120:
            return 0.0, ["Güncel konut azami vade sınırı"]
        upper = min(upper, 20_000_000.0)
        if requested > 20_000_000.0:
            binding.append("Güncel konut azami kredi tutarı")
        if a.collateral_value <= 0:
            return 0.0, ["konut ekspertiz/teminat değeri eksik"]
        ref = housing_ltv_reference(a.collateral_value, a.collateral_energy_class, a.housing_has_other_home)
        max_loan = ref.get("max_loan")
        if max_loan is not None and float(max_loan) < upper:
            upper = max(0.0, float(max_loan))
            binding.append("BDDK konut kredi/değer oranı referansı")

    if a.monthly_net_income > 0:
        effective_dsr, _, _ = effective_debt_service_ratio_limit(a.product_type, policy.max_debt_service_ratio)
        capacity = a.monthly_net_income * effective_dsr - a.existing_monthly_debt_service
        if capacity <= 0:
            return 0.0, list(dict.fromkeys(binding + ["kurum borç ödeme kapasitesi sınırı"]))
        full_peak_payment = float((requested_action.get("loan_economics") or {}).get("max_contractual_payment") or 0.0)
        if full_peak_payment > capacity + 1e-9 and full_peak_payment > 0:
            affordability_limit = requested * capacity / full_peak_payment
            if affordability_limit < upper:
                upper = max(0.0, affordability_limit)
                binding.append("kurum borç ödeme kapasitesi sınırı")

    return max(0.0, min(requested, upper)), list(dict.fromkeys(binding))


def _dynamic_limit_candidate(
    a: Applicant,
    policy: Policy,
    probabilities: Sequence[float],
    scenario: Scenario,
    static_actions: list[dict],
) -> dict | None:
    """Miktara bağlı tüm kontrolleri yeniden çalıştırarak en yüksek uygun limiti arar."""
    requested = float(a.requested_amount)
    if requested <= 0:
        return None
    requested_action = next((x for x in static_actions if abs(x.get("limit", 0.0) - requested) <= 1e-6), None)
    if requested_action is None:
        requested_action = _action_for_limit(a, policy, probabilities, scenario, requested, factor=1.0, label="ONAY 100%")

    upper, binding = _dynamic_limit_upper_bound(a, policy, requested_action)
    if upper <= 0:
        return None

    upper_action = _action_for_limit(
        a, policy, probabilities, scenario, upper,
        factor=upper / requested, label="ONAY · DİNAMİK LİMİT", is_dynamic=True,
    )
    upper_action["dynamic_binding_constraints"] = binding
    if upper_action["feasible"]:
        if upper < requested - max(1.0, requested * 1e-8):
            return upper_action
        return None

    # PD ve EL oranı aynı sözleşme yapısında limit küçülünce iyileşmez.
    fatal = {"12 aylık PD üst sınırı", "12 aylık beklenen kayıp oranı üst sınırı", "konut ekspertiz/teminat değeri eksik", "taşıt fatura/kasko değeri eksik", "Güncel standart taşıt kredisi araç değer bandı", "Güncel taşıt azami vade sınırı", "Güncel konut azami vade sınırı"}
    if fatal.intersection(upper_action.get("failed_constraints") or []):
        return None

    # RAROC/fiyat tabanı sabit maliyet ve ücretler nedeniyle limite bağlıdır. Bu yüzden
    # üst sınırdan aşağı tarama yapılır; ilk uygun aralık daha sonra ikili aramayla sıkıştırılır.
    ratios = [1.0 - i / 24 for i in range(1, 24)]
    ratios += [0.03, 0.02, 0.01, 0.005, 0.001, 0.0001]
    ratios = sorted({r for r in ratios if 0 < r < 1}, reverse=True)
    higher_limit = upper
    feasible_action = None
    for ratio in ratios:
        trial_limit = upper * ratio
        if trial_limit <= 0:
            continue
        trial = _action_for_limit(
            a, policy, probabilities, scenario, trial_limit,
            factor=trial_limit / requested, label="ONAY · DİNAMİK LİMİT", is_dynamic=True,
        )
        trial["dynamic_binding_constraints"] = binding
        if trial["feasible"]:
            feasible_action = trial
            break
        higher_limit = trial_limit

    if feasible_action is None:
        return None

    low = feasible_action["limit"]
    high = higher_limit
    best = feasible_action
    if high <= low:
        high = min(upper, low * 1.10)
    tolerance = max(1.0, requested * 1e-6)
    for _ in range(18):
        if high - low <= tolerance:
            break
        mid = (low + high) / 2.0
        trial = _action_for_limit(
            a, policy, probabilities, scenario, mid,
            factor=mid / requested, label="ONAY · DİNAMİK LİMİT", is_dynamic=True,
        )
        trial["dynamic_binding_constraints"] = binding
        if trial["feasible"]:
            low = mid
            best = trial
        else:
            high = mid
    return best


def _actions_for_probabilities(
    a: Applicant,
    policy: Policy,
    probabilities: Sequence[float],
    scenario: Scenario = SCENARIOS[0],
) -> list[dict]:
    out: list[dict] = []
    for factor in policy.limit_factors:
        out.append(_action_for_limit(
            a,
            policy,
            probabilities,
            scenario,
            a.requested_amount * factor,
            factor=factor,
            label="REDDET" if factor == 0 else f"ONAY {factor:.0%}",
        ))

    dynamic = _dynamic_limit_candidate(a, policy, probabilities, scenario, out)
    if dynamic is not None:
        # Aynı limite denk gelen sabit aksiyon varsa ikinci kez ekleme.
        if not any(abs(x["limit"] - dynamic["limit"]) <= max(1.0, a.requested_amount * 1e-7) for x in out):
            out.append(dynamic)
    return out

def _select_risk_adjusted(actions: list[dict], probabilities: Sequence[float], policy: Policy, *, force_utility: bool = False) -> tuple[int, dict]:
    payoffs = [x["payoffs"] for x in actions]
    util = evaluate_actions(payoffs, probabilities, "exponential", policy.risk_aversion)
    feasible_idx = [i for i, x in enumerate(actions) if x["feasible"]]
    if not feasible_idx:
        feasible_idx = [0]
    economics_binding = any(bool(x.get("economic_guardrails_binding")) for x in actions if x.get("factor", 0) > 0)
    if economics_binding or force_utility:
        selected = max(feasible_idx, key=lambda i: util["expected_utility"][i])
        selection_mode = "risk_adjusted_utility" if economics_binding else "risk_adjusted_utility_diagnostic"
    else:
        # Public proxy economics are not bank FTP. In pilot mode choose the largest
        # limit that passed credit/regulatory/affordability hard controls; economics
        # remain visible as advisory diagnostics.
        selected = max(feasible_idx, key=lambda i: actions[i].get("limit", 0.0))
        selection_mode = "max_hard_control_feasible_limit"
    for i, x in enumerate(actions):
        x["expected_utility"] = util["expected_utility"][i]
        x["certainty_equivalent"] = util["certainty_equivalent"][i]
        x["risk_premium"] = util["risk_premium"][i]
        x["selection_mode"] = selection_mode
    util["selection_mode"] = selection_mode
    return selected, util


def _posterior_for_signal(prior: Sequence[float], likelihood_rows: Sequence[Sequence[float]], k: int) -> tuple[float, list[float]]:
    prior_n = normalize_probabilities(prior)
    likes = [normalize_probabilities(row) for row in likelihood_rows]
    ps = sum(prior_n[s] * likes[s][k] for s in range(len(prior_n)))
    if ps <= 0:
        return 0.0, [0.0 for _ in prior_n]
    return ps, [prior_n[s] * likes[s][k] / ps for s in range(len(prior_n))]


def _risk_adjusted_evsi(a: Applicant, policy: Policy, prior: Sequence[float], signal: dict) -> dict:
    matrix = signal["signal_given_state"]
    if len(matrix) != len(prior):
        raise ValueError("Bilgi sinyalinde her doğa durumu için bir olabilirlik satırı olmalıdır.")
    if not matrix or not matrix[0]:
        raise ValueError("Bilgi sinyali matrisi boş olamaz.")
    n_signals = len(matrix[0])
    if any(len(row) != n_signals for row in matrix):
        raise ValueError("Bilgi sinyali olabilirlik matrisi dikdörtgen olmalıdır.")
    names = list(signal.get("signal_names") or [f"S{i+1}" for i in range(n_signals)])
    if len(names) != n_signals:
        raise ValueError("Sinyal adları ile olabilirlik matrisi boyutu eşleşmiyor.")

    base_actions = _actions_for_probabilities(a, policy, prior)
    base_idx, base_util = _select_risk_adjusted(base_actions, prior, policy, force_utility=True)
    base_eu = base_util["expected_utility"][base_idx]
    base_ce = base_actions[base_idx]["certainty_equivalent"]

    total_eu_after = 0.0
    details = []
    for k, name in enumerate(names):
        ps, posterior = _posterior_for_signal(prior, matrix, k)
        if ps <= 0:
            details.append({"signal": name, "probability": 0.0, "posterior_states": posterior, "best_action_index": 0, "best_action": "REDDET", "best_value": 0.0, "certainty_equivalent": 0.0, "feasible_actions": ["REDDET"], "failed_constraints": {}})
            continue
        post_actions = _actions_for_probabilities(a, policy, posterior)
        idx, util = _select_risk_adjusted(post_actions, posterior, policy, force_utility=True)
        total_eu_after += ps * util["expected_utility"][idx]
        details.append({
            "signal": name,
            "probability": ps,
            "posterior_states": posterior,
            "posterior_pd": posterior[2],
            "posterior_late_probability": posterior[1],
            "best_action_index": idx,
            "best_action": post_actions[idx]["action"],
            "best_value": post_actions[idx]["certainty_equivalent"],
            "certainty_equivalent": post_actions[idx]["certainty_equivalent"],
            "feasible_actions": [x["action"] for x in post_actions if x["feasible"]],
            "failed_constraints": {x["action"]: x["failed_constraints"] for x in post_actions if x["failed_constraints"]},
        })
    ce_after = certainty_equivalent(total_eu_after, "exponential", policy.risk_aversion, [x for a0 in base_actions for x in a0["payoffs"]])
    evsi_value = max(0.0, ce_after - base_ce)
    return {
        "criterion": "risk_adjusted_certainty_equivalent",
        "policy_reapplied_after_signal": True,
        "base_action": base_actions[base_idx]["action"],
        "base_expected_utility": base_eu,
        "base_certainty_equivalent": base_ce,
        "expected_utility_with_sample_information": total_eu_after,
        "certainty_equivalent_with_sample_information": ce_after,
        "evsi": evsi_value,
        "signals": details,
    }


def _risk_adjusted_evpi(a: Applicant, policy: Policy, prior: Sequence[float]) -> dict:
    base_actions = _actions_for_probabilities(a, policy, prior)
    base_idx, base_util = _select_risk_adjusted(base_actions, prior, policy, force_utility=True)
    base_ce = base_actions[base_idx]["certainty_equivalent"]
    perfect_eu = 0.0
    details = []
    for state_index, state_name in enumerate(STATES):
        posterior = [0.0] * len(STATES)
        posterior[state_index] = 1.0
        actions = _actions_for_probabilities(a, policy, posterior)
        idx, util = _select_risk_adjusted(actions, posterior, policy, force_utility=True)
        perfect_eu += prior[state_index] * util["expected_utility"][idx]
        details.append({
            "state": state_name,
            "probability": prior[state_index],
            "best_action": actions[idx]["action"],
            "certainty_equivalent": actions[idx]["certainty_equivalent"],
            "feasible_actions": [x["action"] for x in actions if x["feasible"]],
        })
    ce_perfect = certainty_equivalent(perfect_eu, "exponential", policy.risk_aversion, [x for a0 in base_actions for x in a0["payoffs"]])
    return {
        "criterion": "risk_adjusted_certainty_equivalent",
        "policy_reapplied_under_perfect_information": True,
        "base_certainty_equivalent": base_ce,
        "certainty_equivalent_with_perfect_information": ce_perfect,
        "evpi": max(0.0, ce_perfect - base_ce),
        "states": details,
    }


def _requested_policy_controls(requested_action: dict, policy: Policy) -> list[dict]:
    controls = [
        {
            "code": "POLICY_PD_12M",
            "name": "12 aylık PD üst sınırı",
            "status": "PASS" if requested_action["posterior_pd_12m"] <= policy.max_pd else "FAIL",
            "actual": requested_action["posterior_pd_12m"],
            "limit": policy.max_pd,
            "unit": "oran",
            "source": "Kurum kredi politikası",
        },
        {
            "code": "POLICY_EL_12M",
            "name": "12 aylık beklenen zarar oranı",
            "status": "PASS" if requested_action["expected_loss_rate_12m"] <= policy.max_expected_loss_rate else "FAIL",
            "actual": requested_action["expected_loss_rate_12m"],
            "limit": policy.max_expected_loss_rate,
            "unit": "oran",
            "source": "Kurum kredi politikası",
        },
        {
            "code": "POLICY_RAROC",
            "name": "Asgari Pilot RAROC",
            "status": requested_action.get("raroc_status", "PASS"),
            "actual": requested_action["raroc"],
            "limit": policy.min_raroc,
            "unit": "oran",
            "source": "Kurum ekonomik politikası · pilot kamu fonlama vekilinde danışma amaçlı",
        },
        {
            "code": "POLICY_PRICING_FLOOR",
            "name": "Politika fiyat tabanı",
            "status": requested_action.get("pricing_floor_status", "PASS"),
            "actual": requested_action.get("current_rate", 0.0),
            "limit": requested_action.get("pricing_floor_rate", 0.0),
            "unit": "oran",
            "source": "K-Risk ekonomik fiyatlama · gerçek banka FTP bağlanana kadar danışma amaçlı",
        },
    ]
    for chk in (requested_action.get("banking_checks") or {}).get("checks") or []:
        c = dict(chk)
        if c.get("status") != "PASS":
            c["status"] = "FAIL"
        controls.append(c)
    return controls


def _primary_failure(failures: Sequence[str]) -> str | None:
    ordered = [
        "konut ekspertiz/teminat değeri eksik",
        "BDDK tüketici kredisi vade sınırı",
        "BDDK konut kredi/değer oranı referansı",
        "kurum borç ödeme kapasitesi sınırı",
        "politika fiyat tabanı hesaplanamadı",
        "politika fiyat tabanı",
        "asgari pilot RAROC",
        "12 aylık PD üst sınırı",
        "12 aylık beklenen kayıp oranı üst sınırı",
    ]
    fs = list(failures)
    for item in ordered:
        if item in fs:
            return item
    return fs[0] if fs else None


def _data_quality_warnings(a: Applicant) -> list[dict]:
    warnings: list[dict] = []
    annual_income = a.monthly_net_income * 12.0
    if a.requested_amount > 0 and annual_income <= 0:
        warnings.append({"code":"MISSING_AFFORDABILITY_BASE","severity":"high","message":"Aylık net gelir/nakit akışı 0. Ödeme gücü girdisini doğrulayın."})
    elif annual_income > 0:
        ratio = a.requested_amount / annual_income
        if ratio >= 10:
            warnings.append({"code":"REQUEST_TO_ANNUAL_INCOME_EXTREME","severity":"high","ratio":ratio,"message":f"Talep tutarı yıllık net gelir/nakit akışının {tr_number(ratio, 1)} katı. Girdileri doğrulayın."})
        elif ratio >= 5:
            warnings.append({"code":"REQUEST_TO_ANNUAL_INCOME_HIGH","severity":"medium","ratio":ratio,"message":f"Talep tutarı yıllık net gelir/nakit akışının {tr_number(ratio, 1)} katı. Girdileri kontrol edin."})
    if a.existing_monthly_debt_service > a.monthly_net_income > 0:
        warnings.append({"code":"EXISTING_DEBT_SERVICE_ABOVE_INCOME","severity":"high","message":"Mevcut aylık borç servisi aylık net geliri aşıyor."})
    if a.product_type == "konut" and a.collateral_value <= 0:
        warnings.append({"code":"HOUSING_COLLATERAL_MISSING","severity":"high","message":"Konut kredisi için ekspertiz/teminat değeri girilmelidir."})
    if a.product_type == "tasit" and a.collateral_value <= 0:
        warnings.append({"code":"VEHICLE_VALUE_MISSING","severity":"high","message":"Taşıt kredisi için fatura/kasko değeri girilmelidir."})
    if a.parameter_status != "approved":
        warnings.append({"code":"PUBLIC_FUNDING_PROXY_NON_BINDING","severity":"medium","message":"RAROC ve fiyat tabanı kamuya açık fonlama vekiliyle hesaplanıyor; gerçek banka FTP bağlanana kadar otomatik ret sebebi değildir."})
    if a.requested_amount > 0 and a.upfront_fee / a.requested_amount >= .10:
        warnings.append({"code":"UPFRONT_FEE_HIGH","severity":"high","message":"Peşin ücret/komisyon talep tutarının %10 veya üzerinde. Girdiyi doğrulayın."})
    elif a.requested_amount > 0 and a.upfront_fee / a.requested_amount >= .05:
        warnings.append({"code":"UPFRONT_FEE_ELEVATED","severity":"medium","message":"Peşin ücret/komisyon talep tutarına göre yüksek görünüyor."})
    if a.annual_rate == 0:
        warnings.append({"code":"ZERO_CUSTOMER_RATE","severity":"medium","message":"Müşteri faiz oranı %0. Fiyatlama girdisini doğrulayın."})
    if a.lgd == 0:
        warnings.append({"code":"ZERO_LGD","severity":"medium","message":"LGD %0. Risk girdisinin kaynağını doğrulayın."})
    if a.product_type == "spot" and a.repayment_type != "bullet":
        warnings.append({"code":"SPOT_REPAYMENT_MISMATCH","severity":"medium","message":"Spot ürün seçildi ancak geri ödeme yapısı vade sonu anapara değil."})
    return warnings


def evaluate_credit(a: Applicant, policy: Policy, signal: dict | None = DEFAULT_SIGNAL) -> dict:
    a.validate()
    policy.validate()
    _enforce_production_governance(policy)

    probs = _base_probabilities(a, SCENARIOS[0])
    decision_candidates = _actions_for_probabilities(a, policy, probs)
    selected, util = _select_risk_adjusted(decision_candidates, probs, policy)
    feasible_idx = [i for i, x in enumerate(decision_candidates) if x["feasible"]] or [0]
    risk_neutral = max(feasible_idx, key=lambda i: decision_candidates[i]["expected_profit"])
    chosen = decision_candidates[selected]

    requested_action = next(
        (x for x in decision_candidates if abs(x.get("limit", 0.0) - a.requested_amount) <= max(1e-6, a.requested_amount * 1e-9)),
        None,
    )
    if requested_action is None:
        requested_action = _action_for_limit(a, policy, probs, SCENARIOS[0], a.requested_amount, factor=1.0, label="ONAY 100%")
    request_failures = list(requested_action.get("failed_constraints") or [])

    names = [x["action"] for x in decision_candidates]
    payoffs = [x["payoffs"] for x in decision_candidates]
    classic_science = decision_analysis(names, STATES, payoffs, probs)
    ra_evpi = _risk_adjusted_evpi(a, policy, probs)

    stress = []
    for sc in SCENARIOS:
        sp = _base_probabilities(a, sc)
        scenario_actions = _actions_for_probabilities(a, policy, sp, sc)
        idx, _ = _select_risk_adjusted(scenario_actions, sp, policy)
        stress.append({
            "scenario": sc.name,
            "recommended_limit": scenario_actions[idx]["limit"],
            "decision": "REDDET" if scenario_actions[idx]["limit"] == 0 else "ONAY",
            "expected_profit": scenario_actions[idx]["expected_profit"],
            "expected_loss": scenario_actions[idx]["expected_loss"],
            "posterior_pd": scenario_actions[idx]["posterior_pd"],
            "pd_multiplier": sc.pd_mult,
            "lgd_multiplier": sc.lgd_mult,
            "funding_add": sc.funding_add,
        })

    info = None
    if signal:
        info = _risk_adjusted_evsi(a, policy, probs, signal)
        info["name"] = signal.get("name", "Ek bilgi sinyali")
        info["cost"] = float(signal.get("cost", 0))
        info["net_value"] = info["evsi"] - info["cost"]
        info["source_mode"] = str(signal.get("source_mode", "simulation"))
        info["source_note"] = str(
            signal.get(
                "source_note",
                "Bu bilgi kaynağı için yalnız hesaplama yapılır; sistem satın al/alma önerisi üretmez.",
            )
        )
        info["is_simulation"] = info["source_mode"] == "simulation"
        info["action_recommendation"] = None
        signal_actions = {x.get("best_action") for x in info.get("signals") or [] if x.get("probability", 0) > 0}
        if info["evsi"] <= 1e-6:
            if len(signal_actions) <= 1:
                blocking = [x for x in request_failures if x not in {"12 aylık PD üst sınırı", "12 aylık beklenen kayıp oranı üst sınırı"}]
                if blocking:
                    info["interpretation"] = "Ek risk bilgisi kararı değiştirmiyor; " + ", ".join(blocking[:3]) + " devam ediyor."
                else:
                    info["interpretation"] = "Ek bilgi mevcut politika altında seçilen kredi aksiyonunu değiştirmiyor; hesaplanan karar değeri 0 TL'dir."
            else:
                info["interpretation"] = "Sinyaller bazı ara sonuçları değiştirse de risk-ayarlı kesinlik eşdeğerinde ek parasal değer üretmiyor."
        else:
            info["interpretation"] = "Ek bilgi, bazı sinyal sonuçlarında uygulanabilir aksiyonu veya risk-ayarlı değerlemeyi değiştiriyor."
        if info["evsi"] > ra_evpi["evpi"] + 1e-6:
            raise RuntimeError("Bilgi değeri tutarlılık ihlali: EVSI, EVPI değerini aşıyor.")

    robust = len({round(float(x["recommended_limit"]), 2) for x in stress}) == 1
    all_reject = all(float(x["recommended_limit"]) <= 0 for x in stress)
    robustness_label = "TÜM SENARYOLARDA REDDET" if all_reject else ("KARAR DEĞİŞMEDİ" if robust else "HASSAS")

    pricing_floor = chosen.get("pricing_floor_rate") if chosen["limit"] > 0 else None
    governance = _policy_governance(policy)
    max_feasible_limit = max((float(x["limit"]) for x in decision_candidates if x.get("feasible") and x.get("limit", 0) > 0), default=0.0)
    primary_failure = _primary_failure(request_failures)
    secondary_failures = [x for x in request_failures if x != primary_failure]
    full_request_feasible = bool(requested_action.get("feasible"))

    if chosen["limit"] <= 0:
        decision_label = "REDDET"
    elif chosen["limit"] < a.requested_amount - max(1.0, a.requested_amount * 1e-7):
        decision_label = "KISMİ ONAY"
    else:
        decision_label = "ONAY"

    if full_request_feasible:
        decision_summary = f"Talep edilen {tr_money(a.requested_amount)} tutar politika kontrollerini geçti."
    elif chosen["limit"] > 0:
        reason_text = primary_failure or "politika sınırları"
        decision_summary = (
            f"Talep edilen {tr_money(a.requested_amount)}, {reason_text} nedeniyle tam olarak uygun değil. "
            f"Bağlayıcı kredi, mevzuat ve ödeme gücü kontrolleri altında {tr_money(chosen['limit'])} limit önerildi."
        )
    else:
        reason_text = primary_failure or "politika ve ekonomik eşikler"
        decision_summary = (
            f"Talep edilen {tr_money(a.requested_amount)}, {reason_text} nedeniyle uygun değil. "
            "Mevcut politika altında pozitif onay limiti bulunamadı."
        )

    explanation = [
        decision_summary,
        f"{policy.name} {policy.version} politikası sabit limit aksiyonlarına ek olarak dinamik uygulanabilir limit sınırını da değerlendirdi.",
        f"Başvuru PD girdisi {tr_percent_ratio(a.pd, 2)}; 12 aylık politika PD'si {tr_percent_ratio(requested_action['posterior_pd_12m'], 2)}, vade PD'si {tr_percent_ratio(requested_action['posterior_pd'], 2)} olarak hesaplandı.",
    ]
    if request_failures:
        explanation.append("Talep edilen tutarı engelleyen kontroller: " + "; ".join(request_failures) + ".")
    if chosen["limit"] > 0:
        explanation.append(
            f"Seçilen limit {tr_money(chosen['limit'])}; ilk taksit {tr_money(chosen.get('loan_economics', {}).get('monthly_payment', 0))}, "
            f"beklenen ekonomik NPV {tr_money(chosen['expected_npv'])} ve beklenen kayıp {tr_money(chosen['expected_loss'])}."
        )
    else:
        explanation.append("REDDET aksiyonu kredi kullandırımı yaratmadığından seçilen aksiyon için taksit, NPV ve EL sıfırları başvuru risk metriği olarak yorumlanmaz.")
    explanation.extend([
        f"Risk-nötr seçim {decision_candidates[risk_neutral]['action']}; fayda ile risk ayarlı seçim {chosen['action']}.",
        f"Risk toleransı {tr_money(governance['risk_tolerance_tl'])}; kalibrasyon durumu {policy.risk_calibration_status}.",
        f"Karar dayanıklılığı: {robustness_label}.",
    ])
    if max_feasible_limit > 0 and max_feasible_limit < a.requested_amount - 1:
        explanation.append(f"Politika içinde bulunan maksimum uygulanabilir pozitif limit yaklaşık {tr_money(max_feasible_limit)}'dir.")
    if info:
        kaynak = "simülasyon" if info.get("is_simulation") else info.get("source_mode", "tanımlı")
        explanation.append(
            f"{info['name']} için risk-ayarlı EVSI {tr_money(info['evsi'])}, maliyet {tr_money(info['cost'])}, "
            f"net fark {tr_money(info['net_value'])}. Kaynak modu: {kaynak}. {info.get('interpretation', '')}"
        )

    trace = [
        {"step": 1, "stage": "dogrulama", "detail": "Başvuru girdileri deterministik doğrulamadan ve veri kalitesi uyarılarından geçti."},
        {"step": 2, "stage": "nakit_akisi", "detail": "Ürün vergi/fon profiliyle aylık anapara-faiz-BSMV-KKDF-bakiye planı oluşturuldu."},
        {"step": 3, "stage": "ekonomi", "detail": "Ödeyen/gecikmiş/temerrüt durumları tek olasılık sistemi altında birleştirildi; workout fonlama süresi dahil edildi."},
        {"step": 4, "stage": "risk_sinirlari", "detail": "PD, beklenen zarar, Pilot RAROC, fiyat tabanı, ödeme gücü ve tanımlı mevzuat referansları talep edilen tutara uygulandı."},
        {"step": 5, "stage": "dinamik_limit", "detail": "Miktara bağlı kontroller yeniden çalıştırılarak en yüksek uygun limit arandı."},
        {"step": 6, "stage": "karar_bilimi", "detail": "Uygulanabilir adaylar üstel fayda ve risk toleransı ile sıralandı; risk-ayarlı EVPI aynı kriterle hesaplandı."},
        {"step": 7, "stage": "stres", "detail": "Karar yavaşlama ve ağır stres senaryolarında dinamik limit dahil yeniden değerlendirildi."},
        {"step": 8, "stage": "bilgi_degeri", "detail": "Her sinyal sonrası Bayes posterioru ile politika guardrail'leri yeniden uygulandı ve risk-ayarlı EVSI hesaplandı."},
    ]

    requested_loan = requested_action.get("loan_economics") or {}
    requested_pricing = {
        "current_rate": a.annual_rate,
        "break_even_rate": requested_action.get("break_even_rate", 0.0),
        "risk_adjusted_floor_rate": requested_action.get("pricing_floor_rate", 0.0),
        "margin_to_floor": None if requested_action.get("pricing_floor_rate") is None else a.annual_rate - float(requested_action.get("pricing_floor_rate")),
        "floor_status": requested_action.get("pricing_floor_status", "PASS"),
    }
    requested_economics = {
        "expected_profit": requested_action["expected_profit"],
        "expected_npv": requested_action["expected_npv"],
        "expected_npv_12m": requested_action["expected_npv_12m"],
        "expected_loss": requested_action["expected_loss"],
        "expected_loss_12m": requested_action["expected_loss_12m"],
        "expected_loss_rate": requested_action["expected_loss_rate"],
        "expected_loss_rate_12m": requested_action["expected_loss_rate_12m"],
        "raroc": requested_action["raroc"],
        "economic_capital": requested_action["economic_capital"],
    }

    legacy_actions = [x for x in decision_candidates if not x.get("is_dynamic")]
    policy_controls = _requested_policy_controls(requested_action, policy)

    return {
        "applicant": a.asdict(),
        "policy": policy.asdict(),
        "policy_governance": governance,
        "selection_mode": chosen.get("selection_mode"),
        "market_context": market_snapshot(a.product_type, a.term_months),
        "banking_checks": chosen.get("banking_checks") if chosen["limit"] > 0 else requested_action.get("banking_checks"),
        "policy_controls": policy_controls,
        "loan_economics": chosen.get("loan_economics"),
        "decision": "REDDET" if chosen["limit"] == 0 else "ONAY",
        "decision_label": decision_label,
        "decision_summary": decision_summary,
        "primary_reason": primary_failure,
        "secondary_reasons": secondary_failures,
        "request_failures": request_failures,
        "requested_amount_feasible": full_request_feasible,
        "recommended_limit": chosen["limit"],
        "recommended_limit_factor": chosen["factor"],
        "max_feasible_limit": max_feasible_limit,
        "risk_neutral_limit": decision_candidates[risk_neutral]["limit"],
        "application_risk": {
            "input_pd": a.pd,
            "pd_basis": a.pd_basis,
            "pd_12m": requested_action["posterior_pd_12m"],
            "term_pd": requested_action["posterior_pd"],
            "lgd": requested_action.get("effective_lgd", a.lgd),
        },
        "requested_scenario": {
            "limit": a.requested_amount,
            "feasible": requested_action.get("feasible"),
            "failed_constraints": request_failures,
            "loan_economics": requested_loan,
            "economics": requested_economics,
            "pricing": requested_pricing,
        },
        "data_quality_warnings": _data_quality_warnings(a),
        "pricing": {
            "applicable": chosen["limit"] > 0,
            "current_rate": a.annual_rate,
            "break_even_rate": chosen["break_even_rate"] if chosen["limit"] > 0 else None,
            "risk_adjusted_floor_rate": pricing_floor if chosen["limit"] > 0 else None,
            "margin_to_floor": (a.annual_rate - pricing_floor) if chosen["limit"] > 0 and pricing_floor is not None else None,
            "floor_status": chosen.get("pricing_floor_status") if chosen["limit"] > 0 else "UYGULANMAZ",
            "target_margin_rate": policy.target_margin_rate,
        },
        "economics": {
            "applicable": chosen["limit"] > 0,
            "expected_profit": chosen["expected_profit"],
            "cashflow_expected_contribution": chosen["cashflow_expected_contribution"],
            "expected_npv": chosen["expected_npv"],
            "expected_npv_12m": chosen["expected_npv_12m"],
            "expected_loss": chosen["expected_loss"],
            "expected_loss_12m": chosen["expected_loss_12m"],
            "expected_loss_rate": chosen["expected_loss_rate"],
            "expected_loss_rate_12m": chosen["expected_loss_rate_12m"],
            "unexpected_loss": chosen["unexpected_loss"],
            "recovery_rate": chosen["recovery_rate"],
            "credit_var": chosen["credit_var"],
            "economic_capital": chosen["economic_capital"],
            "economic_capital_method": chosen["economic_capital_method"],
            "economic_capital_confidence": chosen["economic_capital_confidence"],
            "capital_model_status": chosen["capital_model_status"],
            "raroc": chosen["raroc"],
            "raroc_label": "K-Risk Pilot RAROC",
            "certainty_equivalent": chosen["certainty_equivalent"],
            "risk_premium": chosen["risk_premium"],
        },
        "robustness": {"stable_across_scenarios": robust, "label": robustness_label, "scenarios": stress},
        "information_value": info,
        "decision_science": {
            "maximin": classic_science["metrics"]["maximin"],
            "maximax": classic_science["metrics"]["maximax"],
            "minimax_regret": classic_science["metrics"]["minimax_regret"],
            "expected_value": classic_science["metrics"]["expected_value"],
            "expected_regret": classic_science["metrics"]["expected_regret"],
            "evpi": ra_evpi["evpi"],
            "evpi_method": ra_evpi["criterion"],
            "evpi_details": ra_evpi,
            "classical_risk_neutral_evpi": classic_science["metrics"]["evpi"],
        },
        # Geriye dönük API uyumluluğu: eski sabit politika aksiyonları aynı alanda kalır.
        "actions": legacy_actions,
        "decision_candidates": decision_candidates,
        "explanation": explanation,
        "trace": trace,
    }

