from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4

from app.api.deps import require
from app.api.schemas import EADRequest, PortfolioRiskRequest, SingleRiskRequest, StressRiskRequest
from app.decision.credit_risk import (
    CreditExposure,
    StressScenario,
    ead_from_commitment,
    monte_carlo_portfolio,
    portfolio_analytic_metrics,
    single_exposure_metrics,
    stress_portfolio,
)
from app.infra.db import audit

router = APIRouter(prefix="/risk", tags=["Kredi Riski ve Stres"])


def _exposure(item) -> CreditExposure:
    return CreditExposure(
        exposure_id=item.exposure_id,
        pd=item.pd,
        lgd=item.lgd,
        ead=item.ead,
        sector=item.sector,
    )


def _scenario(item) -> StressScenario:
    return StressScenario(
        name=item.name,
        pd_multiplier=item.pd_multiplier,
        lgd_multiplier=item.lgd_multiplier,
        ead_multiplier=item.ead_multiplier,
        probability=item.probability,
    )



@router.post("/ead", summary="CCF ile EAD hesapla")
def calculate_ead(req: EADRequest, user=Depends(require("admin", "risk_manager", "analyst"))):
    try:
        return ead_from_commitment(req.drawn_amount, req.undrawn_amount, req.ccf)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/single", summary="Tek kredi EL, UL, VaR ve ekonomik sermaye analizi")
def single(req: SingleRiskRequest, user=Depends(require("admin", "risk_manager", "analyst"))):
    try:
        return single_exposure_metrics(_exposure(req.exposure), req.confidence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/portfolio", summary="Portföy kredi riski analizi")
def portfolio(req: PortfolioRiskRequest, user=Depends(require("admin", "risk_manager"))):
    try:
        xs = [_exposure(x) for x in req.exposures]
        analytic = portfolio_analytic_metrics(xs, req.correlation, req.confidence)
        simulation = monte_carlo_portfolio(xs, req.simulations, req.correlation, req.seed) if req.run_monte_carlo else None
        result = {"analytic": analytic, "monte_carlo": simulation}
        audit(user["sub"], "kredi_riski_portfoy_analizi", "risk_calismasi", str(uuid4()), {"rows": len(xs), "correlation": req.correlation, "simulations": req.simulations if req.run_monte_carlo else 0})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stress", summary="PD-LGD-EAD stres senaryolarını çalıştır")
def stress(req: StressRiskRequest, user=Depends(require("admin", "risk_manager"))):
    try:
        xs = [_exposure(x) for x in req.exposures]
        scs = [_scenario(x) for x in req.scenarios]
        result = stress_portfolio(xs, scs, req.correlation, req.confidence)
        audit(user["sub"], "kredi_riski_stres_analizi", "risk_calismasi", str(uuid4()), {"rows": len(xs), "scenarios": [x.name for x in scs], "correlation": req.correlation})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


