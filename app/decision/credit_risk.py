from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Iterable


@dataclass(frozen=True)
class CreditExposure:
    exposure_id: str
    pd: float
    lgd: float
    ead: float
    sector: str = "diger"

    def validate(self) -> None:
        if not 1 <= len(self.exposure_id) <= 80:
            raise ValueError("Risk kaydı kimliği 1-80 karakter arasında olmalıdır.")
        if not 0 < self.pd < 1:
            raise ValueError("PD 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.lgd <= 1:
            raise ValueError("LGD 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.ead <= 10_000_000_000:
            raise ValueError("EAD izin verilen aralığın dışında.")
        if not 1 <= len(self.sector) <= 80:
            raise ValueError("Sektör adı 1-80 karakter arasında olmalıdır.")

    @property
    def loss_if_default(self) -> float:
        return self.ead * self.lgd

    @property
    def expected_loss(self) -> float:
        return self.pd * self.loss_if_default

    @property
    def unexpected_loss(self) -> float:
        # Sabit EAD/LGD ve Bernoulli temerrüt göstergesi altında kaybın standart sapması.
        return self.loss_if_default * math.sqrt(self.pd * (1.0 - self.pd))


@dataclass(frozen=True)
class StressScenario:
    name: str
    pd_multiplier: float = 1.0
    lgd_multiplier: float = 1.0
    ead_multiplier: float = 1.0
    probability: float | None = None

    def validate(self) -> None:
        if not 1 <= len(self.name) <= 80:
            raise ValueError("Senaryo adı 1-80 karakter arasında olmalıdır.")
        for label, value in (
            ("PD çarpanı", self.pd_multiplier),
            ("LGD çarpanı", self.lgd_multiplier),
            ("EAD çarpanı", self.ead_multiplier),
        ):
            if not 0 <= value <= 10:
                raise ValueError(f"{label} 0 ile 10 arasında olmalıdır.")
        if self.probability is not None and not 0 <= self.probability <= 1:
            raise ValueError("Senaryo olasılığı 0 ile 1 arasında olmalıdır.")


def ead_from_commitment(drawn_amount: float, undrawn_amount: float, ccf: float) -> dict:
    if not 0 <= drawn_amount <= 10_000_000_000:
        raise ValueError("Kullanılmış tutar izin verilen aralığın dışında.")
    if not 0 <= undrawn_amount <= 10_000_000_000:
        raise ValueError("Kullanılmamış limit izin verilen aralığın dışında.")
    if not 0 <= ccf <= 1:
        raise ValueError("CCF 0 ile 1 arasında olmalıdır.")
    converted = undrawn_amount * ccf
    ead = drawn_amount + converted
    return {
        "drawn_amount": drawn_amount,
        "undrawn_amount": undrawn_amount,
        "ccf": ccf,
        "converted_undrawn": converted,
        "ead": ead,
        "formula": "EAD = kullanılmış tutar + CCF × kullanılmamış limit",
    }


def single_exposure_metrics(exposure: CreditExposure, confidence: float = 0.99) -> dict:
    exposure.validate()
    if not 0.5 <= confidence < 1:
        raise ValueError("Güven düzeyi 0.50 ile 1 arasında olmalıdır.")
    loss = exposure.loss_if_default
    el = exposure.expected_loss
    ul = exposure.unexpected_loss
    # İki-durumlu sabit EAD/LGD varsayımında kayıp yalnız 0 veya EAD×LGD olabilir.
    var = 0.0 if confidence <= 1.0 - exposure.pd else loss
    ec = max(0.0, var - el)
    return {
        "exposure": asdict(exposure),
        "recovery_rate": 1.0 - exposure.lgd,
        "loss_if_default": loss,
        "expected_loss": el,
        "expected_loss_rate": el / exposure.ead if exposure.ead else 0.0,
        "unexpected_loss": ul,
        "unexpected_loss_rate": ul / exposure.ead if exposure.ead else 0.0,
        "credit_var": var,
        "confidence": confidence,
        "economic_capital": ec,
        "method_note": "Tek kredi için iki-durumlu Bernoulli kayıp modeli; EAD ve LGD sabit kabul edilir.",
    }


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return float(sorted_values[idx])


def _sector_summary(exposures: list[CreditExposure]) -> tuple[list[dict], float]:
    total_ead = sum(x.ead for x in exposures)
    sector: dict[str, dict[str, float]] = {}
    for x in exposures:
        s = sector.setdefault(x.sector, {"ead": 0.0, "expected_loss": 0.0, "count": 0.0})
        s["ead"] += x.ead
        s["expected_loss"] += x.expected_loss
        s["count"] += 1
    rows = []
    hhi = 0.0
    for name, values in sector.items():
        share = values["ead"] / total_ead if total_ead else 0.0
        hhi += share * share
        rows.append({
            "sector": name,
            "count": int(values["count"]),
            "ead": values["ead"],
            "ead_share": share,
            "expected_loss": values["expected_loss"],
        })
    rows.sort(key=lambda x: x["ead"], reverse=True)
    return rows, hhi


def portfolio_analytic_metrics(exposures: Iterable[CreditExposure], default_correlation: float = 0.0, confidence: float = 0.999) -> dict:
    xs = list(exposures)
    if not xs:
        raise ValueError("Portföyde en az bir kredi olmalıdır.")
    if len(xs) > 5000:
        raise ValueError("Etkileşimli risk analizi en fazla 5.000 kredi kabul eder.")
    if not 0 <= default_correlation < 1:
        raise ValueError("Temerrüt korelasyonu 0 ile 1 arasında olmalıdır.")
    if not 0.5 <= confidence < 1:
        raise ValueError("Güven düzeyi 0.50 ile 1 arasında olmalıdır.")
    for x in xs:
        x.validate()
    el = sum(x.expected_loss for x in xs)
    terms = [x.loss_if_default * math.sqrt(x.pd * (1 - x.pd)) for x in xs]
    independent_var = sum(t * t for t in terms)
    correlated_var = independent_var + default_correlation * max(0.0, (sum(terms) ** 2 - independent_var))
    ul = math.sqrt(max(correlated_var, 0.0))
    z = NormalDist().inv_cdf(confidence)
    approx_var = max(0.0, el + z * ul)
    total_ead = sum(x.ead for x in xs)
    sectors, hhi = _sector_summary(xs)
    return {
        "count": len(xs),
        "total_ead": total_ead,
        "expected_loss": el,
        "expected_loss_rate": el / total_ead if total_ead else 0.0,
        "unexpected_loss": ul,
        "unexpected_loss_rate": ul / total_ead if total_ead else 0.0,
        "approx_credit_var": approx_var,
        "confidence": confidence,
        "economic_capital_approx": max(0.0, approx_var - el),
        "default_correlation": default_correlation,
        "sector_hhi": hhi,
        "sector_concentration": sectors,
        "method_note": "UL ve VaR, tek ortak korelasyon varsayımı altında analitik yaklaşık değerlerdir; regülasyon sermaye formülü değildir.",
    }


def monte_carlo_portfolio(
    exposures: Iterable[CreditExposure],
    simulations: int = 8000,
    asset_correlation: float = 0.15,
    seed: int = 20260810,
) -> dict:
    xs = list(exposures)
    if not xs:
        raise ValueError("Portföyde en az bir kredi olmalıdır.")
    if len(xs) > 5000:
        raise ValueError("Monte Carlo analizi en fazla 5.000 kredi kabul eder.")
    if not 1000 <= simulations <= 20000:
        raise ValueError("Simülasyon sayısı 1.000 ile 20.000 arasında olmalıdır.")
    if not 0 <= asset_correlation < 1:
        raise ValueError("Varlık korelasyonu 0 ile 1 arasında olmalıdır.")
    for x in xs:
        x.validate()

    nd = NormalDist()
    thresholds = [nd.inv_cdf(x.pd) for x in xs]
    severities = [x.loss_if_default for x in xs]
    sqrt_rho = math.sqrt(asset_correlation)
    sqrt_idio = math.sqrt(1.0 - asset_correlation)
    rng = random.Random(seed)
    losses: list[float] = []
    append = losses.append
    for _ in range(simulations):
        common = rng.gauss(0.0, 1.0)
        loss = 0.0
        common_part = sqrt_rho * common
        for threshold, severity in zip(thresholds, severities):
            latent = common_part + sqrt_idio * rng.gauss(0.0, 1.0)
            if latent < threshold:
                loss += severity
        append(loss)

    losses.sort()
    mean_loss = statistics.fmean(losses)
    ul = statistics.pstdev(losses)
    var95 = _quantile(losses, 0.95)
    var99 = _quantile(losses, 0.99)
    var999 = _quantile(losses, 0.999)
    tail99 = [v for v in losses if v >= var99]
    es99 = statistics.fmean(tail99) if tail99 else var99
    analytical_el = sum(x.expected_loss for x in xs)
    total_ead = sum(x.ead for x in xs)
    sectors, hhi = _sector_summary(xs)
    top_el = sorted(
        ({"exposure_id": x.exposure_id, "sector": x.sector, "ead": x.ead, "pd": x.pd, "lgd": x.lgd, "expected_loss": x.expected_loss} for x in xs),
        key=lambda r: r["expected_loss"], reverse=True,
    )[:20]
    return {
        "count": len(xs),
        "simulations": simulations,
        "seed": seed,
        "asset_correlation": asset_correlation,
        "total_ead": total_ead,
        "analytical_expected_loss": analytical_el,
        "simulation_mean_loss": mean_loss,
        "unexpected_loss": ul,
        "credit_var_95": var95,
        "credit_var_99": var99,
        "credit_var_999": var999,
        "expected_shortfall_99": es99,
        "economic_capital_99": max(0.0, var99 - analytical_el),
        "economic_capital_999": max(0.0, var999 - analytical_el),
        "expected_loss_rate": analytical_el / total_ead if total_ead else 0.0,
        "sector_hhi": hhi,
        "sector_concentration": sectors,
        "top_expected_loss_contributors": top_el,
        "method_note": "K-Risk pilot portföy motoru: tek-faktörlü korelasyonlu Monte Carlo. Düzenleyici sermaye hesaplamasının yerine geçmez.",
    }


def apply_scenario(exposures: Iterable[CreditExposure], scenario: StressScenario) -> list[CreditExposure]:
    scenario.validate()
    out = []
    for x in exposures:
        out.append(CreditExposure(
            exposure_id=x.exposure_id,
            pd=min(0.999999, max(0.000001, x.pd * scenario.pd_multiplier)),
            lgd=min(1.0, max(0.0, x.lgd * scenario.lgd_multiplier)),
            ead=max(0.0, x.ead * scenario.ead_multiplier),
            sector=x.sector,
        ))
    return out


def stress_portfolio(
    exposures: Iterable[CreditExposure],
    scenarios: Iterable[StressScenario],
    default_correlation: float = 0.15,
    confidence: float = 0.999,
) -> dict:
    xs = list(exposures)
    scs = list(scenarios)
    if not xs:
        raise ValueError("Portföy boş olamaz.")
    if not 1 <= len(scs) <= 12:
        raise ValueError("1-12 stres senaryosu tanımlanmalıdır.")
    results = []
    weighted_el = 0.0
    probability_sum = 0.0
    for sc in scs:
        transformed = apply_scenario(xs, sc)
        metrics = portfolio_analytic_metrics(transformed, default_correlation, confidence)
        row = {
            "scenario": sc.name,
            "pd_multiplier": sc.pd_multiplier,
            "lgd_multiplier": sc.lgd_multiplier,
            "ead_multiplier": sc.ead_multiplier,
            "probability": sc.probability,
            **metrics,
        }
        results.append(row)
        if sc.probability is not None:
            weighted_el += sc.probability * metrics["expected_loss"]
            probability_sum += sc.probability
    if probability_sum and abs(probability_sum - 1.0) > 1e-6:
        raise ValueError("Senaryo olasılıkları verilmişse toplamları 1 olmalıdır.")
    base = results[0]
    for row in results:
        row["el_change_vs_first"] = row["expected_loss"] - base["expected_loss"]
        row["el_change_pct_vs_first"] = (row["expected_loss"] / base["expected_loss"] - 1.0) if base["expected_loss"] else None
    worst = max(results, key=lambda r: r["expected_loss"])
    return {
        "base_scenario": base["scenario"],
        "results": results,
        "worst_scenario": worst["scenario"],
        "worst_expected_loss": worst["expected_loss"],
        "probability_weighted_expected_loss": weighted_el if probability_sum else None,
        "probability_sum": probability_sum if probability_sum else None,
        "method_note": "Senaryo motoru PD, LGD ve EAD çarpanlarını birlikte uygular; makro değişkenlerden bu çarpanlara dönüşüm kurumun kalibre edilmiş uydu modelinden gelmelidir.",
    }
