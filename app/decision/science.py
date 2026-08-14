from __future__ import annotations
import math
from statistics import NormalDist
from typing import Sequence


def normalize_probabilities(probs: Sequence[float]) -> list[float]:
    if not probs or any(p < 0 for p in probs): raise ValueError("Olasılıklar negatif olamaz ve liste boş olamaz")
    total=float(sum(probs))
    if total <= 0: raise ValueError("Olasılık toplamı pozitif olmalıdır")
    return [float(p)/total for p in probs]


def regret_matrix(payoffs: Sequence[Sequence[float]]) -> list[list[float]]:
    if not payoffs or not payoffs[0]: raise ValueError("Kazanç matrisi boş olamaz")
    cols=len(payoffs[0])
    if any(len(r)!=cols for r in payoffs): raise ValueError("Kazanç matrisi dikdörtgen olmalıdır")
    maxima=[max(row[j] for row in payoffs) for j in range(cols)]
    return [[maxima[j]-float(row[j]) for j in range(cols)] for row in payoffs]


def decision_analysis(actions: Sequence[str], states: Sequence[str], payoffs: Sequence[Sequence[float]], probabilities: Sequence[float]) -> dict:
    if len(payoffs)!=len(actions) or not actions or not states or any(len(r)!=len(states) for r in payoffs): raise ValueError("Karar matrisi boyutları geçersiz")
    probs=normalize_probabilities(probabilities)
    if len(probs)!=len(states): raise ValueError("Olasılık ve doğa durumu sayıları eşleşmiyor")
    p=[[float(x) for x in row] for row in payoffs]
    regrets=regret_matrix(p)
    row_min=[min(r) for r in p]; row_max=[max(r) for r in p]; max_reg=[max(r) for r in regrets]
    ev=[sum(q*x for q,x in zip(probs,r)) for r in p]
    er=[sum(q*x for q,x in zip(probs,r)) for r in regrets]
    best_ev=max(range(len(actions)), key=lambda i:ev[i])
    perfect=sum(probs[j]*max(r[j] for r in p) for j in range(len(states)))
    return {
      "actions":list(actions),"states":list(states),"probabilities":probs,"payoffs":p,"regrets":regrets,
      "metrics":{
        "maximin":{"action":actions[max(range(len(actions)),key=lambda i:row_min[i])],"value":max(row_min),"values":row_min},
        "maximax":{"action":actions[max(range(len(actions)),key=lambda i:row_max[i])],"value":max(row_max),"values":row_max},
        "minimax_regret":{"action":actions[min(range(len(actions)),key=lambda i:max_reg[i])],"value":min(max_reg),"values":max_reg},
        "expected_value":{"action":actions[best_ev],"value":ev[best_ev],"values":ev},
        "expected_regret":{"action":actions[min(range(len(actions)),key=lambda i:er[i])],"value":min(er),"values":er},
        "ev_with_perfect_information":perfect,"evpi":max(0.0,perfect-ev[best_ev])
      }
    }


def evsi(payoffs: Sequence[Sequence[float]], prior_states: Sequence[float], signal_given_state: Sequence[Sequence[float]], signal_names: Sequence[str] | None=None) -> dict:
    prior=normalize_probabilities(prior_states); n_states=len(prior); n_actions=len(payoffs)
    if n_actions==0 or any(len(r)!=n_states for r in payoffs): raise ValueError("Kazanç matrisi boyutları geçersiz")
    if len(signal_given_state)!=n_states: raise ValueError("Olabilirlik matrisinde her doğa durumu için bir satır olmalıdır")
    n_signals=len(signal_given_state[0])
    if n_signals==0 or any(len(r)!=n_signals for r in signal_given_state): raise ValueError("Olabilirlik matrisi dikdörtgen olmalıdır")
    like=[normalize_probabilities(r) for r in signal_given_state]
    names=list(signal_names or [f"S{i+1}" for i in range(n_signals)])
    if len(names)!=n_signals: raise ValueError("Sinyal adları ile matris boyutu eşleşmiyor")
    base_values=[sum(prior[s]*payoffs[a][s] for s in range(n_states)) for a in range(n_actions)]
    base=max(base_values); after=0.0; details=[]
    for k in range(n_signals):
        ps=sum(prior[s]*like[s][k] for s in range(n_states))
        posterior=[prior[s]*like[s][k]/ps for s in range(n_states)] if ps>0 else [0.0]*n_states
        values=[sum(posterior[s]*payoffs[a][s] for s in range(n_states)) for a in range(n_actions)] if ps>0 else [0.0]*n_actions
        best=max(range(n_actions),key=lambda a:values[a]) if values else 0
        after += ps*values[best]
        details.append({"signal":names[k],"probability":ps,"posterior_states":posterior,"best_action_index":best,"best_value":values[best] if values else 0.0})
    return {"criterion":"expected_monetary_value","base_expected_value":base,"expected_value_with_sample_information":after,"evsi":max(0.0,after-base),"signals":details}


def beta_binomial_update(alpha: float,beta: float,successes:int,failures:int) -> dict:
    if alpha<=0 or beta<=0 or successes<0 or failures<0: raise ValueError("Beta-Binom parametreleri geçersiz")
    a=alpha+successes; b=beta+failures
    return {"prior":{"alpha":alpha,"beta":beta,"mean":alpha/(alpha+beta)},"data":{"successes":successes,"failures":failures},"posterior":{"alpha":a,"beta":b,"mean":a/(a+b),"variance":a*b/(((a+b)**2)*(a+b+1))},"next_prior":{"alpha":a,"beta":b}}


def gamma_poisson_update(shape:float,rate:float,count:int,exposure:float=1.0)->dict:
    if shape<=0 or rate<=0 or count<0 or exposure<=0: raise ValueError("Gamma-Poisson parametreleri geçersiz")
    s=shape+count; r=rate+exposure
    return {"prior":{"shape":shape,"rate":rate,"mean_lambda":shape/rate},"data":{"count":count,"exposure":exposure},"posterior":{"shape":s,"rate":r,"mean_lambda":s/r,"variance_lambda":s/(r*r)},"next_prior":{"shape":s,"rate":r}}


def discrete_bayes(prior:Sequence[float], likelihood:Sequence[float])->dict:
    if len(prior)!=len(likelihood) or not prior or any(x<0 for x in prior) or any(x<0 for x in likelihood): raise ValueError("Bayes vektörleri geçersiz")
    nums=[float(p)*float(l) for p,l in zip(prior,likelihood)]; evidence=sum(nums)
    if evidence<=0: raise ValueError("Kanıt/normalleştirme sabiti pozitif olmalıdır")
    return {"prior":list(prior),"likelihood":list(likelihood),"evidence":evidence,"posterior":[x/evidence for x in nums]}


def sampling_likelihood(total:int,target:int,draws:int,observed_targets:int,replacement:bool=False)->float:
    if total<=0 or not(0<=target<=total) or draws<0 or not(0<=observed_targets<=draws): raise ValueError("Örnekleme parametreleri geçersiz")
    if replacement:
        p=target/total; return math.comb(draws,observed_targets)*(p**observed_targets)*((1-p)**(draws-observed_targets))
    if draws>total or observed_targets>target or draws-observed_targets>total-target: return 0.0
    return math.comb(target,observed_targets)*math.comb(total-target,draws-observed_targets)/math.comb(total,draws)


def utility(x:float,kind:str="exponential",risk_aversion:float=.00002)->float:
    kind=kind.lower()
    if kind=="linear": return x
    if kind=="exponential":
        if risk_aversion<=0: raise ValueError("Riskten kaçınma parametresi pozitif olmalıdır")
        return -math.exp(max(-700,min(700,-risk_aversion*x)))
    if kind=="log": return math.log(max(1e-12,x+max(1.0,-x+1.0)))
    if kind=="sqrt": return math.sqrt(max(0.0,x+max(0.0,-x)))
    raise ValueError("Bilinmeyen fayda fonksiyonu")


def certainty_equivalent(expected_utility:float,kind:str,risk_aversion:float,outcomes:Sequence[float]|None=None)->float:
    if kind=="linear": return expected_utility
    if kind=="exponential":
        if expected_utility>=0: raise ValueError("Beklenen üstel fayda negatif olmalıdır")
        return -math.log(-expected_utility)/risk_aversion
    vals=list(outcomes or [-1e6,1e6]); lo=min(vals)-max(1000,abs(min(vals))); hi=max(vals)+max(1000,abs(max(vals)))
    for _ in range(120):
        mid=(lo+hi)/2
        if utility(mid,kind,risk_aversion)<expected_utility: lo=mid
        else: hi=mid
    return (lo+hi)/2


def evaluate_actions(payoffs:Sequence[Sequence[float]],probabilities:Sequence[float],kind:str="exponential",risk_aversion:float=.00002)->dict:
    probs=normalize_probabilities(probabilities)
    if any(len(r)!=len(probs) for r in payoffs): raise ValueError("Boyutlar eşleşmiyor")
    em=[sum(p*x for p,x in zip(probs,r)) for r in payoffs]
    eu=[sum(p*utility(x,kind,risk_aversion) for p,x in zip(probs,r)) for r in payoffs]
    ce=[certainty_equivalent(u,kind,risk_aversion,r) for u,r in zip(eu,payoffs)]
    return {"expected_money":em,"expected_utility":eu,"certainty_equivalent":ce,"risk_premium":[m-c for m,c in zip(em,ce)],"best_action_index":max(range(len(payoffs)),key=lambda i:eu[i])}


def newsvendor_optimal(mean:float,std:float,price:float,cost:float,salvage:float=0.0)->dict:
    if std<=0 or price<=cost or cost<salvage: raise ValueError("Fiyat > maliyet >= hurda değeri ve standart sapma > 0 olmalıdır")
    cr=(price-cost)/((price-cost)+(cost-salvage)); z=NormalDist().inv_cdf(cr)
    return {"critical_ratio":cr,"z":z,"optimal_quantity":mean+z*std}


def linear_payoff_intersection(a1_intercept:float,a1_slope:float,a2_intercept:float,a2_slope:float)->dict:
    den=a1_slope-a2_slope
    if abs(den)<1e-12: return {"has_intersection":False,"critical_mu":None}
    return {"has_intersection":True,"critical_mu":(a2_intercept-a1_intercept)/den}
