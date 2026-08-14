from app.domain.models import Applicant, Policy
from app.decision.credit import evaluate_credit, DEFAULT_SIGNAL

BAL=Policy("balanced","Balanced","3.0","active",.000022,(0,.25,.5,.75,1),.28,.17,.10,.015)

def applicant(pd=.08):
    return Applicant("X",150000,pd,.55,annual_rate=.32,funding_cost=.18,operating_cost=900,capital_cost_rate=.03,late_probability=.10,late_loss_rate=.04)

def test_credit_returns_complete_decision():
    r=evaluate_credit(applicant(),BAL,DEFAULT_SIGNAL)
    assert r["decision"] in {"ONAY","REDDET"}
    assert len(r["actions"])==5
    assert "evpi" in r["decision_science"]
    assert "recommendation" not in r["information_value"]
    assert r["information_value"]["action_recommendation"] is None
    assert len(r["trace"])>=5

def test_stress_not_more_aggressive_than_base_for_demo():
    r=evaluate_credit(applicant(),BAL,None)
    limits=[x["recommended_limit"] for x in r["robustness"]["scenarios"]]
    assert limits[1] <= limits[0]
    assert limits[2] <= limits[1]

def test_high_pd_hits_guardrail():
    r=evaluate_credit(applicant(.32),BAL,None)
    assert r["recommended_limit"]==0
    assert r["decision"]=="REDDET"

def test_pricing_floor_is_transparent():
    r=evaluate_credit(applicant(),BAL,None)
    if r["recommended_limit"]>0:
        assert r["pricing"]["break_even_rate"]>0
        assert r["pricing"]["risk_adjusted_floor_rate"]>=r["pricing"]["break_even_rate"]

def test_applicant_validation():
    bad=Applicant("X",1000,1.2,.5)
    try: bad.validate()
    except ValueError: pass
    else: raise AssertionError("invalid PD should fail")
