from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import APP_VERSION, MODEL_VERSION
from app.core.formatting import tr_money, tr_number, tr_percent_ratio

REPORT_SCHEMA_VERSION = "3.0"


def _find_fonts():
    candidates = [
        ("Arial", Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        ("DejaVuSans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        ("LiberationSans", Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"), Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf")),
    ]
    for name, regular, bold in candidates:
        if regular.exists() and bold.exists():
            return name, regular, bold
    return None


def build_decision_pdf(record: dict, generated_by: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_info = _find_fonts()
    if font_info:
        family, regular_path, bold_path = font_info
        regular_name, bold_name = f"{family}-KR-Regular", f"{family}-KR-Bold"
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    else:
        regular_name, bold_name = "Helvetica", "Helvetica-Bold"

    RED = colors.HexColor("#840000")
    DARK = colors.HexColor("#1F2024")
    MUTED = colors.HexColor("#696A70")
    LINE = colors.HexColor("#E4E1E0")
    SOFT = colors.HexColor("#F7F5F4")
    GREEN = colors.HexColor("#16794A")
    AMBER = colors.HexColor("#8A5B13")

    out = BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title="K-Risk Karar Raporu", author="K-Risk",
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=base["Title"], fontName=bold_name, fontSize=19, leading=23, textColor=DARK, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontName=bold_name, fontSize=11.5, leading=14, textColor=DARK, spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("body", parent=base["BodyText"], fontName=regular_name, fontSize=8.4, leading=11.5, textColor=DARK, spaceAfter=3)
    small = ParagraphStyle("small", parent=body, fontSize=7.2, leading=9.5, textColor=MUTED)
    kicker = ParagraphStyle("kicker", parent=small, fontName=bold_name, textColor=RED, fontSize=7.5, leading=9, spaceAfter=3)
    cell = ParagraphStyle("cell", parent=small, textColor=DARK)
    cell_bold = ParagraphStyle("cellb", parent=cell, fontName=bold_name)

    request = record.get("request") or {}
    result = record.get("result") or {}
    override = record.get("override")
    policy = result.get("policy") or {}
    governance = result.get("policy_governance") or {}
    application_risk = result.get("application_risk") or {}
    requested = result.get("requested_scenario") or {}
    requested_econ = requested.get("economics") or {}
    requested_loan = requested.get("loan_economics") or {}
    requested_pricing = requested.get("pricing") or {}
    selected_econ = result.get("economics") or {}
    selected_loan = result.get("loan_economics") or {}
    selected_pricing = result.get("pricing") or {}
    controls = result.get("policy_controls") or []
    robustness = result.get("robustness") or {}
    market = result.get("market_context") or {}
    info = result.get("information_value") or {}
    science = result.get("decision_science") or {}

    final_decision = override.get("decision") if override else result.get("decision_label", result.get("decision", "-"))
    final_limit = override.get("limit") if override else result.get("recommended_limit", 0)
    selected = bool(final_limit and result.get("decision") == "ONAY")
    econ = selected_econ if selected else requested_econ
    loan = selected_loan if selected else requested_loan
    pricing = selected_pricing if selected else requested_pricing

    def val(v, default="-"):
        return default if v is None or v == "" else str(v)

    def money(v):
        if v is None:
            return "-"
        try:
            return tr_money(float(v))
        except Exception:
            return val(v)

    def pct(v):
        if v is None:
            return "-"
        try:
            return tr_percent_ratio(float(v), 1)
        except Exception:
            return val(v)

    def dt_tr(v):
        if not v:
            return "-"
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            dt = dt.astimezone(ZoneInfo("Europe/Istanbul"))
            months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
            return f"{dt.day} {months[dt.month-1]} {dt.year} · {dt:%H:%M} TRT"
        except Exception:
            return str(v)

    def product(v):
        return {"ihtiyac":"Bireysel ihtiyaç","konut":"Konut","tasit":"Taşıt","ticari_taksitli":"Taksitli ticari","spot":"Spot / vade sonu","diger":"Diğer"}.get(str(v), val(v))

    def repayment(v):
        return {"equal_installment":"Eşit taksit","equal_principal":"Eşit anapara","bullet":"Vade sonu anapara"}.get(str(v), val(v))

    def table(rows, widths, header=True):
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("GRID", (0,0), (-1,-1), .35, LINE), ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("FONTNAME", (0,0), (-1,-1), regular_name), ("FONTSIZE", (0,0), (-1,-1), 7),
            ("TOPPADDING", (0,0), (-1,-1), 4.2), ("BOTTOMPADDING", (0,0), (-1,-1), 4.2),
        ]
        if header:
            style += [("BACKGROUND", (0,0), (-1,0), SOFT), ("FONTNAME", (0,0), (-1,0), bold_name), ("TEXTCOLOR", (0,0), (-1,0), DARK)]
        t.setStyle(TableStyle(style))
        return t

    story = []
    logo_path = Path(__file__).resolve().parents[1] / "static" / "k-risk-logo.png"
    if logo_path.exists():
        logo = Image(str(logo_path), width=10 * mm, height=10 * mm)
        header = Table([[logo, Paragraph("K-RISK · KARAR RAPORU", kicker)]], colWidths=[13 * mm, 167 * mm])
        header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
        story.append(header)
    story.append(Paragraph("Karar Özeti", title))
    story.append(Paragraph(
        f"Başvuru <b>{val(record.get('applicant_id'))}</b> · Karar No {val(record.get('id'))}<br/>"
        f"{dt_tr(record.get('at'))} · Oluşturan {val(record.get('actor'))}", body
    ))

    summary = Table([
        ["KARAR", "LİMİT", "POLİTİKA", "STRES"],
        [final_decision, money(final_limit) if final_limit else "—", f"{val(policy.get('name'), record.get('policy_id'))} {val(policy.get('version'), '')}", val(robustness.get("label"))],
    ], colWidths=[40*mm, 45*mm, 50*mm, 45*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),SOFT),("FONTNAME",(0,0),(-1,0),bold_name),("FONTSIZE",(0,0),(-1,0),6.8),("TEXTCOLOR",(0,0),(-1,0),MUTED),
        ("FONTNAME",(0,1),(-1,1),bold_name),("FONTSIZE",(0,1),(-1,1),9.5),("GRID",(0,0),(-1,-1),.4,LINE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("TEXTCOLOR",(0,1),(0,1),GREEN if final_decision == "ONAY" else (AMBER if final_decision == "KISMİ ONAY" else RED)),
    ]))
    story += [Spacer(1, 3*mm), summary]

    story.append(Paragraph("1. Karar gerekçesi", h2))
    primary = result.get("primary_reason") or ("Politika kontrolleri geçti" if final_decision == "ONAY" else "Uygun pozitif limit bulunamadı")
    reason_rows = [[Paragraph("Birincil neden", cell_bold), Paragraph(f"<b>{val(primary)}</b><br/>{val(result.get('decision_summary'))}", cell)]]
    secondary = result.get("secondary_reasons") or []
    if secondary:
        reason_rows.append([Paragraph("Diğer bağlayıcı kontroller", cell_bold), Paragraph(" · ".join(map(str, secondary)), cell)])
    max_limit = float(result.get("max_feasible_limit") or 0)
    if 0 < max_limit < float(request.get("requested_amount") or 0):
        reason_rows.append([Paragraph("En yüksek uygun limit", cell_bold), Paragraph(money(max_limit), cell)])
    story.append(table(reason_rows, [47*mm, 133*mm], header=False))

    story.append(Paragraph("2. Başvuru özeti", h2))
    input_rows = [
        ["Kredi ürünü", product(request.get("product_type")), "Talep", money(request.get("requested_amount"))],
        ["Vade / ödeme", f"{val(request.get('term_months'))} ay · {repayment(request.get('repayment_type'))}", "Müşteri faizi", f"{pct((request.get('annual_rate') or 0)/12)} aylık · {pct(request.get('annual_rate'))} yıllık nominal"],
        ["12 aylık PD", pct(application_risk.get("pd_12m", request.get("pd"))), "LGD", pct(application_risk.get("lgd", request.get("lgd")))],
        ["Aylık net gelir", money(request.get("monthly_net_income")), "Mevcut aylık borç servisi", money(request.get("existing_monthly_debt_service"))],
        ["EAD çarpanı", val(request.get("ead_factor")), "Geç ödeme olasılığı", pct(request.get("late_probability"))],
        ["Geç ödeme kayıp oranı", pct(request.get("late_loss_rate")), "Teminat / ekspertiz", money(request.get("collateral_value"))],
        ["Başvuran yaşı", val(request.get("applicant_age_years")), "Başka konut", "Evet" if request.get("housing_has_other_home") else "Hayır"],
        ["Taşıt durumu", "2. el" if request.get("vehicle_is_used") else "0 km / belirtilmedi", "Taşıt yaşı", f"{val(request.get('vehicle_age_years'))} yıl"],
    ]
    story.append(table(input_rows, [38*mm, 52*mm, 43*mm, 47*mm], header=False))

    story.append(Paragraph("3. Politika kontrolleri", h2))
    control_rows = [["Kontrol", "Durum", "Gerçekleşen", "Sınır"]]
    for c in controls:
        unit = c.get("unit")
        actual = pct(c.get("actual")) if unit == "oran" else (money(c.get("actual")) if unit == "TL" else f"{val(c.get('actual'))} {val(unit, '')}".strip())
        limit = pct(c.get("limit")) if unit == "oran" else ("Zorunlu" if c.get("limit") is None else (money(c.get("limit")) if unit == "TL" else f"{val(c.get('limit'))} {val(unit, '')}".strip()))
        control_rows.append([Paragraph(val(c.get("name")), cell), val(c.get("status")), actual, limit])
    story.append(table(control_rows, [76*mm, 25*mm, 40*mm, 39*mm]))
    story.append(Paragraph(
        f"Politika eşikleri: maks. PD {pct(policy.get('max_pd'))} · maks. 12 aylık EL {pct(policy.get('max_expected_loss_rate'))} · "
        f"min. Pilot RAROC {pct(policy.get('min_raroc'))} · risk toleransı {money(governance.get('risk_tolerance_tl'))}.", small
    ))

    story.append(Paragraph("4. Kredi ekonomisi", h2))
    economy_rows = [
        ["Gösterge", "Değer", "Gösterge", "Değer"],
        ["İlk taksit", money(loan.get("monthly_payment")), "En yüksek dönem ödemesi", money(loan.get("max_contractual_payment"))],
        ["Beklenen NPV", money(econ.get("expected_npv")), "Beklenen zarar", money(econ.get("expected_loss"))],
        ["Pilot RAROC", pct(econ.get("raroc")), "12 aylık EL", money(econ.get("expected_loss_12m"))],
        ["Başabaş oran", pct(pricing.get("break_even_rate")), "Politika fiyat tabanı", pct(pricing.get("risk_adjusted_floor_rate"))],
    ]
    story.append(table(economy_rows, [49*mm, 41*mm, 49*mm, 41*mm]))
    if not selected:
        story.append(Paragraph("REDDET halinde bu bölüm, 0 TL red aksiyonu yerine talep edilen kredinin varsayımsal ekonomik görünümünü gösterir.", small))

    actions = result.get("decision_candidates") or []
    if actions:
        story.append(Paragraph("5. Değerlendirilen limitler", h2))
        rows = [["Aksiyon", "Limit", "NPV", "EL", "RAROC", "Sonuç"]]
        seen = 0
        for a in sorted(actions, key=lambda x: float(x.get("limit") or 0)):
            if seen >= 7:
                break
            status = "UYGUN" if a.get("feasible") else ", ".join(a.get("failed_constraints") or [])
            rows.append([val(a.get("action")), money(a.get("limit")), money(a.get("expected_npv")), money(a.get("expected_loss")), pct(a.get("raroc")), Paragraph(status, cell)])
            seen += 1
        story.append(table(rows, [32*mm, 31*mm, 28*mm, 28*mm, 24*mm, 37*mm]))

    scenarios = robustness.get("scenarios") or []
    if scenarios:
        story.append(Paragraph("6. Stres testi", h2))
        rows = [["Senaryo", "Şok", "Karar / Limit"]]
        names = {"baz":"Baz","yavaslama":"Yavaşlama","agir_stres":"Ağır stres"}
        for sc in scenarios:
            shock = "Mevcut varsayımlar" if sc.get("scenario") == "baz" else f"PD ×{tr_number(float(sc.get('pd_multiplier',1)), 2)} · LGD ×{tr_number(float(sc.get('lgd_multiplier',1)), 2)} · fonlama +{tr_number(float(sc.get('funding_add',0))*100, 1)} puan"
            limit = float(sc.get("recommended_limit") or 0)
            rows.append([names.get(sc.get("scenario"), val(sc.get("scenario"))), shock, money(limit) if limit else "REDDET"])
        story.append(table(rows, [38*mm, 92*mm, 50*mm]))

    if info:
        story.append(Paragraph("7. Ek bilgi değeri analizi", h2))
        evpi = float(science.get("evpi") or 0)
        story.append(Paragraph(
            f"EVSI <b>{money(info.get('evsi'))}</b> · bilgi maliyeti <b>{money(info.get('cost'))}</b> · net değer <b>{money(info.get('net_value'))}</b> · EVPI <b>{money(evpi)}</b>.<br/>"
            f"{val(info.get('interpretation'))}", body
        ))

    story.append(Paragraph("8. Piyasa referansı", h2))
    flow = market.get("public_lending_reference") or {}
    bank_ref = market.get("akbank_customer_rate_reference") or {}
    if request.get("product_type") == "konut":
        sector_rate = flow.get("housing_loan_rate")
    elif request.get("product_type") == "tasit":
        sector_rate = flow.get("vehicle_loan_rate")
    elif request.get("product_type") in {"ticari_taksitli", "spot"}:
        sector_rate = flow.get("tl_commercial_loan_rate")
    else:
        sector_rate = flow.get("consumer_loan_rate")
    story.append(Paragraph(
        f"Müşteri oranı <b>{pct((request.get('annual_rate') or 0)/12)} aylık</b>. "
        f"Akbank kamu örneği <b>{pct(bank_ref.get('monthly_rate'))} aylık</b> ({val(bank_ref.get('as_of'))}); "
        f"TCMB ilgili sektör akım faizi <b>{pct(sector_rate)} yıllık</b> ({val(flow.get('as_of'))}). "
        f"TCMB politika faizi <b>{pct(market.get('tcmb_policy_rate'))}</b> ({val(market.get('as_of'))}). "
        f"Pilot fonlama vekili <b>{pct(request.get('funding_cost'))}</b>; {val(market.get('funding_proxy_note'))}", body
    ))

    if override:
        story.append(Paragraph("9. Yetkili karar", h2))
        story.append(Paragraph(f"{val(override.get('actor'))}: <b>{val(override.get('decision'))}</b> · {money(override.get('limit'))}. Gerekçe: {val(override.get('reason'))}", body))

    story += [Spacer(1, 3*mm), Paragraph(
        "<b>PROJE UYARISI:</b> Bu uygulama gerçek değildir ve mezuniyet sonrası öğrenme amaçlı projedir. Bu rapor gerçek banka kredi kararı veya kurum onayı değildir.", small
    )]

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(15*mm, 10.5*mm, 195*mm, 10.5*mm)
        canvas.setFont(regular_name, 6.3)
        canvas.setFillColor(MUTED)
        canvas.drawString(15*mm, 6.8*mm, "K-Risk · Karar Raporu")
        canvas.drawCentredString(105*mm, 6.8*mm, f"Platform {APP_VERSION} · Motor {MODEL_VERSION} · Rapor {REPORT_SCHEMA_VERSION}")
        canvas.drawRightString(195*mm, 6.8*mm, f"Sayfa {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def report_filename(record: dict) -> str:
    applicant = "".join(ch for ch in str(record.get("applicant_id") or "basvuru") if ch.isalnum() or ch in "-_")[:40]
    decision = "".join(ch for ch in str(record.get("id") or "karar") if ch.isalnum() or ch in "-_")[:16]
    return f"K-Risk_Karar_Raporu_{applicant}_{decision}.pdf"
