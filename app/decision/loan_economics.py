from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.decision.capital import analytical_credit_var_capital

RepaymentType = Literal["equal_installment", "equal_principal", "bullet"]
PDBasis = Literal["annual_12m", "lifetime"]


@dataclass(frozen=True)
class ScheduleRow:
    period: int
    opening_balance: float
    payment: float
    interest: float
    bsmv: float
    kkdf: float
    taxes_and_funds: float
    principal: float
    closing_balance: float
    funding_cost: float
    expected_default_probability: float
    survival_probability_start: float
    expected_loss: float
    expected_interest_income: float
    expected_funding_cost: float
    economic_capital: float
    capital_cost: float

    def asdict(self) -> dict:
        return asdict(self)


def monthly_rate_from_annual_nominal(annual_rate: float) -> float:
    if annual_rate < 0:
        raise ValueError("Yıllık nominal oran negatif olamaz.")
    return annual_rate / 12.0


def present_value(amount: float, monthly_discount_rate: float, period: int) -> float:
    if period < 0:
        raise ValueError("İskonto dönemi negatif olamaz.")
    if monthly_discount_rate < 0:
        raise ValueError("İskonto oranı negatif olamaz.")
    if period == 0 or amount == 0:
        return amount
    return amount / ((1.0 + monthly_discount_rate) ** period)


def annuity_payment(principal: float, monthly_rate: float, months: int) -> float:
    if principal < 0:
        raise ValueError("Anapara negatif olamaz.")
    if months < 1:
        raise ValueError("Vade en az 1 ay olmalıdır.")
    if monthly_rate < 0:
        raise ValueError("Aylık faiz negatif olamaz.")
    if principal == 0:
        return 0.0
    if abs(monthly_rate) < 1e-15:
        return principal / months
    growth = (1.0 + monthly_rate) ** months
    return principal * monthly_rate * growth / (growth - 1.0)


def _constant_monthly_hazard(pd: float, months_for_pd: int) -> float:
    if not 0 <= pd <= 1:
        raise ValueError("PD 0 ile 1 arasında olmalıdır.")
    if months_for_pd < 1:
        raise ValueError("PD ufku en az 1 ay olmalıdır.")
    if pd == 0:
        return 0.0
    if pd == 1:
        return 1.0
    return 1.0 - (1.0 - pd) ** (1.0 / months_for_pd)


def horizon_pd(pd: float, basis: PDBasis, term_months: int) -> tuple[float, float]:
    """Return (term PD, monthly hazard).

    annual_12m is extended with a constant monthly hazard. lifetime is interpreted as
    the probability for the stated contractual term. This is a transparent pilot
    transformation; a bank implementation should replace it with an approved marginal
    PD term structure.
    """
    if term_months < 1:
        raise ValueError("Vade en az 1 ay olmalıdır.")
    if basis == "annual_12m":
        h = _constant_monthly_hazard(pd, 12)
        term = 1.0 - (1.0 - h) ** term_months
    elif basis == "lifetime":
        h = _constant_monthly_hazard(pd, term_months)
        term = pd
    else:
        raise ValueError("PD ufku annual_12m veya lifetime olmalıdır.")
    return min(term, 0.999999), h


def twelve_month_pd(pd: float, basis: PDBasis, term_months: int) -> float:
    _, h = horizon_pd(pd, basis, term_months)
    months = min(term_months, 12)
    return min(0.999999, 1.0 - (1.0 - h) ** months)


def optimum_term_indicator(monthly_rate: float, max_months: int = 600) -> dict:
    """Geçer (2014) literature indicator; not a lending recommendation."""
    if monthly_rate <= 0:
        return {
            "available": False,
            "months": None,
            "method": "Ödeme değişimi = dönemsel faiz oranı",
            "note": "Sıfır faizli kredide bu optimum-vade göstergesi tanımlı değildir.",
        }
    if monthly_rate >= 1:
        return {
            "available": False,
            "months": None,
            "method": "Ödeme değişimi = dönemsel faiz oranı",
            "note": "Dönemsel faiz %100 veya üzerindeyken gösterge hesaplanmaz.",
        }
    prev_payment = annuity_payment(1.0, monthly_rate, 1)
    prev_delta = None
    for months in range(2, max_months + 1):
        payment = annuity_payment(1.0, monthly_rate, months)
        delta = abs(payment - prev_payment) / prev_payment
        if delta <= monthly_rate:
            if prev_delta is None or abs(prev_delta - delta) < 1e-15:
                estimate = float(months)
            else:
                fraction = (prev_delta - monthly_rate) / (prev_delta - delta)
                estimate = (months - 1) + max(0.0, min(1.0, fraction))
            return {
                "available": True,
                "months": estimate,
                "method": "|T(v+1)-T(v)| / T(v) = dönemsel faiz oranı",
                "note": "Literatür göstergesidir; kurum vade politikası veya tahsis önerisi değildir.",
            }
        prev_delta = delta
        prev_payment = payment
    return {
        "available": False,
        "months": None,
        "method": "|T(v+1)-T(v)| / T(v) = dönemsel faiz oranı",
        "note": f"{max_months} aya kadar eşik bulunamadı.",
    }


def build_contractual_schedule(
    principal: float,
    annual_rate: float,
    funding_cost: float,
    term_months: int,
    repayment_type: RepaymentType = "equal_installment",
    bsmv_rate: float = 0.0,
    kkdf_rate: float = 0.0,
) -> list[dict]:
    """Build a tax/fund-aware contractual schedule.

    BSMV/KKDF are treated as customer cash outflows calculated on contractual interest.
    They are not bank interest income. For equal installments the gross installment is
    level, so the annuity rate is r * (1 + BSMV + KKDF).
    """
    if principal < 0:
        raise ValueError("Anapara negatif olamaz.")
    if term_months < 1 or term_months > 600:
        raise ValueError("Vade 1-600 ay arasında olmalıdır.")
    if not 0 <= bsmv_rate <= 1 or not 0 <= kkdf_rate <= 1:
        raise ValueError("BSMV/KKDF oranları 0 ile 1 arasında olmalıdır.")
    if repayment_type not in {"equal_installment", "equal_principal", "bullet"}:
        raise ValueError("Geri ödeme tipi geçersiz.")

    customer_m = monthly_rate_from_annual_nominal(annual_rate)
    funding_m = monthly_rate_from_annual_nominal(funding_cost)
    gross_financing_m = customer_m * (1.0 + bsmv_rate + kkdf_rate)
    fixed_payment = annuity_payment(principal, gross_financing_m, term_months) if repayment_type == "equal_installment" else None
    fixed_principal = principal / term_months if repayment_type == "equal_principal" else None

    rows: list[dict] = []
    balance = principal
    for m in range(1, term_months + 1):
        opening = max(balance, 0.0)
        interest = opening * customer_m
        bsmv = interest * bsmv_rate
        kkdf = interest * kkdf_rate
        taxes = bsmv + kkdf
        funding = opening * funding_m

        if repayment_type == "equal_installment":
            payment = fixed_payment or 0.0
            principal_paid = payment - interest - taxes
        elif repayment_type == "equal_principal":
            principal_paid = fixed_principal or 0.0
            payment = principal_paid + interest + taxes
        else:
            principal_paid = opening if m == term_months else 0.0
            payment = interest + taxes + principal_paid

        if m == term_months or principal_paid > opening:
            principal_paid = opening
            payment = interest + taxes + principal_paid
        principal_paid = max(0.0, principal_paid)
        closing = max(0.0, opening - principal_paid)
        rows.append({
            "period": m,
            "opening_balance": opening,
            "payment": payment,
            "interest": interest,
            "bsmv": bsmv,
            "kkdf": kkdf,
            "taxes_and_funds": taxes,
            "principal": principal_paid,
            "closing_balance": closing,
            "funding_cost_contractual": funding,
        })
        balance = closing
    return rows


def _conditional_event_weights(total_probability: float, term_months: int) -> list[float]:
    """Conditional timing weights given that an event occurs during the term."""
    if total_probability <= 0:
        return [0.0] * term_months
    hazard = _constant_monthly_hazard(min(total_probability, 0.999999), term_months)
    probs: list[float] = []
    survival = 1.0
    for _ in range(term_months):
        p = survival * hazard
        probs.append(p)
        survival *= 1.0 - hazard
    total = sum(probs)
    return [p / total for p in probs] if total > 0 else [0.0] * term_months


def _workout_funding_pv(ead: float, monthly_funding_rate: float, discount_m: float, default_period: int, recovery_lag_months: int) -> float:
    if ead <= 0 or recovery_lag_months <= 0 or monthly_funding_rate <= 0:
        return 0.0
    return sum(
        present_value(ead * monthly_funding_rate, discount_m, default_period + j)
        for j in range(recovery_lag_months)
    )


def _workout_funding_nominal(ead: float, monthly_funding_rate: float, recovery_lag_months: int) -> float:
    return max(0.0, ead) * max(0.0, monthly_funding_rate) * max(0, recovery_lag_months)


def cashflow_economics(
    *,
    principal: float,
    annual_rate: float,
    funding_cost: float,
    term_months: int,
    repayment_type: RepaymentType,
    pd: float,
    pd_basis: PDBasis,
    lgd: float,
    ead_factor: float,
    late_probability: float,
    late_loss_rate: float,
    operating_cost: float,
    upfront_fee: float,
    capital_cost_rate: float,
    capital_confidence: float,
    capital_model_status: str,
    bsmv_rate: float = 0.0,
    kkdf_rate: float = 0.0,
    recovery_lag_months: int = 0,
    funding_method: str = "flat_funding_rate_pilot",
) -> dict:
    if not 0 <= lgd <= 1:
        raise ValueError("LGD 0 ile 1 arasında olmalıdır.")
    if not 0 <= late_probability <= 1:
        raise ValueError("Geç ödeme olasılığı 0 ile 1 arasında olmalıdır.")
    if not 0 <= late_loss_rate <= 1:
        raise ValueError("Geç ödeme kayıp oranı 0 ile 1 arasında olmalıdır.")
    if not 0 <= recovery_lag_months <= 120:
        raise ValueError("Recovery/workout süresi 0-120 ay arasında olmalıdır.")

    schedule = build_contractual_schedule(
        principal, annual_rate, funding_cost, term_months, repayment_type,
        bsmv_rate=bsmv_rate, kkdf_rate=kkdf_rate,
    )
    term_pd, _ = horizon_pd(pd, pd_basis, term_months)
    pd_12m = twelve_month_pd(pd, pd_basis, term_months)
    late_effective = min(max(0.0, late_probability), max(0.0, 1.0 - term_pd))
    good_effective = max(0.0, 1.0 - term_pd - late_effective)
    state_probabilities = [good_effective, late_effective, term_pd]

    default_weights = _conditional_event_weights(term_pd, term_months)
    late_weights = _conditional_event_weights(late_effective, term_months)
    default_probs = [term_pd * w for w in default_weights]
    late_probs = [late_effective * w for w in late_weights]

    funding_m = monthly_rate_from_annual_nominal(funding_cost)
    customer_m = monthly_rate_from_annual_nominal(annual_rate)
    gross_customer_m = customer_m * (1.0 + bsmv_rate + kkdf_rate)
    discount_m = funding_m

    # Capital is a transparent pilot adapter, not a regulatory/ICAAP capital engine.
    capital_by_period: list[float] = []
    cap_cost_by_period: list[float] = []
    for row in schedule:
        ead = row["opening_balance"] * ead_factor
        cap = analytical_credit_var_capital(pd_12m, lgd, ead, capital_confidence, capital_model_status)
        capital_by_period.append(cap.economic_capital)
        cap_cost_by_period.append(cap.economic_capital * capital_cost_rate / 12.0)

    total_interest = sum(r["interest"] for r in schedule)
    total_bsmv = sum(r["bsmv"] for r in schedule)
    total_kkdf = sum(r["kkdf"] for r in schedule)
    total_tax = total_bsmv + total_kkdf
    total_payment = sum(r["payment"] for r in schedule)
    total_funding = sum(r["funding_cost_contractual"] for r in schedule)
    total_capital_cost = sum(cap_cost_by_period)
    avg_balance = sum(r["opening_balance"] for r in schedule) / term_months if term_months else 0.0

    # Performing state: full contracted spread, with taxes/funds treated as pass-through customer cash flow.
    perform_npv = upfront_fee - operating_cost
    for row, cap_cost in zip(schedule, cap_cost_by_period):
        perform_npv += present_value(row["interest"] - row["funding_cost_contractual"] - cap_cost, discount_m, row["period"])

    # Late-only state is mutually exclusive from default. A single late-event loss is timed over the term.
    conditional_late_loss = 0.0
    conditional_late_loss_pv = 0.0
    if late_effective > 0:
        conditional_late_loss = sum(w * r["opening_balance"] * late_loss_rate for w, r in zip(late_weights, schedule))
        conditional_late_loss_pv = sum(
            w * present_value(r["opening_balance"] * late_loss_rate, discount_m, r["period"])
            for w, r in zip(late_weights, schedule)
        )
    late_payoff = perform_npv - conditional_late_loss_pv

    # Default state: no future performing margin after the default event. The unresolved EAD
    # continues to carry funding cost for an explicit workout/recovery lag.
    cumulative_predefault_margin_pv = 0.0
    cumulative_predefault_interest = 0.0
    cumulative_predefault_funding = 0.0
    cumulative_predefault_capital_cost = 0.0
    default_payoffs: list[float] = []
    default_losses: list[float] = []
    workout_funding_nominals: list[float] = []
    workout_funding_pvs: list[float] = []
    predefault_interests: list[float] = []
    predefault_fundings: list[float] = []
    predefault_capital_costs: list[float] = []

    for row, cap_cost in zip(schedule, cap_cost_by_period):
        ead_at_default = row["opening_balance"] * ead_factor
        loss_at_default = ead_at_default * lgd
        workout_nominal = _workout_funding_nominal(ead_at_default, funding_m, recovery_lag_months)
        workout_pv = _workout_funding_pv(ead_at_default, funding_m, discount_m, row["period"], recovery_lag_months)
        payoff = (
            upfront_fee
            - operating_cost
            + cumulative_predefault_margin_pv
            - present_value(loss_at_default, discount_m, row["period"])
            - workout_pv
        )
        default_payoffs.append(payoff)
        default_losses.append(loss_at_default)
        workout_funding_nominals.append(workout_nominal)
        workout_funding_pvs.append(workout_pv)
        predefault_interests.append(cumulative_predefault_interest)
        predefault_fundings.append(cumulative_predefault_funding)
        predefault_capital_costs.append(cumulative_predefault_capital_cost)

        margin_cf = row["interest"] - row["funding_cost_contractual"] - cap_cost
        cumulative_predefault_margin_pv += present_value(margin_cf, discount_m, row["period"])
        cumulative_predefault_interest += row["interest"]
        cumulative_predefault_funding += row["funding_cost_contractual"]
        cumulative_predefault_capital_cost += cap_cost

    def weighted(values: list[float], weights: list[float]) -> float:
        return sum(w * x for w, x in zip(weights, values)) if values and weights else 0.0

    default_payoff = weighted(default_payoffs, default_weights) if term_pd > 0 else perform_npv
    conditional_default_loss = weighted(default_losses, default_weights) if term_pd > 0 else 0.0
    conditional_workout_funding = weighted(workout_funding_nominals, default_weights) if term_pd > 0 else 0.0
    conditional_workout_funding_pv = weighted(workout_funding_pvs, default_weights) if term_pd > 0 else 0.0
    conditional_predefault_interest = weighted(predefault_interests, default_weights) if term_pd > 0 else total_interest
    conditional_predefault_funding = weighted(predefault_fundings, default_weights) if term_pd > 0 else total_funding
    conditional_predefault_capital_cost = weighted(predefault_capital_costs, default_weights) if term_pd > 0 else total_capital_cost

    expected_npv = good_effective * perform_npv + late_effective * late_payoff + term_pd * default_payoff
    # One source of truth: state expected value and cash-flow NPV must be identical.
    state_expected_profit = expected_npv

    nondefault_prob = good_effective + late_effective
    expected_interest = nondefault_prob * total_interest + term_pd * conditional_predefault_interest
    expected_funding = nondefault_prob * total_funding + term_pd * (conditional_predefault_funding + conditional_workout_funding)
    expected_loss = term_pd * conditional_default_loss
    expected_late_loss = late_effective * conditional_late_loss
    expected_capital_cost = nondefault_prob * total_capital_cost + term_pd * conditional_predefault_capital_cost
    expected_workout_funding = term_pd * conditional_workout_funding

    lifetime_expected_contribution = (
        expected_interest + upfront_fee - expected_funding - expected_loss - expected_late_loss - operating_cost - expected_capital_cost
    )

    # Period-level expectations consistent with the mutually-exclusive state model.
    enriched: list[ScheduleRow] = []
    cumulative_default_through = 0.0
    expected_npv_12m = upfront_fee - operating_cost
    first12_income_before_capital = upfront_fee - operating_cost
    first12_expected_loss = 0.0
    first12_capitals: list[float] = []

    for idx, (row, cap_value, cap_cost) in enumerate(zip(schedule, capital_by_period, cap_cost_by_period)):
        period = row["period"]
        default_prob_this = default_probs[idx]
        active_before_payment_prob = max(0.0, 1.0 - cumulative_default_through - default_prob_this)
        interest_expected = active_before_payment_prob * row["interest"]
        base_funding_expected = active_before_payment_prob * row["funding_cost_contractual"]
        loss_expected = default_prob_this * row["opening_balance"] * ead_factor * lgd
        late_loss_expected = late_probs[idx] * row["opening_balance"] * late_loss_rate
        capital_cost_expected = active_before_payment_prob * cap_cost

        # Workout funding occurring in this calendar period from defaults in this or previous periods.
        workout_expected_period = 0.0
        if recovery_lag_months > 0 and funding_m > 0:
            for default_idx, default_prob in enumerate(default_probs):
                default_period = default_idx + 1
                if default_prob <= 0:
                    continue
                if default_period <= period < default_period + recovery_lag_months:
                    ead_default = schedule[default_idx]["opening_balance"] * ead_factor
                    workout_expected_period += default_prob * ead_default * funding_m
        funding_expected_period = base_funding_expected + workout_expected_period

        enriched.append(ScheduleRow(
            period=period,
            opening_balance=row["opening_balance"],
            payment=row["payment"],
            interest=row["interest"],
            bsmv=row["bsmv"],
            kkdf=row["kkdf"],
            taxes_and_funds=row["taxes_and_funds"],
            principal=row["principal"],
            closing_balance=row["closing_balance"],
            funding_cost=row["funding_cost_contractual"],
            expected_default_probability=default_prob_this,
            survival_probability_start=max(0.0, 1.0 - cumulative_default_through),
            expected_loss=loss_expected,
            expected_interest_income=interest_expected,
            expected_funding_cost=funding_expected_period,
            economic_capital=cap_value,
            capital_cost=capital_cost_expected,
        ))

        if period <= 12:
            net_cf = interest_expected - funding_expected_period - loss_expected - late_loss_expected - capital_cost_expected
            expected_npv_12m += present_value(net_cf, discount_m, period)
            first12_income_before_capital += interest_expected - funding_expected_period - loss_expected - late_loss_expected
            first12_expected_loss += loss_expected
            first12_capitals.append(cap_value)
        cumulative_default_through += default_prob_this

    avg_ec_12m = sum(first12_capitals) / len(first12_capitals) if first12_capitals else 0.0
    annualized_raroc = first12_income_before_capital / avg_ec_12m if avg_ec_12m > 1e-9 else (10.0 if first12_income_before_capital >= 0 else -10.0)

    perform_profit_nominal = total_interest + upfront_fee - total_funding - operating_cost - total_capital_cost
    effective_annual_customer_cost = (1.0 + gross_customer_m) ** 12 - 1.0 if gross_customer_m > -1 else 0.0

    return {
        "term_months": term_months,
        "repayment_type": repayment_type,
        "monthly_customer_rate": customer_m,
        "monthly_customer_cost_rate_including_tax_fund": gross_customer_m,
        "annual_effective_customer_cost_including_tax_fund": effective_annual_customer_cost,
        "monthly_funding_rate": funding_m,
        "monthly_payment": schedule[0]["payment"] if schedule else 0.0,
        "max_contractual_payment": max((row["payment"] for row in schedule), default=0.0),
        "max_contractual_payment_period": max(schedule, key=lambda row: row["payment"])["period"] if schedule else None,
        "contractual_total_payment": total_payment,
        "contractual_total_interest": total_interest,
        "contractual_total_bsmv": total_bsmv,
        "contractual_total_kkdf": total_kkdf,
        "contractual_total_tax_and_fund": total_tax,
        "contractual_total_funding_cost": total_funding,
        "average_outstanding_balance": avg_balance,
        "bsmv_rate": bsmv_rate,
        "kkdf_rate": kkdf_rate,
        "term_pd": term_pd,
        "pd_12m_for_capital": pd_12m,
        "pd_term_structure_method": "constant_monthly_hazard_pilot",
        "expected_interest_income": expected_interest,
        "expected_funding_cost": expected_funding,
        "expected_workout_funding_cost": expected_workout_funding,
        "expected_loss_lifetime": expected_loss,
        "expected_loss_12m": first12_expected_loss,
        "expected_late_loss": expected_late_loss,
        "capital_cost_lifetime": expected_capital_cost,
        "discount_rate_annual": funding_cost,
        "discount_rate_monthly": discount_m,
        "discount_method": funding_method,
        "recovery_lag_months": recovery_lag_months,
        "workout_method": "flat_ead_funding_until_recovery_pilot",
        "expected_npv": expected_npv,
        "expected_npv_12m": expected_npv_12m,
        "perform_profit_nominal": perform_profit_nominal,
        "perform_profit": perform_npv,
        "conditional_default_loss": conditional_default_loss,
        "conditional_workout_funding_cost": conditional_workout_funding,
        "conditional_workout_funding_cost_pv": conditional_workout_funding_pv,
        "conditional_late_loss": conditional_late_loss,
        "conditional_late_loss_pv": conditional_late_loss_pv,
        "state_expected_profit": state_expected_profit,
        "state_model": "mutually_exclusive_good_late_default",
        "lifetime_expected_contribution": lifetime_expected_contribution,
        "annualized_raroc": annualized_raroc,
        "raroc_method": "pilot_12m_credit_var_capital_profile",
        "average_economic_capital_12m": avg_ec_12m,
        "state_payoffs": [perform_npv, late_payoff, default_payoff],
        "state_probabilities": state_probabilities,
        "schedule": [x.asdict() for x in enriched],
        "optimum_term_indicator": optimum_term_indicator(customer_m),
    }


def solve_break_even_annual_rate(
    *,
    principal: float,
    funding_cost: float,
    term_months: int,
    repayment_type: RepaymentType,
    pd: float,
    pd_basis: PDBasis,
    lgd: float,
    ead_factor: float,
    late_probability: float,
    late_loss_rate: float,
    operating_cost: float,
    upfront_fee: float,
    capital_cost_rate: float,
    capital_confidence: float,
    capital_model_status: str,
    bsmv_rate: float = 0.0,
    kkdf_rate: float = 0.0,
    recovery_lag_months: int = 0,
    funding_method: str = "flat_funding_rate_pilot",
    low: float = 0.0,
    high: float = 5.0,
) -> float | None:
    if principal <= 0:
        return 0.0

    def objective(rate: float) -> float:
        return cashflow_economics(
            principal=principal,
            annual_rate=rate,
            funding_cost=funding_cost,
            term_months=term_months,
            repayment_type=repayment_type,
            pd=pd,
            pd_basis=pd_basis,
            lgd=lgd,
            ead_factor=ead_factor,
            late_probability=late_probability,
            late_loss_rate=late_loss_rate,
            operating_cost=operating_cost,
            upfront_fee=upfront_fee,
            capital_cost_rate=capital_cost_rate,
            capital_confidence=capital_confidence,
            capital_model_status=capital_model_status,
            bsmv_rate=bsmv_rate,
            kkdf_rate=kkdf_rate,
            recovery_lag_months=recovery_lag_months,
            funding_method=funding_method,
        )["expected_npv"]

    if objective(low) >= 0:
        return low
    if objective(high) < 0:
        return None
    for _ in range(24):
        mid = (low + high) / 2.0
        if objective(mid) >= 0:
            high = mid
        else:
            low = mid
    return high
