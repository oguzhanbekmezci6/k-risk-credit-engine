from __future__ import annotations

from dataclasses import asdict, dataclass


# Public market data are deliberately kept separate from bank-internal model parameters.
# TCMB loan rates are weekly annualised weighted-average FLOW rates and are market
# benchmarks, not a promise that a specific customer will receive that rate.
MARKET_REFERENCE = {
    "policy_as_of": "2026-07-23",
    "flow_rates_as_of": "2026-07-31",
    "funding_proxy_as_of": "2026-07-17",
    "tcmb_policy_rate": 0.37,
    "tcmb_overnight_lending": 0.40,
    "tcmb_overnight_borrowing": 0.355,
    # Kept as a dated public funding proxy until a real bank FTP / treasury curve is connected.
    "tl_deposit_rate": 0.467,
    # Latest embedded TCMB weekly flow loan-rate observations available for this build.
    "tl_commercial_loan_rate": 0.5248,
    "consumer_loan_rate": 0.5691,
    "housing_loan_rate": 0.3882,
    "vehicle_loan_rate": 0.3883,
    "cpi_yoy_june_2026": 0.3211,
    "inflation_expectation_12m_july_2026": 0.240,
}


# Public Akbank retail examples displayed on akbank.com as of 11.08.2026.
# Rates are MONTHLY contractual nominal rates. Customer-specific pricing may differ.
AKBANK_REFERENCE = {
    "as_of": "2026-08-11",
    "ihtiyac": {
        "monthly_rate": 0.0384,
        "label": "Hayat sigortalı ihtiyaç kredisi örnek oranı",
        "source": "Güncel bireysel kredi referansı",
    },
    "konut": {
        "monthly_rate": 0.0315,
        "label": "Konut kredisi hesaplama örnek oranı",
        "source": "Güncel konut kredisi referansı",
    },
    "tasit": {
        "monthly_rate_by_max_term": ((12, 0.0375), (24, 0.0370), (36, 0.0365), (48, 0.0360)),
        "label": "0 km taşıt kredisi örnek oranı (hayat sigortası + kasko şartlı)",
        "source": "Güncel taşıt kredisi referansı",
    },
}


def akbank_rate_reference(product_type: str, term_months: int = 12) -> dict | None:
    """Return the dated Akbank public monthly-rate example for supported retail products."""
    if product_type == "tasit":
        rows = AKBANK_REFERENCE["tasit"]["monthly_rate_by_max_term"]
        monthly = next((rate for max_term, rate in rows if term_months <= max_term), None)
        if monthly is None:
            return None
        meta = AKBANK_REFERENCE["tasit"]
    elif product_type in {"ihtiyac", "konut"}:
        meta = AKBANK_REFERENCE[product_type]
        monthly = meta["monthly_rate"]
    else:
        return None
    return {
        "as_of": AKBANK_REFERENCE["as_of"],
        "monthly_rate": monthly,
        "annual_nominal_rate": monthly * 12.0,
        "label": meta["label"],
        "source": meta["source"],
        "status": "public_bank_example_not_customer_offer",
    }


@dataclass(frozen=True)
class EconomicProfile:
    segment: str
    funding_cost: float
    funding_method: str
    operating_cost: float
    capital_cost_rate: float
    ead_factor: float
    late_probability: float
    late_loss_rate: float
    recovery_lag_months: int
    bsmv_rate: float
    kkdf_rate: float
    tax_status: str
    tax_note: str
    parameter_status: str = "pilot"

    def asdict(self) -> dict:
        return asdict(self)




def default_customer_annual_nominal_rate(product_type: str, term_months: int = 12) -> float:
    """Default pricing input when API/UI does not supply a customer rate.

    Akbank public retail examples are preferred for supported products. For products
    without a public Akbank quote in this build, TCMB sector flow rate is used only
    as a transparent market benchmark/default, not as an Akbank offer.
    """
    bank_ref = akbank_rate_reference(product_type, term_months)
    if bank_ref is not None:
        return float(bank_ref["annual_nominal_rate"])
    if product_type in {"ticari_taksitli", "spot"}:
        return float(MARKET_REFERENCE["tl_commercial_loan_rate"])
    return float(MARKET_REFERENCE["consumer_loan_rate"])

def infer_segment(product_type: str) -> str:
    if product_type in {"ticari_taksitli", "spot"}:
        return "ticari"
    return "bireysel"


def default_purpose(product_type: str) -> str:
    return {
        "ihtiyac": "bireysel ihtiyaç finansmanı",
        "konut": "konut edinimi finansmanı",
        "tasit": "taşıt edinimi finansmanı",
        "ticari_taksitli": "işletme / yatırım finansmanı",
        "spot": "kısa vadeli işletme finansmanı",
        "diger": "genel finansman",
    }.get(product_type, "genel finansman")


def default_repayment_source(product_type: str) -> str:
    return "işletme nakit akışı" if product_type in {"ticari_taksitli", "spot"} else "düzenli gelir / nakit akışı"


def economic_profile_for(product_type: str, *, housing_bsmv_exempt: bool = False) -> EconomicProfile:
    """Return centrally governed pilot parameters for a product.

    Funding is not claimed to be a real bank FTP. In the absence of a connected bank
    treasury curve, the most recent public TL deposit flow rate is used as a dated and
    visible proxy. All other operational/risk parameters are explicit pilot institution
    assumptions and are not presented as public economic facts.
    """
    segment = infer_segment(product_type)

    if product_type in {"ihtiyac", "tasit", "diger"}:
        bsmv = 0.15
        kkdf = 0.15
        tax_status = "consumer_credit"
        tax_note = "Tüketici kredisi pilot vergi profili: faiz üzerinden BSMV %15 ve KKDF %15."
    elif product_type == "konut":
        # Valid housing loans are treated as KKDF-exempt. BSMV exemption is conditional
        # after 28.12.2023; the user must explicitly confirm the eligibility condition.
        bsmv = 0.0 if housing_bsmv_exempt else 0.15
        kkdf = 0.0
        tax_status = "housing_exempt" if housing_bsmv_exempt else "housing_bsmv_taxable"
        tax_note = (
            "Konut finansmanı: KKDF %0; BSMV istisnası kullanıcı tarafından şartların sağlandığı teyit edilirse %0, aksi halde tüketici kredi oranı %15 uygulanır."
        )
    else:  # commercial installment / spot
        bsmv = 0.05
        kkdf = 0.0
        tax_status = "commercial_credit"
        tax_note = "Ticari kredi pilot vergi profili: faiz üzerinden genel BSMV %5, KKDF %0."

    return EconomicProfile(
        segment=segment,
        funding_cost=MARKET_REFERENCE["tl_deposit_rate"],
        funding_method="TCMB TL mevduat akım faizi bazlı pilot fonlama vekili; gerçek banka FTP değildir",
        operating_cost=900.0,
        capital_cost_rate=0.03,
        ead_factor=1.0,
        late_probability=0.10,
        late_loss_rate=0.04,
        recovery_lag_months=6,
        bsmv_rate=bsmv,
        kkdf_rate=kkdf,
        tax_status=tax_status,
        tax_note=tax_note,
    )
