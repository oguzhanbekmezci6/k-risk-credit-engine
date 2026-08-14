from __future__ import annotations

from datetime import date

from app.decision.economic_profiles import MARKET_REFERENCE, akbank_rate_reference


REFERENCE_AS_OF = "2026-08-11"


def consumer_loan_max_term_months(credit_amount: float) -> int:
    """BDDK 13.02.2025 / 11152 general consumer-loan term reference."""
    if credit_amount < 0:
        raise ValueError("Kredi tutarı negatif olamaz.")
    if credit_amount <= 125_000:
        return 36
    if credit_amount <= 250_000:
        return 24
    return 12


def vehicle_loan_reference(vehicle_value: float) -> dict:
    """Akbank public standard vehicle-loan value/LTV/term table (11.08.2026).

    For 0 km vehicles Akbank uses final invoice value; for used vehicles it uses
    the relevant vehicle value/kasko basis. This is a bank product rule, not a
    universal regulatory table for every special vehicle programme.
    """
    if vehicle_value <= 0:
        return {"available": False, "max_ltv": None, "max_loan": None, "max_term_months": None}
    if vehicle_value <= 400_000:
        ratio, max_term = 0.70, 48
    elif vehicle_value <= 800_000:
        ratio, max_term = 0.50, 36
    elif vehicle_value <= 1_200_000:
        ratio, max_term = 0.30, 24
    elif vehicle_value <= 2_000_000:
        ratio, max_term = 0.20, 12
    else:
        ratio, max_term = 0.0, 0
    return {
        "available": ratio > 0,
        "vehicle_value": vehicle_value,
        "max_ltv": ratio,
        "max_loan": vehicle_value * ratio,
        "max_term_months": max_term,
        "source": "Güncel taşıt kredisi ürün koşulları (11.08.2026)",
        "status": "bank_product_reference",
    }


def housing_ltv_reference(property_value: float, energy_class: str, has_other_home: bool = False) -> dict:
    """BDDK 11364 base LTV table plus the still-applicable BDDK 10656 other-home reduction."""
    if property_value <= 0:
        return {"available": False, "max_ltv": None, "max_loan": None}
    cls = (energy_class or "other").upper().strip()
    if cls in {"A", "B", "A-B", "AB"}:
        col = 0
        normalized = "A-B"
    elif cls == "C":
        col = 1
        normalized = "C"
    else:
        col = 2
        normalized = "DİĞER"
    if property_value <= 5_000_000:
        ratios = (0.90, 0.80, 0.70)
    elif property_value <= 7_000_000:
        ratios = (0.80, 0.70, 0.60)
    elif property_value <= 10_000_000:
        ratios = (0.70, 0.60, 0.50)
    elif property_value <= 20_000_000:
        ratios = (0.50, 0.40, 0.30)
    else:
        ratios = (0.40, 0.30, 0.20)
    base_ratio = ratios[col]
    # BDDK 10656 says the maximum ratio is reduced by 75% when the borrower/spouse/
    # minor child owns at least one other qualifying dwelling: remaining ratio = 25%.
    ratio = base_ratio * (0.25 if has_other_home else 1.0)
    return {
        "available": True,
        "energy_class": normalized,
        "property_value": property_value,
        "has_other_home": bool(has_other_home),
        "base_max_ltv": base_ratio,
        "max_ltv": ratio,
        "max_loan": property_value * ratio,
        "source": "BDDK 11364 (29.01.2026) + 10656 (24.08.2023)" if has_other_home else "BDDK 11364 (29.01.2026)",
        "status": "regulatory_reference",
    }


def effective_debt_service_ratio_limit(product_type: str, internal_limit: float) -> tuple[float, str, str]:
    """Use the stricter of internal policy and Akbank's public 50% retail reference."""
    if product_type == "ihtiyac":
        return min(float(internal_limit), 0.50), "AKBANK_RETAIL_AFFORDABILITY", "Güncel bireysel ihtiyaç kredisi ürün koşulları (11.08.2026)"
    return float(internal_limit), "INTERNAL_AFFORDABILITY", "Kurum politikası / pilot varsayım"


def market_snapshot(product_type: str | None = None, term_months: int = 12) -> dict:
    policy_date = date.fromisoformat(MARKET_REFERENCE["policy_as_of"])
    flow_date = date.fromisoformat(MARKET_REFERENCE["flow_rates_as_of"])
    funding_date = date.fromisoformat(MARKET_REFERENCE["funding_proxy_as_of"])
    reference_date = date.fromisoformat(REFERENCE_AS_OF)
    policy_age_days = max(0, (reference_date - policy_date).days)
    flow_age_days = max(0, (reference_date - flow_date).days)
    funding_age_days = max(0, (reference_date - funding_date).days)
    snap = {
        "as_of": MARKET_REFERENCE["policy_as_of"],
        "reference_date": REFERENCE_AS_OF,
        "age_days": policy_age_days,
        "freshness_status": "GÜNCEL" if policy_age_days <= 21 else ("ESKİYEBİLİR" if policy_age_days <= 45 else "ESKİ"),
        "tcmb_policy_rate": MARKET_REFERENCE["tcmb_policy_rate"],
        "tcmb_overnight_lending": MARKET_REFERENCE["tcmb_overnight_lending"],
        "tcmb_overnight_borrowing": MARKET_REFERENCE["tcmb_overnight_borrowing"],
        "source": "TCMB PPK 2026-28 (23.07.2026)",
        "public_lending_reference": {
            "as_of": MARKET_REFERENCE["flow_rates_as_of"],
            "age_days": flow_age_days,
            "freshness_status": "GÜNCEL" if flow_age_days <= 14 else ("ESKİYEBİLİR" if flow_age_days <= 45 else "ESKİ"),
            "tl_commercial_loan_rate": MARKET_REFERENCE["tl_commercial_loan_rate"],
            "consumer_loan_rate": MARKET_REFERENCE["consumer_loan_rate"],
            "housing_loan_rate": MARKET_REFERENCE["housing_loan_rate"],
            "vehicle_loan_rate": MARKET_REFERENCE["vehicle_loan_rate"],
            "source": "TCMB Haftalık Akım Faiz İstatistikleri; yıllıklandırılmış ağırlıklı ortalama (31.07.2026)",
            "status": "dated_public_market_benchmark",
        },
        "funding_proxy": {
            "as_of": MARKET_REFERENCE["funding_proxy_as_of"],
            "age_days": funding_age_days,
            "tl_deposit_rate": MARKET_REFERENCE["tl_deposit_rate"],
            "source": "TCMB PPK Toplantı Özeti 2026-32; TL mevduat akım faizi (17.07.2026)",
            "status": "dated_public_proxy_not_ftp",
        },
        "macro_context": {
            "cpi_yoy_june_2026": MARKET_REFERENCE["cpi_yoy_june_2026"],
            "inflation_expectation_12m_july_2026": MARKET_REFERENCE["inflation_expectation_12m_july_2026"],
            "source": "TCMB PPK Toplantı Özeti 2026-32",
        },
        "funding_proxy_note": "Pilot fonlama vekili kamuya açık TL mevduat akım faizidir; gerçek banka FTP'si değildir.",
        "note": "Müşteriye uygulanan oran ile TCMB sektör ortalaması ayrı kavramlardır; TCMB oranı müşteri teklifi değildir. Pilot fonlama vekili gerçek banka FTP'si değildir.",
    }
    bank_ref = akbank_rate_reference(product_type or "", term_months)
    if bank_ref:
        snap["akbank_customer_rate_reference"] = bank_ref
    return snap


def daily_banking_checks(
    *,
    product_type: str,
    proposed_limit: float,
    requested_term_months: int,
    collateral_value: float = 0.0,
    collateral_energy_class: str = "other",
    housing_has_other_home: bool = False,
    applicant_age_years: int = 0,
    vehicle_is_used: bool = False,
    vehicle_age_years: int = 0,
    monthly_net_income: float = 0.0,
    existing_monthly_debt_service: float = 0.0,
    proposed_monthly_payment: float = 0.0,
    internal_max_debt_service_ratio: float = 0.60,
) -> dict:
    checks: list[dict] = []
    hard_failures: list[str] = []

    if product_type == "ihtiyac":
        max_term = consumer_loan_max_term_months(proposed_limit)
        ok = requested_term_months <= max_term
        checks.append({
            "code": "BDDK_CONSUMER_TERM", "name": "Tüketici kredisi vade sınırı",
            "status": "PASS" if ok else "FAIL", "actual": requested_term_months, "limit": max_term,
            "unit": "ay", "source": "BDDK 11152 (13.02.2025)",
        })
        if not ok:
            hard_failures.append("BDDK tüketici kredisi vade sınırı")

    if product_type == "tasit":
        if collateral_value <= 0:
            checks.append({
                "code": "VEHICLE_VALUE_REQUIRED", "name": "Taşıt fatura / kasko değeri", "status": "FAIL",
                "actual": collateral_value, "limit": None, "unit": "TL", "source": "Güncel taşıt kredisi ürün koşulları",
                "note": "Taşıt kredi/değer ve vade kontrolü için araç değeri zorunludur.",
            })
            hard_failures.append("taşıt fatura/kasko değeri eksik")
        else:
            ref = vehicle_loan_reference(collateral_value)
            if not ref["available"]:
                checks.append({
                    "code": "AKBANK_VEHICLE_VALUE_BAND", "name": "Güncel standart taşıt kredisi araç değer bandı",
                    "status": "FAIL", "actual": collateral_value, "limit": 2_000_000.0, "unit": "TL", "source": ref["source"],
                })
                hard_failures.append("Güncel standart taşıt kredisi araç değer bandı")
            else:
                actual_ltv = proposed_limit / collateral_value
                ltv_ok = proposed_limit <= ref["max_loan"] + 1e-6
                term_ok = requested_term_months <= ref["max_term_months"]
                checks.append({
                    "code": "AKBANK_VEHICLE_LTV", "name": "Taşıt kredi/değer oranı",
                    "status": "PASS" if ltv_ok else "FAIL", "actual": actual_ltv, "limit": ref["max_ltv"],
                    "unit": "oran", "source": ref["source"],
                })
                checks.append({
                    "code": "AKBANK_VEHICLE_TERM", "name": "Taşıt azami vade",
                    "status": "PASS" if term_ok else "FAIL", "actual": requested_term_months, "limit": ref["max_term_months"],
                    "unit": "ay", "source": ref["source"],
                })
                if not ltv_ok:
                    hard_failures.append("Güncel taşıt kredi/değer sınırı")
                if not term_ok:
                    hard_failures.append("Güncel taşıt azami vade sınırı")

            if vehicle_is_used:
                if vehicle_age_years <= 0:
                    checks.append({
                        "code": "AKBANK_USED_VEHICLE_AGE_REQUIRED", "name": "2. el taşıt yaşı",
                        "status": "FAIL", "actual": vehicle_age_years, "limit": 10, "unit": "yıl",
                        "source": "Güncel ikinci el taşıt kredisi koşulları (11.08.2026)",
                        "note": "2. el bireysel taşıtta araç yaşı ve yaş + vade kontrolü için yaş bilgisi zorunludur.",
                    })
                    hard_failures.append("2. el taşıt yaşı eksik")
                else:
                    age_ok = vehicle_age_years <= 10
                    age_term_limit = max(0, 144 - vehicle_age_years * 12)
                    age_term_ok = requested_term_months <= age_term_limit
                    checks.append({
                        "code": "AKBANK_USED_VEHICLE_AGE", "name": "2. el taşıt azami yaşı",
                        "status": "PASS" if age_ok else "FAIL", "actual": vehicle_age_years, "limit": 10,
                        "unit": "yıl", "source": "Güncel ikinci el taşıt kredisi koşulları (11.08.2026)",
                    })
                    checks.append({
                        "code": "AKBANK_USED_VEHICLE_AGE_TERM", "name": "2. el taşıt yaş + vade sınırı",
                        "status": "PASS" if age_term_ok else "FAIL", "actual": vehicle_age_years * 12 + requested_term_months,
                        "limit": 144, "unit": "ay", "source": "Güncel ikinci el taşıt kredisi koşulları (11.08.2026)",
                    })
                    if not age_ok:
                        hard_failures.append("Güncel 2. el taşıt azami yaş sınırı")
                    if not age_term_ok:
                        hard_failures.append("Güncel 2. el taşıt yaş + vade sınırı")

    if product_type == "konut":
        term_ok = requested_term_months <= 120
        amount_ok = proposed_limit <= 20_000_000 + 1e-6
        if applicant_age_years <= 0:
            checks.append({
                "code": "AKBANK_HOUSING_AGE_REQUIRED", "name": "Konut kredisi başvuran yaşı",
                "status": "FAIL", "actual": applicant_age_years, "limit": None, "unit": "yıl",
                "source": "Güncel konut kredisi koşulları (11.08.2026)",
                "note": "Güncel yaş + vade kontrolünü uygulamak için başvuran yaşı zorunludur.",
            })
            hard_failures.append("konut başvuran yaşı eksik")
        else:
            age_term_ok = applicant_age_years * 12 + requested_term_months <= 70 * 12
            checks.append({
                "code": "AKBANK_HOUSING_AGE_TERM", "name": "Konut yaş + vade sınırı",
                "status": "PASS" if age_term_ok else "FAIL",
                "actual": applicant_age_years * 12 + requested_term_months, "limit": 70 * 12, "unit": "ay",
                "source": "Güncel konut kredisi koşulları (11.08.2026)",
                "note": "Başvuran yaşı ile kredi vadesinin toplamı 70 yılı aşmamalıdır.",
            })
            if not age_term_ok:
                hard_failures.append("Güncel konut yaş + vade sınırı")
        checks.append({
            "code": "AKBANK_HOUSING_TERM", "name": "Güncel konut azami vade",
            "status": "PASS" if term_ok else "FAIL", "actual": requested_term_months, "limit": 120,
            "unit": "ay", "source": "Güncel konut kredisi koşulları (11.08.2026)",
        })
        checks.append({
            "code": "AKBANK_HOUSING_MAX_AMOUNT", "name": "Güncel konut azami kredi tutarı",
            "status": "PASS" if amount_ok else "FAIL", "actual": proposed_limit, "limit": 20_000_000.0,
            "unit": "TL", "source": "Güncel konut kredisi koşulları (11.08.2026)",
        })
        if not term_ok:
            hard_failures.append("Güncel konut azami vade sınırı")
        if not amount_ok:
            hard_failures.append("Güncel konut azami kredi tutarı")
        if collateral_value <= 0:
            checks.append({
                "code": "HOUSING_COLLATERAL_REQUIRED", "name": "Konut ekspertiz / teminat değeri",
                "status": "FAIL", "actual": collateral_value, "limit": None, "unit": "TL",
                "source": "K-Risk girdi bütünlüğü", "note": "Konut kredi/değer kontrolü için ekspertiz/teminat değeri zorunludur.",
            })
            hard_failures.append("konut ekspertiz/teminat değeri eksik")
        else:
            ref = housing_ltv_reference(collateral_value, collateral_energy_class, housing_has_other_home)
            actual_ltv = proposed_limit / collateral_value
            ok = proposed_limit <= (ref.get("max_loan") or 0.0) + 1e-6
            checks.append({
                "code": "BDDK_HOUSING_LTV_REFERENCE", "name": "Konut kredi/değer oranı referansı",
                "status": "PASS" if ok else "FAIL", "actual": actual_ltv, "limit": ref.get("max_ltv"),
                "unit": "oran", "source": ref.get("source"),
                "note": "Başka konut sahipliği seçildiyse BDDK 10656 uyarınca baz oran %75 azaltılır." if housing_has_other_home else None,
            })
            if not ok:
                hard_failures.append("BDDK konut kredi/değer oranı referansı")

    debt_service_ratio = None
    affordability_limit, affordability_code, affordability_source = effective_debt_service_ratio_limit(
        product_type, internal_max_debt_service_ratio
    )
    if monthly_net_income > 0:
        debt_service_ratio = (existing_monthly_debt_service + proposed_monthly_payment) / monthly_net_income
        ok = debt_service_ratio <= affordability_limit + 1e-12
        checks.append({
            "code": affordability_code, "name": "Borç ödeme / net gelir", "status": "PASS" if ok else "FAIL",
            "actual": debt_service_ratio, "limit": affordability_limit, "unit": "oran", "source": affordability_source,
            "note": "En yüksek sözleşmesel dönem ödemesi kullanılır; ihtiyaç kredisinde güncel %50 hane geliri referansı ile kurum limitinin sıkı olanı uygulanır." if product_type == "ihtiyac" else "Geri ödeme planındaki en yüksek sözleşmesel dönem ödemesi kullanılır.",
        })
        if not ok:
            hard_failures.append("Müşteri ödeme kapasitesi sınırı")

    return {
        "as_of": REFERENCE_AS_OF, "checks": checks, "hard_failures": hard_failures,
        "debt_service_ratio": debt_service_ratio, "effective_debt_service_ratio_limit": affordability_limit,
        "regulatory_engine_scope": "regulatory_plus_akbank_public_product_rules",
    }
