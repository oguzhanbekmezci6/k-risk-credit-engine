from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require
from app.api.schemas import (
    BinomialRequest,
    DiscreteBayesRequest,
    EVSIRequest,
    LinearRequest,
    MatrixRequest,
    NewsvendorRequest,
    PoissonRequest,
    UtilityRequest,
)
from app.decision.science import (
    beta_binomial_update,
    decision_analysis,
    discrete_bayes,
    evaluate_actions,
    evsi,
    gamma_poisson_update,
    linear_payoff_intersection,
    newsvendor_optimal,
)

router = APIRouter(prefix="/science", tags=["Karar Bilimi"])
_AUTH = Depends(require("admin", "risk_manager"))


def call(fn, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/matrix", summary="Karar matrisi analizi")
def matrix(req: MatrixRequest, user=_AUTH):
    return call(decision_analysis, req.actions, req.states, req.payoffs, req.probabilities)


@router.post("/evsi", summary="Örneklem bilgisinin beklenen değerini hesapla")
def sample_info(req: EVSIRequest, user=_AUTH):
    return call(evsi, req.payoffs, req.prior_states, req.signal_given_state, req.signal_names)


@router.post("/bayes/binomial", summary="Beta-Binom Bayes güncellemesi")
def binomial(req: BinomialRequest, user=_AUTH):
    return call(beta_binomial_update, req.alpha, req.beta, req.successes, req.failures)


@router.post("/bayes/poisson", summary="Gamma-Poisson Bayes güncellemesi")
def poisson(req: PoissonRequest, user=_AUTH):
    return call(gamma_poisson_update, req.shape, req.rate, req.count, req.exposure)


@router.post("/bayes/discrete", summary="Ayrık Bayes güncellemesi")
def discrete(req: DiscreteBayesRequest, user=_AUTH):
    return call(discrete_bayes, req.prior, req.likelihood)


@router.post("/utility", summary="Beklenen fayda analizi")
def util(req: UtilityRequest, user=_AUTH):
    return call(evaluate_actions, req.payoffs, req.probabilities, req.kind, req.risk_aversion)


@router.post("/normal/newsvendor", summary="Normal dağılım altında optimal miktar")
def normal(req: NewsvendorRequest, user=_AUTH):
    return call(newsvendor_optimal, req.mean, req.std, req.price, req.cost, req.salvage)


@router.post("/linear/intersection", summary="Doğrusal kazanç fonksiyonlarının kesişimi")
def linear(req: LinearRequest, user=_AUTH):
    return call(linear_payoff_intersection, req.a1_intercept, req.a1_slope, req.a2_intercept, req.a2_slope)
