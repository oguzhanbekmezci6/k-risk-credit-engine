from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_brand_assets_and_version():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
    css=(ROOT/"app/static/styles.css").read_text(encoding="utf-8")
    config=(ROOT/"app/core/config.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "14.1.2"' in config
    assert 'MODEL_VERSION = "credit-cashflow-risk-14.1.2"' in config
    assert 'k-risk-wordmark.png?v=14.1.2' in html
    assert 'styles.css?v=14.1.2' in html
    assert '--kr-red:#960000' in css
    assert 'K-RİSK' in html and 'KARAR MOTORU' in html

def test_login_is_purpose_first():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
    start=html.index('<div id="loginView"')
    end=html.index('<div id="passwordView"', start)
    login=html[start:end]
    assert '<h2>Giriş</h2>' in login
    assert 'Basit kullanım' not in login
    assert 'Açıklanabilir sonuç' not in login
    assert 'Yönetici raporu' not in login
    assert 'Kredi kararını' not in login

def test_all_runtime_pages_remain_available():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
    for page in ['overview','decision','history','risk','governance','science']:
        assert f'data-page="{page}"' in html

def test_learning_project_disclaimer_is_visible_and_documented():
    html=(ROOT/"app/static/index.html").read_text(encoding="utf-8")
    readme=(ROOT/"README.md").read_text(encoding="utf-8")
    report=(ROOT/"app/services/report_service.py").read_text(encoding="utf-8")
    notice="Bu uygulama gerçek değildir ve mezuniyet sonrası öğrenme amaçlı projedir."
    assert html.count(notice) >= 2
    assert notice in readme
    assert notice in report



def test_modern_native_typography_and_prominent_project_notice():
    css=(ROOT/"app/static/styles.css").read_text(encoding="utf-8")
    assert 'Aptos' in css
    assert 'Arial Nova' in css
    assert '--kr-font-ui' in css
    assert 'Segoe UI Variable Text' not in css
    assert 'font-family:Inter' not in css
    assert 'font:14px/1.5 Inter' not in css
    assert '.auth-disclaimer:before' in css
    assert 'ÖĞRENME PROJESİ' in css
    assert 'border-left:4px solid var(--kr-red)' in css
