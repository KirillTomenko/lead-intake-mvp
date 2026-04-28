"""
Lead Intake MVP
---------------
A lightweight webhook service for capturing leads into SQLite with event logging.
"""

import logging
import os
import sqlite3
import csv
from io import StringIO
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from database import init_db, save_lead, get_all_leads, get_lead_by_id, get_leads_filtered, get_unique_sources, get_lead_stats
from models import LeadInput, LeadResponse, LeadListResponse, HealthResponse
from notifier import notify_new_lead, log_error

# ─── Load environment variables ───────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("events.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Lead Intake service starting up...")
    init_db()
    logger.info("✅ Database initialised")
    yield
    logger.info("🛑 Lead Intake service shut down")

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Lead Intake MVP",
    description="A lightweight webhook service that captures incoming leads, persists them to SQLite, and emits structured event logs.",
    version="1.0.0",
    contact={"name": "Lead Intake MVP", "url": "https://github.com/yourusername/lead-intake-mvp"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Templates ────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory="templates")

# ─── Static files (for favicon) ───────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Security (HTTP Basic Auth) ───────────────────────────────────────────────
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверка логина/пароля админа"""
    correct_username = os.getenv("ADMIN_USERNAME", "admin")
    correct_password = os.getenv("ADMIN_PASSWORD", "admin")
    
    if credentials.username != correct_username or credentials.password != correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ─── Validation error handler (400 instead of FastAPI default 422) ───────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Extract human-readable messages
    messages = []
    for e in errors:
        field = ".".join(str(loc) for loc in e.get("loc", []) if loc != "body")
        msg = e.get("msg", "Invalid value")
        if field:
            messages.append(f"{field}: {msg}")
        else:
            messages.append(msg)
    detail = "; ".join(messages) if messages else "Invalid request data"
    return JSONResponse(
        status_code=400,
        content={"status": "error", "code": 400, "message": detail},
    )

# ─── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_error(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "code": 500, "message": "Internal server error. The incident has been logged."},
    )

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Quick liveness check — useful for uptime monitors."""
    return {"status": "ok", "service": "lead-intake-mvp", "version": "1.0.0"}

# 🔐 Protected UI routes
@app.get("/", response_class=HTMLResponse, tags=["UI"], include_in_schema=False, dependencies=[Depends(verify_admin)])
async def dashboard(request: Request):
    """🎨 Русскоязычная панель управления"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/docs-ru", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(verify_admin)])
async def custom_docs_ru(request: Request):
    """📚 Русская документация"""
    return templates.TemplateResponse("docs_ru.html", {"request": request})

# 📋 Public API routes (no auth - for webhooks)
@app.post("/lead", response_model=LeadResponse, status_code=201, tags=["Leads"])
async def create_lead(lead: LeadInput):
    """Accept a lead payload, validate it, persist to SQLite, and emit notifications."""
    try:
        lead_id = save_lead(name=lead.name, contact=lead.contact, source=lead.source, comment=lead.comment)
    except RuntimeError as db_err:
        log_error(f"DB write failed: {db_err}")
        raise HTTPException(status_code=500, detail="Database unavailable.")
    
    # Async notifications (don't block response)
    import asyncio
    asyncio.create_task(notify_new_lead(lead_id=lead_id, contact=lead.contact, name=lead.name))
    
    return {"status": "ok", "message": "Lead accepted and saved.", "id": lead_id, "contact": lead.contact}

@app.get("/leads", response_model=LeadListResponse, tags=["Leads"])
async def list_leads():
    """Return all leads stored in the database."""
    try:
        leads = get_all_leads()
    except RuntimeError as db_err:
        log_error(f"DB read failed: {db_err}")
        raise HTTPException(status_code=500, detail="Could not read from database.")
    return {"status": "ok", "total": len(leads), "leads": leads}

# ✅ СНАЧАЛА КОНКРЕТНЫЕ РОУТЫ (с фиксированным путём)
@app.get("/leads/filter", tags=["Leads"])
async def filter_leads(request: Request):
    """Filter leads by date and source — 100% ручная обработка"""
    
    # 🔑 Получаем параметры ТОЛЬКО через request — без авто-валидации
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    source = request.query_params.get("source")
    
    # Отладка через print (безопасно в любых контекстах)
    print(f"🔍 Filter params: from={date_from}, to={date_to}, source={source}")
    
    # Очистка дат (мягкая)
    def clean_date(d):
        if not d or not isinstance(d, str):
            return None
        d = d.strip()
        # Проверяем: 10 символов, дефисы на 4-й и 7-й позиции
        if len(d) >= 10 and d[4] == '-' and d[7] == '-':
            return d[:10]  # Возвращаем только YYYY-MM-DD
        return None
    
    try:
        leads = get_leads_filtered(
            date_from=clean_date(date_from),
            date_to=clean_date(date_to),
            source=source,
        )
        print(f"✅ Filter result: {len(leads)} leads")
        return {"status": "ok", "total": len(leads), "leads": leads}
        
    except RuntimeError as db_err:
        # Используем log_error из notifier (он импортирован)
        log_error(f"Filter DB error: {db_err}")
        raise HTTPException(status_code=500, detail="Database error during filtering")
    except Exception as e:
        # Используем print + log_error для надёжности
        print(f"❌ Filter unexpected error: {type(e).__name__}: {e}")
        log_error(f"Filter unexpected error: {type(e).__name__}: {e}")
        # Возвращаем 400 вместо 422 — это наша ошибка, не валидация FastAPI
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": f"Invalid filter: {str(e)}"}
        )


@app.get("/leads/sources", tags=["Leads"])
async def get_sources():
    """Get unique sources list."""
    try:
        sources = get_unique_sources()
    except RuntimeError as db_err:
        log_error(f"Get sources failed: {db_err}")
        raise HTTPException(status_code=500, detail="Could not read sources.")
    return {"status": "ok", "sources": sources}


@app.get("/leads/export/csv", tags=["Leads"])
async def export_leads_csv(
    date_from: str | None = None, 
    date_to: str | None = None, 
    source: str | None = None
):
    """Export leads to CSV format (простой способ)"""
    try:
        leads = get_leads_filtered(date_from=date_from, date_to=date_to, source=source)
    except RuntimeError as db_err:
        log_error(f"CSV export failed: {db_err}")
        raise HTTPException(status_code=500, detail="Could not export data.")
    
    # 🔑 Формируем CSV вручную
    lines = []
    # BOM для Excel
    lines.append('\ufeffID;Дата создания;Имя;Контакт;Источник;Комментарий')
    
    for lead in leads:
        contact = str(lead.get('contact', ''))
        if contact and contact[0].isdigit():
            contact = "'" + contact
        
        # Экранируем точки с запятой в данных
        def escape_semicolon(val):
            if val is None:
                return ''
            val = str(val).replace(';', ',')  # Заменяем ; на ,
            return f'"{val}"' if ',' in str(val) else val
        
        row = ';'.join([
            escape_semicolon(lead.get('id', '')),
            escape_semicolon(lead.get('created_at', '')),
            escape_semicolon(lead.get('name', '')),
            escape_semicolon(contact),
            escape_semicolon(lead.get('source', '')),
            escape_semicolon(lead.get('comment', ''))
        ])
        lines.append(row)
    
    csv_content = '\n'.join(lines)
    csv_bytes = csv_content.encode('utf-8-sig')
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename=leads_{timestamp}.csv"
        }
    )


# ✅ ПОТОМ ДИНАМИЧЕСКИЕ РОУТЫ (с {параметрами})
@app.get("/leads/{lead_id}", tags=["Leads"])
async def get_lead(lead_id: int):
    """Retrieve a single lead record by its numeric ID."""
    try:
        lead = get_lead_by_id(lead_id)
    except RuntimeError as db_err:
        log_error(f"DB read failed: {db_err}")
        raise HTTPException(status_code=500, detail="Could not read from database.")
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead #{lead_id} not found.")
    return {"status": "ok", "lead": lead}


# 📊 Analytics
@app.get("/api/stats", tags=["Analytics"])
async def get_stats():
    """Get statistics for charts."""
    try:
        stats = get_lead_stats()
    except RuntimeError as db_err:
        log_error(f"Stats failed: {db_err}")
        raise HTTPException(status_code=500, detail="Could not get stats.")
    return stats