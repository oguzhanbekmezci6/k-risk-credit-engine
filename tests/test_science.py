import math
from app.decision.science import decision_analysis, evsi, beta_binomial_update, gamma_poisson_update, discrete_bayes, sampling_likelihood, evaluate_actions, newsvendor_optimal, linear_payoff_intersection

def test_decision_matrix_core():
    r=decision_analysis(["A","B"],["good","bad"],[[10,-4],[6,2]],[.7,.3])
    assert r["metrics"]["expected_value"]["action"]=="A"
    assert r["metrics"]["maximin"]["action"]=="B"
    assert r["metrics"]["evpi"]>=0

def test_regret_is_nonnegative():
    r=decision_analysis(["A","B"],["x","y"],[[1,4],[3,2]],[.5,.5])
    assert all(x>=0 for row in r["regrets"] for x in row)

def test_evsi_nonnegative():
    r=evsi([[100,-50],[40,20]],[.7,.3],[[.8,.2],[.2,.8]],["g","b"])
    assert r["evsi"]>=0

def test_beta_binomial_sequential_prior():
    first=beta_binomial_update(2,18,3,47)
    second=beta_binomial_update(first["next_prior"]["alpha"],first["next_prior"]["beta"],2,18)
    assert second["prior"]["alpha"]==5
    assert second["posterior"]["alpha"]==7

def test_gamma_poisson():
    r=gamma_poisson_update(2,4,3,5)
    assert r["posterior"]["shape"]==5
    assert r["posterior"]["rate"]==9

def test_discrete_bayes_normalizes():
    r=discrete_bayes([.6,.4],[.2,.8])
    assert math.isclose(sum(r["posterior"]),1.0)

def test_sampling_without_replacement():
    p=sampling_likelihood(5,1,2,1,False)
    assert math.isclose(p,.4)

def test_utility_output():
    r=evaluate_actions([[100,-100],[40,10]],[.5,.5],"exponential",.01)
    assert len(r["certainty_equivalent"])==2

def test_normal_rule():
    r=newsvendor_optimal(100,10,20,12,4)
    assert 0<r["critical_ratio"]<1
    assert r["optimal_quantity"]>0

def test_linear_intersection():
    r=linear_payoff_intersection(0,2,10,1)
    assert r["has_intersection"] and math.isclose(r["critical_mu"],10)
