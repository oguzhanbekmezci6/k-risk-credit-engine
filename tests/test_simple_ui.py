from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_and_economic_model_versions():
    config = (ROOT / 'app/core/config.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "14.1.2"' in config
    # V11 changes the economic model: taxes/funds, unified states, workout funding and pricing guardrail.
    assert 'MODEL_VERSION = "credit-cashflow-risk-14.1.2"' in config


def test_customer_rate_is_a_primary_decision_field():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    assert html.count('id="dRate"') == 1
    assert 'Müşteriye uygulanan aylık faiz (%)' in html
    assert 'value="3.84"' in html
    assert html.index('id="dRate"') < html.index('<details class="advanced-box v4-advanced">')


def test_explanations_are_quiet_by_default_but_remain_available():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
    assert 'let explanationsOn = false;' in js
    assert 'id="explainModeBtn"' in html
    assert 'Açıklamaları Göster' in html
    assert 'id="helpBtn"' in html and 'id="helpDrawer"' in html


def test_topbar_is_reduced_to_two_daily_actions():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    start = html.index('<div class="top-actions">')
    end = html.index('</div>', start)
    top = html[start:end]
    assert 'topNewDecisionBtn' in top
    assert 'helpBtn' in top
    assert 'version-pill' not in top
    assert 'explainModeBtn' not in top


def test_decision_result_prioritises_four_daily_metrics():
    js = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
    for text in ['Talep edilen', 'Önerilen limit', '12 aylık PD', 'İlk taksit']:
        assert text in js
    assert 'Ayrıntılı analizi göster' in js
    assert "panel('Risk ve ekonomi özeti'" in js


def test_large_type_overrides_exist():
    css = (ROOT / 'app/static/styles.css').read_text(encoding='utf-8')
    assert '.topbar h2{font-size:31px' in css
    assert '.decision-title{font-size:36px' in css
    assert 'font-size:15px' in css  # form controls
    assert '.nav{min-height:50px;font-size:14px' in css


def test_runtime_functions_not_removed_from_navigation():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    for page in ['overview', 'decision', 'history', 'risk', 'governance', 'science']:
        assert f'data-page="{page}"' in html


def test_v101_removes_file_upload_portfolio_feature():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
    main = (ROOT / 'app/main.py').read_text(encoding='utf-8')
    risk = (ROOT / 'app/api/routes/risk.py').read_text(encoding='utf-8')
    req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'data-page="portfolio"' not in html
    assert 'type="file"' not in html
    assert 'demo_portfolio.csv' not in html + js
    assert '/portfolio-csv' not in risk and '/stress-csv' not in risk
    assert 'portfolio.router' not in main
    assert 'python-multipart' not in req
