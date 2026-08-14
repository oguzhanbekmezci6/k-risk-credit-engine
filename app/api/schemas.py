from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.identity import normalize_username

SafeShort = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^<>{}\x00-\x1f]*$")]
Prob = Annotated[float, Field(ge=0.0, le=1.0)]
Money = Annotated[float, Field(ge=0.0, le=1_000_000_000.0)]
FiniteWide = Annotated[float, Field(ge=-1_000_000_000_000.0, le=1_000_000_000_000.0)]


class _UsernameModel(BaseModel):
    @field_validator("username", check_fields=False)
    @classmethod
    def normalize_user_name(cls, value: str) -> str:
        try:
            return normalize_username(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class LoginRequest(_UsernameModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class FirstAdminSetupRequest(_UsernameModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    setup_code: str | None = Field(default=None, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserCreateRequest(_UsernameModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    role: Literal["admin", "risk_manager", "analyst"]


class InformationSignal(BaseModel):
    name: SafeShort = "Varsayımsal ek bilgi sinyali (simülasyon)"
    cost: Money = 350.0
    source_mode: Literal["simulation", "calibrated", "live"] = "simulation"
    source_note: str = Field(default="Gerçek kredi bürosu verisi değildir; örnek olabilirlik matrisiyle yalnız bilgi değeri hesaplanır.", max_length=500, pattern=r"^[^<>{}\x00-\x1f]*$")
    signal_names: list[SafeShort] = Field(default_factory=lambda: ["yeşil", "sarı", "kırmızı"], min_length=1, max_length=10)
    signal_given_state: list[list[Prob]] = Field(
        default_factory=lambda: [[.78, .18, .04], [.30, .52, .18], [.08, .27, .65]],
        min_length=1,
        max_length=10,
    )

    @field_validator("signal_given_state")
    @classmethod
    def validate_matrix_size(cls, value: list[list[float]]) -> list[list[float]]:
        if any(not 1 <= len(row) <= 10 for row in value):
            raise ValueError("Sinyal olasılık matrisinde her satır 1-10 değer içermelidir.")
        return value


class DecisionRequest(BaseModel):
    applicant_id: str = Field(default="DEMO-001", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    requested_amount: Money = 150000
    term_months: int = Field(ge=1, le=600)
    product_type: Literal["ihtiyac", "konut", "tasit", "ticari_taksitli", "spot", "diger"] = "ihtiyac"
    repayment_type: Literal["equal_installment", "equal_principal", "bullet"] = "equal_installment"
    pd: float = Field(default=.08, gt=0.0, lt=1.0)
    pd_basis: Literal["annual_12m", "lifetime"] = "annual_12m"
    lgd: Prob = .55
    annual_rate: float | None = Field(default=None, ge=0.0, le=5.0)
    monthly_net_income: Money = 0
    existing_monthly_debt_service: Money = 0
    collateral_value: Money = 0
    collateral_energy_class: Literal["A", "B", "C", "D", "E", "F", "G", "other"] = "other"
    housing_bsmv_exempt: bool = False
    housing_has_other_home: bool = False
    applicant_age_years: int = Field(default=0, ge=0, le=120)
    vehicle_is_used: bool = False
    vehicle_age_years: int = Field(default=0, ge=0, le=100)
    upfront_fee: Money = 0

    # Audit metadata: retained for API/backward compatibility but not used as risk drivers.
    loan_purpose: str | None = Field(default=None, max_length=120, pattern=r"^[^<>{}\x00-\x1f]*$")
    repayment_source: str | None = Field(default=None, max_length=120, pattern=r"^[^<>{}\x00-\x1f]*$")

    policy_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    information_signal: InformationSignal | None = Field(default_factory=InformationSignal)


class OverrideRequest(BaseModel):
    decision: Literal["ONAY", "REDDET"]
    limit: Money = 0
    reason: str = Field(min_length=8, max_length=500, pattern=r"^[^<>{}\x00-\x1f]+$")


class PolicyRequest(BaseModel):
    policy_id: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    name: SafeShort
    version: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9._-]+$")
    status: Literal["active", "challenger", "draft"] = "draft"
    risk_aversion: float | None = Field(default=None, gt=0.0, le=1.0)
    risk_tolerance_tl: float | None = Field(default=None, gt=0.0, le=100_000_000_000.0)
    risk_calibration_status: Literal["pilot", "approved"] = "pilot"
    risk_calibration_note: str = Field(default="Demo kalibrasyonu; kurum risk komitesi onayı gerekir.", max_length=500, pattern=r"^[^<>{}\x00-\x1f]*$")
    capital_method: Literal["analytical_credit_var"] = "analytical_credit_var"
    capital_confidence: float = Field(default=.99, ge=.90, lt=1.0)
    capital_model_status: Literal["pilot", "approved"] = "pilot"
    max_debt_service_ratio: float = Field(default=.60, gt=0.0, le=2.0)
    affordability_status: Literal["pilot", "approved"] = "pilot"
    limit_factors: list[Prob] = Field(default_factory=lambda: [0, .25, .50, .75, 1.0], min_length=2, max_length=10)
    max_pd: float = Field(default=.28, gt=0.0, lt=1.0)
    max_expected_loss_rate: Prob = .17
    min_raroc: float = Field(default=.10, ge=-10.0, le=10.0)
    target_margin_rate: float = Field(default=.015, ge=0.0, le=5.0)
    description: str = Field(default="", max_length=500, pattern=r"^[^<>{}\x00-\x1f]*$")

    @model_validator(mode="after")
    def risk_parameter_consistency(self):
        if self.risk_aversion is None and self.risk_tolerance_tl is None:
            self.risk_tolerance_tl = 125000.0
        if self.risk_aversion is not None and self.risk_tolerance_tl is not None:
            implied = 1.0 / self.risk_aversion
            if abs(implied - self.risk_tolerance_tl) > max(1.0, implied * 1e-4):
                raise ValueError("risk_aversion ile risk_tolerance_tl birbiriyle tutarlı olmalıdır.")
        return self


class MatrixRequest(BaseModel):
    actions: list[SafeShort] = Field(min_length=1, max_length=20)
    states: list[SafeShort] = Field(min_length=1, max_length=20)
    payoffs: list[list[FiniteWide]] = Field(min_length=1, max_length=20)
    probabilities: list[Prob] = Field(min_length=1, max_length=20)

    @field_validator("payoffs")
    @classmethod
    def max_matrix_width(cls, value: list[list[float]]) -> list[list[float]]:
        if any(not 1 <= len(row) <= 20 for row in value):
            raise ValueError("Kazanç matrisinin her satırı 1-20 değer içermelidir.")
        return value


class EVSIRequest(BaseModel):
    payoffs: list[list[FiniteWide]] = Field(min_length=1, max_length=20)
    prior_states: list[Prob] = Field(min_length=1, max_length=20)
    signal_given_state: list[list[Prob]] = Field(min_length=1, max_length=20)
    signal_names: list[SafeShort] | None = Field(default=None, max_length=20)

    @field_validator("payoffs", "signal_given_state")
    @classmethod
    def max_evsi_width(cls, value: list[list[float]]) -> list[list[float]]:
        if any(not 1 <= len(row) <= 20 for row in value):
            raise ValueError("Matris satırları 1-20 değer içermelidir.")
        return value


class BinomialRequest(BaseModel):
    alpha: float = Field(default=2, gt=0, le=1_000_000)
    beta: float = Field(default=18, gt=0, le=1_000_000)
    successes: int = Field(default=3, ge=0, le=10_000_000)
    failures: int = Field(default=47, ge=0, le=10_000_000)


class PoissonRequest(BaseModel):
    shape: float = Field(default=2, gt=0, le=1_000_000)
    rate: float = Field(default=4, gt=0, le=1_000_000)
    count: int = Field(default=3, ge=0, le=10_000_000)
    exposure: float = Field(default=5, gt=0, le=1_000_000_000)


class DiscreteBayesRequest(BaseModel):
    prior: list[Prob] = Field(min_length=1, max_length=100)
    likelihood: list[Prob] = Field(min_length=1, max_length=100)


class UtilityRequest(BaseModel):
    payoffs: list[list[FiniteWide]] = Field(min_length=1, max_length=20)
    probabilities: list[Prob] = Field(min_length=1, max_length=20)
    kind: Literal["linear", "exponential", "log", "sqrt"] = "exponential"
    risk_aversion: float = Field(default=.00002, ge=0.0, le=10.0)

    @field_validator("payoffs")
    @classmethod
    def max_utility_width(cls, value: list[list[float]]) -> list[list[float]]:
        if any(not 1 <= len(row) <= 20 for row in value):
            raise ValueError("Fayda matrisinin her satırı 1-20 değer içermelidir.")
        return value


class NewsvendorRequest(BaseModel):
    mean: float = Field(default=1000, ge=0, le=1_000_000_000)
    std: float = Field(default=180, gt=0, le=1_000_000_000)
    price: float = Field(default=125, ge=0, le=1_000_000_000)
    cost: float = Field(default=80, ge=0, le=1_000_000_000)
    salvage: float = Field(default=20, ge=-1_000_000_000, le=1_000_000_000)


class LinearRequest(BaseModel):
    a1_intercept: FiniteWide
    a1_slope: FiniteWide
    a2_intercept: FiniteWide
    a2_slope: FiniteWide


class EADRequest(BaseModel):
    drawn_amount: Money = 0.0
    undrawn_amount: Money = 0.0
    ccf: Prob = 0.0


class CreditExposureRequest(BaseModel):
    exposure_id: str = Field(min_length=1, max_length=80, pattern=r"^[^<>{}\x00-\x1f]+$")
    pd: float = Field(gt=0.0, lt=1.0)
    lgd: Prob
    ead: float = Field(ge=0.0, le=10_000_000_000.0)
    sector: str = Field(default="diger", min_length=1, max_length=80, pattern=r"^[^<>{}\x00-\x1f]+$")


class SingleRiskRequest(BaseModel):
    exposure: CreditExposureRequest
    confidence: float = Field(default=0.99, ge=0.50, lt=1.0)


class PortfolioRiskRequest(BaseModel):
    exposures: list[CreditExposureRequest] = Field(min_length=1, max_length=5000)
    correlation: float = Field(default=0.15, ge=0.0, lt=1.0)
    confidence: float = Field(default=0.999, ge=0.50, lt=1.0)
    simulations: int = Field(default=8000, ge=1000, le=20000)
    seed: int = Field(default=20260810, ge=0, le=2_147_483_647)
    run_monte_carlo: bool = True


class StressScenarioRequest(BaseModel):
    name: SafeShort
    pd_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    lgd_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    ead_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    probability: Prob | None = None


class StressRiskRequest(BaseModel):
    exposures: list[CreditExposureRequest] = Field(min_length=1, max_length=5000)
    scenarios: list[StressScenarioRequest] = Field(min_length=1, max_length=12)
    correlation: float = Field(default=0.15, ge=0.0, lt=1.0)
    confidence: float = Field(default=0.999, ge=0.50, lt=1.0)
