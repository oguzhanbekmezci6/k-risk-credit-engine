from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError

from app.api.routes import auth, decision, governance, overview, risk, science
from app.core.config import (
    ALLOWED_ORIGINS,
    API_PREFIX,
    APP_NAME,
    APP_VERSION,
    DOCS_ENABLED,
    MODEL_VERSION,
    MODE,
    TRUSTED_HOSTS,
)
from app.core.dependency_guard import verify_runtime_dependencies
from app.infra.db import init_db
from app.infra.security_middleware import OriginGuardMiddleware, RateLimitMiddleware, RequestSizeMiddleware, SecurityHeadersMiddleware

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MODE != "test":
        verify_runtime_dependencies()
    init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Öğrenme ve portföy amaçlı açıklanabilir kredi karar destek prototipi."
    ),
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)



FIELD_LABELS = {
    "username": "Kullanıcı adı",
    "password": "Şifre",
    "current_password": "Mevcut şifre",
    "new_password": "Yeni şifre",
    "setup_code": "Kurulum kodu",
    "applicant_id": "Başvuru numarası",
    "requested_amount": "Kredi tutarı",
    "term_months": "Vade",
    "product_type": "Kredi ürünü",
    "repayment_type": "Geri ödeme yapısı",
    "pd": "PD",
    "pd_basis": "PD ufku",
    "lgd": "LGD",
    "monthly_net_income": "Aylık net gelir / nakit akışı",
    "existing_monthly_debt_service": "Mevcut aylık borç servisi",
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic hata nesnelerini tarayıcıya ham obje olarak göndermeyiz.
    # Kullanıcıya kısa, Türkçe ve doğrudan düzeltilebilir bir mesaj döneriz.
    messages = []
    for err in exc.errors()[:5]:
        loc = err.get("loc", ())
        field = next((str(x) for x in reversed(loc) if isinstance(x, str) and x not in {"body", "query", "path"}), "Alan")
        label = FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
        msg = str(err.get("msg", "Geçersiz değer."))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        translations = {
            "Field required": "Bu alan zorunludur.",
            "String should have at least 1 character": "Bu alan boş bırakılamaz.",
        }
        msg = translations.get(msg, msg)
        messages.append(f"{label}: {msg}")
    return JSONResponse(status_code=422, content={"detail": " ".join(messages) or "Girilen bilgileri kontrol edin."})

app.add_middleware(RequestSizeMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(OriginGuardMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(TRUSTED_HOSTS))
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )
# Güvenlik başlıkları, middleware kaynaklı hata yanıtları dahil en dış katmanda uygulanır.
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory=STATIC), name="statik")
for router in [auth.router, overview.router, decision.router, risk.router, governance.router, science.router]:
    app.include_router(router, prefix=API_PREFIX)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health", include_in_schema=False)
def health():
    # Dış sağlık kontrolünde gereksiz sürüm/mimari bilgisi ifşa edilmez.
    return {"status": "ok"}
