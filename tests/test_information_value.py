from pathlib import Path
from app.decision.credit import DEFAULT_SIGNAL, evaluate_credit
from app.domain.models import Applicant, Policy

ROOT = Path(__file__).resolve().parents[1]

def _policy():
    return Policy("dengeli","Dengeli","8.1","active",.000008,(0,.25,.5,.75,1),.18,.17,.08,.015)

def _applicant():
    return Applicant("SIM-001",5_000_000,.06,.20,annual_rate=.32,funding_cost=.18,operating_cost=900,capital_cost_rate=.03,late_probability=.10,late_loss_rate=.04)

def test_information_value_is_calculation_only():
    r=evaluate_credit(_applicant(),_policy(),DEFAULT_SIGNAL)
    info=r["information_value"]
    assert info["is_simulation"] is True
    assert info["source_mode"] == "simulation"
    assert "kredi bürosu" not in info["name"].lower()
    assert "recommendation" not in info
    assert info["action_recommendation"] is None
    assert isinstance(info["evsi"], float)
    assert isinstance(info["net_value"], float)

def test_ui_has_k_risk_brand_and_no_buy_sell_recommendation():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"app/static/app.js").read_text(encoding="utf-8")
    assert "K-RİSK" in html
    assert "k-risk-logo.png" in html
    assert "SATIN AL" not in js
    assert "ALMA" not in js
    assert "Ek Bilgi Değeri Analizi" in js
    assert "SİMÜLASYON" in html or "SİMÜLASYON" in js

def test_pdf_is_neutral_about_information_purchase_and_branded():
    src=(ROOT/"app/services/report_service.py").read_text(encoding="utf-8")
    assert "K-RISK" in src
    assert "k-risk-logo.png" in src
    assert "Ek bilgi değeri analizi" in src
    assert "SATIN AL" not in src
    assert "Sistem önerisi" not in src

def test_logo_assets_exist():
    for name in ("k-risk-logo.png","k-risk-favicon.png"):
        p=ROOT/"app/static"/name
        assert p.exists() and p.stat().st_size > 1000
