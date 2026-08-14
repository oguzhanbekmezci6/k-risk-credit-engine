from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_keeps_guided_enterprise_help_center():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert "K-RISK" in html
    assert "Açıklamaları Göster" in html
    assert "Yardım Merkezi" in html
    assert "helpSearch" in html
    assert "Bu Ekran" in html and "Kavram Sözlüğü" in html
    assert "pageGuides" in js and "helpData" in js
    assert "applyExplanationMode" in js
    assert ".page-guide" in css and ".decision-path" in css


def test_explains_core_fields_and_results():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    for text in [
        "Talep edilen kredi tutarı", "Temerrüt olasılığı", "Temerrütte zarar",
        "Varsayımsal ek bilgi maliyeti",
    ]:
        assert text in html
    for key in ["expected_profit", "expected_loss", "raroc", "evsi", "evpi", "stress", "audit"]:
        assert f"{key}:" in js
    assert "Kararı etkileyen politika kontrolleri" in js


def test_validation_is_actionable_and_safe():
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "validateDecisionForm" in js
    assert "Devam etmek için" in js
    assert "innerHTML" not in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
