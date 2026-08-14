from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Applicant:
    applicant_id: str
    requested_amount: float
    pd: float
    lgd: float
    term_months: int = 12
    product_type: str = "ihtiyac"
    repayment_type: str = "equal_installment"
    pd_basis: str = "annual_12m"
    # These two fields are audit metadata. The daily UI does not use them as risk drivers.
    loan_purpose: str = "genel finansman"
    repayment_source: str = "düzenli gelir / nakit akışı"
    annual_rate: float = 0.60
    upfront_fee: float = 0.0
    monthly_net_income: float = 0.0
    existing_monthly_debt_service: float = 0.0
    collateral_value: float = 0.0
    collateral_energy_class: str = "other"
    housing_bsmv_exempt: bool = False
    housing_has_other_home: bool = False
    applicant_age_years: int = 0
    vehicle_is_used: bool = False
    vehicle_age_years: int = 0

    # Centrally governed economic profile. API users do not freely set these values.
    ead_factor: float = 1.0
    funding_cost: float = 0.467
    funding_method: str = "dated_public_proxy"
    operating_cost: float = 900.0
    capital_cost_rate: float = 0.03
    late_probability: float = 0.10
    late_loss_rate: float = 0.04
    recovery_lag_months: int = 6
    bsmv_rate: float = 0.0
    kkdf_rate: float = 0.0
    tax_status: str = "not_set"
    tax_note: str = ""
    parameter_status: str = "pilot"
    segment: str = "bireysel"

    def validate(self) -> None:
        if not 1 <= len(self.applicant_id.strip()) <= 64:
            raise ValueError("Başvuru kimliği 1-64 karakter arasında olmalıdır.")
        if not 0 <= self.requested_amount <= 1_000_000_000:
            raise ValueError("Talep tutarı izin verilen aralığın dışında.")
        if not 0 < self.pd < 1:
            raise ValueError("PD 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.lgd <= 1:
            raise ValueError("LGD 0 ile 1 arasında olmalıdır.")
        if not 1 <= self.term_months <= 600:
            raise ValueError("Vade 1-600 ay arasında olmalıdır.")
        if self.product_type not in {"ihtiyac", "konut", "tasit", "ticari_taksitli", "spot", "diger"}:
            raise ValueError("Kredi ürünü geçersiz.")
        if self.repayment_type not in {"equal_installment", "equal_principal", "bullet"}:
            raise ValueError("Geri ödeme tipi geçersiz.")
        if self.pd_basis not in {"annual_12m", "lifetime"}:
            raise ValueError("PD ufku annual_12m veya lifetime olmalıdır.")
        if not 1 <= len(self.loan_purpose.strip()) <= 120:
            raise ValueError("Kredi amacı 1-120 karakter arasında olmalıdır.")
        if not 1 <= len(self.repayment_source.strip()) <= 120:
            raise ValueError("Geri ödeme kaynağı 1-120 karakter arasında olmalıdır.")
        if not 0 < self.ead_factor <= 5:
            raise ValueError("EAD çarpanı 0 ile 5 arasında olmalıdır.")
        if not 0 <= self.funding_cost <= 5 or not 0 <= self.annual_rate <= 5:
            raise ValueError("Faiz oranları izin verilen aralığın dışında.")
        if not 0 <= self.operating_cost <= 1_000_000_000:
            raise ValueError("Operasyon maliyeti izin verilen aralığın dışında.")
        if not 0 <= self.upfront_fee <= 1_000_000_000:
            raise ValueError("Peşin ücret/komisyon izin verilen aralığın dışında.")
        if not 0 <= self.capital_cost_rate <= 1:
            raise ValueError("Sermaye maliyeti oranı 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.late_probability < 1:
            raise ValueError("Geç ödeme olasılığı 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.late_loss_rate <= 1:
            raise ValueError("Geç ödeme kayıp oranı 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.recovery_lag_months <= 120:
            raise ValueError("Recovery/workout süresi 0-120 ay arasında olmalıdır.")
        if not 0 <= self.bsmv_rate <= 1 or not 0 <= self.kkdf_rate <= 1:
            raise ValueError("Vergi/fon oranları 0 ile 1 arasında olmalıdır.")
        for value, label in [
            (self.monthly_net_income, "Aylık net gelir"),
            (self.existing_monthly_debt_service, "Mevcut aylık borç servisi"),
            (self.collateral_value, "Teminat/ekspertiz değeri"),
        ]:
            if not 0 <= value <= 10_000_000_000:
                raise ValueError(f"{label} izin verilen aralığın dışında.")
        if not 0 <= self.applicant_age_years <= 120:
            raise ValueError("Başvuran yaşı 0-120 yıl arasında olmalıdır.")
        if not 0 <= self.vehicle_age_years <= 100:
            raise ValueError("Taşıt yaşı 0-100 yıl arasında olmalıdır.")
        if self.collateral_energy_class.upper() not in {"A", "B", "C", "D", "E", "F", "G", "A-B", "AB", "OTHER", "DİĞER"}:
            raise ValueError("Enerji sınıfı geçersiz.")
        if not 1 <= len(self.segment) <= 40:
            raise ValueError("Segment adı 1-40 karakter arasında olmalıdır.")
        for value, label, max_len in [
            (self.funding_method, "Fonlama yöntemi", 240),
            (self.tax_status, "Vergi profili", 80),
            (self.tax_note, "Vergi notu", 600),
            (self.parameter_status, "Parametre durumu", 40),
        ]:
            if not 0 <= len(value) <= max_len:
                raise ValueError(f"{label} metni izin verilen uzunluğun dışında.")

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Policy:
    policy_id: str
    name: str
    version: str
    status: str
    risk_aversion: float
    limit_factors: tuple[float, ...]
    max_pd: float
    max_expected_loss_rate: float
    min_raroc: float
    target_margin_rate: float
    description: str = ""
    risk_calibration_status: str = "pilot"
    risk_calibration_note: str = "Demo kalibrasyonu; kurum risk komitesi onayı gerekir."
    capital_method: str = "analytical_credit_var"
    capital_confidence: float = 0.99
    capital_model_status: str = "pilot"
    max_debt_service_ratio: float = 0.60
    affordability_status: str = "pilot"

    def validate(self) -> None:
        if not 2 <= len(self.policy_id) <= 64:
            raise ValueError("Politika kimliği geçersiz.")
        if not 1 <= len(self.name) <= 80:
            raise ValueError("Politika adı geçersiz.")
        if self.status not in {"active", "challenger", "draft"}:
            raise ValueError("Politika durumu geçersiz.")
        if not 0 < self.risk_aversion <= 1:
            raise ValueError("Riskten kaçınma parametresi geçersiz.")
        if not 2 <= len(self.limit_factors) <= 10 or any(not 0 <= x <= 1 for x in self.limit_factors):
            raise ValueError("Limit çarpanları 0-1 arasında ve 2-10 adet olmalıdır.")
        if tuple(sorted(set(self.limit_factors))) != tuple(self.limit_factors):
            raise ValueError("Limit çarpanları artan ve benzersiz olmalıdır.")
        if not 0 < self.max_pd < 1:
            raise ValueError("Maksimum PD geçersiz.")
        if not 0 <= self.max_expected_loss_rate <= 1:
            raise ValueError("Maksimum beklenen kayıp oranı geçersiz.")
        if not -10 <= self.min_raroc <= 10:
            raise ValueError("Minimum RAROC sınırı geçersiz.")
        if not 0 <= self.target_margin_rate <= 5:
            raise ValueError("Hedef marj oranı geçersiz.")
        if self.risk_calibration_status not in {"pilot", "approved"}:
            raise ValueError("Risk kalibrasyon durumu pilot veya approved olmalıdır.")
        if not 1 <= len(self.risk_calibration_note) <= 500:
            raise ValueError("Risk kalibrasyon notu geçersiz.")
        if self.capital_method != "analytical_credit_var":
            raise ValueError("Bu sürümde yalnız analytical_credit_var sermaye yöntemi desteklenir.")
        if not .90 <= self.capital_confidence < 1:
            raise ValueError("Sermaye güven düzeyi 0.90 ile 1 arasında olmalıdır.")
        if self.capital_model_status not in {"pilot", "approved"}:
            raise ValueError("Sermaye model durumu pilot veya approved olmalıdır.")
        if not 0 < self.max_debt_service_ratio <= 2:
            raise ValueError("Borç ödeme / gelir sınırı geçersiz.")
        if self.affordability_status not in {"pilot", "approved"}:
            raise ValueError("Ödeme gücü politika durumu pilot veya approved olmalıdır.")

    def asdict(self) -> dict[str, Any]:
        d = asdict(self)
        d["limit_factors"] = list(self.limit_factors)
        d["risk_tolerance_tl"] = (1.0 / self.risk_aversion) if self.risk_aversion > 0 else None
        return d
