"""
Municipal Intel - FastAPI Application

FastAPI backend for municipal government ERP lead intelligence platform.
Replaces Streamlit with persistent database, background task processing, and responsive UI.
"""

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends, Response, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import json
import os

from src.database import init_db, get_db, Scan, Lead, Municipality, MunicipalSource, User
from src.discovery import SourceDiscovery
from src.scraper import MunicipalScraper
from src.analyzer import DocumentAnalyzer
from src.signals import SIGNALS
from src.auth import (
    create_magic_link,
    verify_magic_link,
    get_current_user,
    get_current_user_optional,
    require_role,
    set_session_cookie,
    clear_session_cookie,
    send_magic_link_email,
    APP_URL,
    RESEND_API_KEY
)

# Initialize FastAPI app
app = FastAPI(title="Municipal Intel", version="2.0")

# Initialize database
init_db()


# ============================================================
# EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    """Redirect unauthenticated browser requests to /login."""
    # API requests get JSON error; page requests get redirect
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    """Return a clean 403 page for unauthorized role access."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(
            content="""<!DOCTYPE html><html><head><title>Access Denied</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#F5F3EF;}
.box{max-width:400px;text-align:center;padding:2rem;}h1{font-size:1.5rem;color:#1A1816;margin-bottom:0.5rem;}p{color:#3D3A35;margin-bottom:1.5rem;}
a{color:#1E3BC0;text-decoration:none;font-weight:500;}</style></head>
<body><div class="box"><h1>Access Denied</h1><p>You don't have permission to view this page.</p>
<a href="/dashboard">&larr; Go to Dashboard</a></div></body></html>""",
            status_code=403
        )
    return JSONResponse(status_code=403, content={"detail": str(exc.detail)})


# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ============================================================
# PYDANTIC MODELS
# ============================================================

class MagicLinkRequest(BaseModel):
    email: EmailStr


class ScanConfig(BaseModel):
    states: List[str]
    population_tier: str  # micro | small | small-mid | mid-market | upper-mid | large
    source_types: Optional[List[str]] = None  # meeting_minutes, procurement, etc.


class LeadUpdate(BaseModel):
    notes: Optional[str] = None


class AdminApproveRequest(BaseModel):
    email: str
    role: str = "client"  # client | consultant | admin


class RoleUpdateRequest(BaseModel):
    role: str


# ============================================================
# POPULATION TIER RANGES
# ============================================================

POPULATION_TIERS = {
    "micro": (0, 2500),
    "small": (2500, 10000),
    "small-mid": (10000, 25000),
    "mid-market": (25000, 75000),
    "upper-mid": (75000, 150000),
    "large": (150000, 999999999)
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_population_range(tier: str) -> tuple:
    """Get population min/max for a given tier."""
    return POPULATION_TIERS.get(tier, (0, 999999999))


def update_scan_progress(db: Session, scan_id: str, phase: str, pct: int, message: str):
    """Update scan progress in database."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if scan:
        scan.progress_phase = phase
        scan.progress_pct = pct
        scan.progress_message = message
        db.commit()


def run_scan(scan_id: str, config: dict):
    """
    Background task: Execute a scan.

    Reads enriched sources from MunicipalSource table.
    For unenriched cities, falls back to URL probing (discovery.py).
    Writes progress updates and leads to database as it goes.
    """
    from src.database import SessionLocal
    db = SessionLocal()

    # Initialize scraper and analyzer
    scraper = MunicipalScraper(delay=1.5, timeout=8, max_docs=10)
    analyzer = DocumentAnalyzer(use_llm=False)  # Disable LLM for speed
    discovery = SourceDiscovery(request_delay=1.0, timeout=8)

    try:
        # Get scan record
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            return

        # Update status to running
        scan.status = "running"
        db.commit()

        # Parse config
        states = config.get("states", [])
        population_tier = config.get("population_tier", "small")
        source_types = config.get("source_types", ["meeting_minutes", "procurement"])

        # Get population range
        pop_min, pop_max = get_population_range(population_tier)

        # Phase 1: Discovery - Get municipalities
        update_scan_progress(db, scan_id, "discovery", 0, "Loading municipalities...")

        municipalities = db.query(Municipality).filter(
            Municipality.state.in_(states),
            Municipality.population >= pop_min,
            Municipality.population <= pop_max
        ).all()

        total_cities = len(municipalities)
        update_scan_progress(db, scan_id, "discovery", 10, f"Found {total_cities} cities to scan")

        # Phase 2: Scraping & Analysis
        sources_found = 0
        docs_scraped = 0
        leads_hot = 0
        leads_warm = 0
        leads_cold = 0

        for idx, muni in enumerate(municipalities):
            progress_pct = 10 + int((idx / total_cities) * 80)  # 10-90%
            update_scan_progress(db, scan_id, "scraping", progress_pct, f"Scanning {muni.name}, {muni.state}...")

            # Check if municipality has enriched sources
            enriched_sources = db.query(MunicipalSource).filter(
                MunicipalSource.municipality_id == muni.id
            ).all()

            if enriched_sources:
                # Use enriched sources - scrape each one
                sources_found += len(enriched_sources)
                for source in enriched_sources:
                    try:
                        # Scrape documents from this source
                        scraped_docs = scraper.scrape_source(source)
                        docs_scraped += len(scraped_docs)

                        # Analyze each document
                        for doc in scraped_docs:
                            result = analyzer.analyze_document(
                                doc,
                                population=muni.population,
                                min_score=30,
                                source_type=source.source_type
                            )

                            if result:
                                # Create lead record
                                lead = Lead(
                                    scan_id=scan_id,
                                    municipality=result.municipality,
                                    state=result.state,
                                    population=result.population,
                                    title=result.title,
                                    url=result.url,
                                    date=result.date,
                                    source_type=result.source_type,
                                    relevance_score=result.relevance_score,
                                    lead_type=result.lead_type,
                                    customer_status=result.customer_status,
                                    recommended_action=result.recommended_action,
                                    signal_matches_json={
                                        m.signal_type: {
                                            "keyword": m.keyword,
                                            "context": m.context,
                                            "weight": m.weight
                                        }
                                        for m in result.signal_matches
                                    }
                                )
                                db.add(lead)
                                db.commit()

                                # Update lead counts
                                if lead.lead_type == "hot":
                                    leads_hot += 1
                                elif lead.lead_type == "warm":
                                    leads_warm += 1
                                else:
                                    leads_cold += 1

                    except Exception as e:
                        print(f"Error scraping source {source.url}: {str(e)}")
                        continue
            else:
                # Fall back to discovery (URL probing) for unenriched cities
                # Skip for now - this is slow and most cities should be enriched
                pass

        # Phase 3: Complete
        update_scan_progress(db, scan_id, "complete", 100, "Scan complete")

        # Update final stats
        scan.status = "completed"
        scan.completed_at = datetime.utcnow()
        scan.stats_json = {
            "sources_found": sources_found,
            "docs_scraped": docs_scraped,
            "leads_hot": leads_hot,
            "leads_warm": leads_warm,
            "leads_cold": leads_cold,
            "total_leads": leads_hot + leads_warm + leads_cold
        }
        db.commit()

    except Exception as e:
        # Mark scan as failed
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if scan:
            scan.status = "failed"
            scan.progress_message = f"Error: {str(e)}"
            db.commit()
        print(f"Scan {scan_id} failed: {str(e)}")

    finally:
        db.close()


# ============================================================
# PUBLIC ROUTES
# ============================================================

@app.get("/", response_class=FileResponse)
async def landing():
    """Serve public landing page as a static file (no template processing)."""
    return FileResponse("static/landing.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0"}


# ============================================================
# WAITLIST ENDPOINT
# ============================================================

class WaitlistRequest(BaseModel):
    email: str
    name: Optional[str] = None
    title: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None
    current_erp: Optional[str] = None
    open_to_contact: Optional[bool] = None
    company: Optional[str] = None
    interest: Optional[str] = None
    source: Optional[str] = None  # 'municipality' or 'consultant'

@app.post("/api/waitlist")
async def join_waitlist(request: WaitlistRequest, db: Session = Depends(get_db)):
    """Add email to waitlist. Returns 200 even on duplicate to avoid leaking whether an email exists."""
    try:
        db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS waitlist (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    title TEXT,
                    municipality TEXT,
                    state TEXT,
                    current_erp TEXT,
                    open_to_contact BOOLEAN,
                    company TEXT,
                    interest TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        )
        db.execute(
            text("""
                INSERT INTO waitlist
                (email, name, title, municipality, state, current_erp, open_to_contact, company, interest, source)
                VALUES (:email, :name, :title, :municipality, :state, :current_erp, :open_to_contact, :company, :interest, :source)
                ON CONFLICT (email) DO NOTHING
            """),
            {
                "email": request.email.lower().strip(),
                "name": request.name,
                "title": request.title,
                "municipality": request.municipality,
                "state": request.state,
                "current_erp": request.current_erp,
                "open_to_contact": request.open_to_contact,
                "company": request.company,
                "interest": request.interest,
                "source": request.source
            }
        )
        db.commit()
    except Exception:
        db.rollback()
    return {"status": "ok"}


# ============================================================
# AUTHENTICATION ENDPOINTS
# ============================================================

@app.post("/api/auth/request-magic-link")
async def request_magic_link(request: MagicLinkRequest, db: Session = Depends(get_db)):
    """
    Send a magic link to the user's email.

    Only sends if the user has been approved (exists in users table).
    Always returns 200 — never leak whether an email is registered.
    """
    magic_link = create_magic_link(db, request.email)

    if magic_link:
        # User exists — build and send the link
        magic_url = f"{APP_URL}/auth/verify/{magic_link.token}"
        send_magic_link_email(request.email, magic_url)

        response = {"success": True, "registered": True}

        # Dev mode: include link in response
        if not RESEND_API_KEY:
            response["dev_link"] = magic_url
    else:
        # User not found — tell frontend to show "thank you" holding message
        response = {"success": True, "registered": False}

    return response


@app.get("/auth/verify/{token}")
async def verify_magic_link_route(token: str, db: Session = Depends(get_db)):
    """
    Verify magic link token and create session.

    Redirects based on user role:
      client    → /dashboard
      consultant → /municipal-intel
      admin     → /municipal-intel
    """
    user = verify_magic_link(db, token)

    if not user:
        return RedirectResponse(url="/login?error=invalid_link", status_code=303)

    # Set cookie directly on the RedirectResponse — not on the injected Response,
    # which is a different object and won't carry cookies through the redirect.
    redirect = RedirectResponse(url="/app", status_code=303)
    set_session_cookie(redirect, user)
    return redirect


@app.post("/api/auth/logout")
async def logout(response: Response):
    """Logout user by clearing session cookie."""
    clear_session_cookie(response)
    return {"success": True}


# ============================================================
# AUTH PAGE ROUTES
# ============================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Login page with magic link form.

    If already authenticated, redirect to appropriate dashboard.
    """
    if user:
        return RedirectResponse(url="/app", status_code=303)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })


# ============================================================
# PROTECTED APP ROUTES
# ============================================================

@app.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    """Redirect legacy /dashboard to unified /app shell."""
    return RedirectResponse(url="/app", status_code=303)


@app.get("/municipal-intel")
async def municipal_intel(user: dict = Depends(get_current_user)):
    """Redirect legacy /municipal-intel to unified /app shell."""
    return RedirectResponse(url="/app", status_code=303)


@app.get("/app", response_class=HTMLResponse)
async def app_shell(request: Request, user: dict = Depends(get_current_user)):
    """
    Unified app shell with role-conditional tabs:
      - Dashboard (all roles)
      - Scanner (consultant + admin)
      - Admin (admin only)
    """
    return templates.TemplateResponse("app.html", {
        "request": request,
        "user": user
    })


@app.get("/api/states")
async def get_covered_states(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return states that have municipal sources in the database, sorted alphabetically.
    Used to populate the scanner state selector with only covered states.
    """
    from sqlalchemy import func
    rows = (
        db.query(Municipality.state, func.count(MunicipalSource.id).label("source_count"))
        .join(MunicipalSource, MunicipalSource.municipality_id == Municipality.id)
        .group_by(Municipality.state)
        .order_by(Municipality.state)
        .all()
    )
    return {"states": [{"code": row.state, "source_count": row.source_count} for row in rows]}


@app.post("/api/scans")
async def create_scan(
    config: ScanConfig,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start a new scan.

    Returns scan_id immediately and runs scan in background.
    Frontend polls GET /api/scans/{id} for progress.

    **Requires authentication.**
    """
    # Create scan record
    scan = Scan(
        user_id=user["user_id"],
        config_json=config.dict(),
        status="pending",
        progress_phase="discovery",
        progress_pct=0,
        progress_message="Initializing scan..."
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    # Start background task
    background_tasks.add_task(run_scan, scan.id, config.dict())

    return {
        "scan_id": scan.id,
        "status": "pending",
        "message": "Scan started"
    }


@app.get("/api/scans/{scan_id}")
async def get_scan(
    scan_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get scan status and progress.

    Frontend polls this endpoint every 2 seconds during scan.

    **Requires authentication.** Users can only access their own scans.
    """
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.user_id == user["user_id"]
    ).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    return {
        "id": scan.id,
        "status": scan.status,
        "progress_phase": scan.progress_phase,
        "progress_pct": scan.progress_pct,
        "progress_message": scan.progress_message,
        "stats": scan.stats_json,
        "created_at": scan.created_at.isoformat(),
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "config": scan.config_json
    }


@app.get("/api/scans/{scan_id}/leads")
async def get_leads(
    scan_id: str,
    type: Optional[str] = None,
    source: Optional[str] = None,
    sort: Optional[str] = "score",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get leads for a scan.

    Query params:
    - type: hot | warm | cold (filter by lead type)
    - source: meeting_minutes | procurement | etc (filter by source type)
    - sort: score | date | municipality (sort by field)

    **Requires authentication.** Users can only access leads from their own scans.
    """
    # Verify scan belongs to user
    scan = db.query(Scan).filter(
        Scan.id == scan_id,
        Scan.user_id == user["user_id"]
    ).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    query = db.query(Lead).filter(Lead.scan_id == scan_id)

    # Apply filters
    if type:
        query = query.filter(Lead.lead_type == type)
    if source:
        query = query.filter(Lead.source_type == source)

    # Apply sorting
    if sort == "score":
        query = query.order_by(Lead.relevance_score.desc())
    elif sort == "date":
        query = query.order_by(Lead.date.desc())
    elif sort == "municipality":
        query = query.order_by(Lead.municipality)

    leads = query.all()

    return {
        "leads": [
            {
                "id": lead.id,
                "municipality": lead.municipality,
                "state": lead.state,
                "population": lead.population,
                "title": lead.title,
                "url": lead.url,
                "date": lead.date,
                "source_type": lead.source_type,
                "relevance_score": lead.relevance_score,
                "lead_type": lead.lead_type,
                "recommended_action": lead.recommended_action,
                "signal_matches": lead.signal_matches_json,
                "notes": lead.notes
            }
            for lead in leads
        ]
    }


@app.get("/api/scans")
async def list_scans(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all past scans with summary stats.

    Enables scan history view in frontend.

    **Requires authentication.** Users only see their own scans.
    """
    scans = db.query(Scan).filter(
        Scan.user_id == user["user_id"]
    ).order_by(Scan.created_at.desc()).all()

    return {
        "scans": [
            {
                "id": scan.id,
                "created_at": scan.created_at.isoformat(),
                "status": scan.status,
                "config": scan.config_json,
                "stats": scan.stats_json
            }
            for scan in scans
        ]
    }


@app.patch("/api/leads/{lead_id}")
async def update_lead(
    lead_id: str,
    update: LeadUpdate,
    db: Session = Depends(get_db)
):
    """Update lead notes."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if update.notes is not None:
        lead.notes = update.notes
    db.commit()

    return {"success": True}


@app.get("/api/scan-preview")
async def scan_preview(
    states: List[str] = Query(default=[]),
    population_tier: str = "small",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Preview a scan config: return city counts and estimated runtime.

    Query params:
    - states: one or more state abbreviations (repeated param)
    - population_tier: micro | small | small-mid | mid-market | upper-mid | large

    Returns:
    - total_cities: total municipalities matching the filter
    - enriched_cities: verified domain + at least one source
    - unenriched_cities: everything else (will need discovery)
    - total_sources: number of known MunicipalSource records for enriched cities
    - estimated_seconds: (enriched × 3) + (unenriched × 30)
    """
    if not states:
        return {
            "total_cities": 0, "enriched_cities": 0,
            "unenriched_cities": 0, "total_sources": 0, "estimated_seconds": 0
        }

    pop_min, pop_max = get_population_range(population_tier)

    # Load matching municipalities (ids + domain_status only)
    from sqlalchemy import func
    municipalities = (
        db.query(Municipality.id, Municipality.domain_status)
        .filter(
            Municipality.state.in_(states),
            Municipality.population >= pop_min,
            Municipality.population <= pop_max,
        )
        .all()
    )

    if not municipalities:
        return {
            "total_cities": 0, "enriched_cities": 0,
            "unenriched_cities": 0, "total_sources": 0, "estimated_seconds": 0
        }

    total_cities = len(municipalities)
    all_ids = [m.id for m in municipalities]

    # Find which of those ids have at least one source (one query, no N+1)
    ids_with_sources = set(
        row[0]
        for row in db.query(MunicipalSource.municipality_id)
        .filter(MunicipalSource.municipality_id.in_(all_ids))
        .distinct()
        .all()
    )

    enriched_ids = [
        m.id for m in municipalities
        if m.domain_status == "verified" and m.id in ids_with_sources
    ]
    enriched_count = len(enriched_ids)
    unenriched_count = total_cities - enriched_count

    # Count total sources for enriched cities
    total_sources = (
        db.query(func.count(MunicipalSource.id))
        .filter(MunicipalSource.municipality_id.in_(enriched_ids))
        .scalar()
    ) if enriched_ids else 0

    estimated_seconds = enriched_count * 3 + unenriched_count * 30

    return {
        "total_cities": total_cities,
        "enriched_cities": enriched_count,
        "unenriched_cities": unenriched_count,
        "total_sources": total_sources,
        "estimated_seconds": estimated_seconds,
    }


@app.get("/api/municipalities")
async def get_municipalities(
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get municipalities for frontend selectors.

    Query params:
    - state: Filter by state abbreviation
    """
    query = db.query(Municipality)

    if state:
        query = query.filter(Municipality.state == state)

    municipalities = query.all()

    return {
        "municipalities": [
            {
                "name": m.name,
                "state": m.state,
                "population": m.population,
                "domain_status": m.domain_status
            }
            for m in municipalities
        ]
    }


@app.get("/api/export/{scan_id}")
async def export_scan(
    scan_id: str,
    format: str = "html",
    db: Session = Depends(get_db)
):
    """
    Generate and download export report.

    Formats: html | json
    """
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    leads = db.query(Lead).filter(Lead.scan_id == scan_id).all()

    if format == "json":
        # JSON export
        return {
            "scan": {
                "id": scan.id,
                "created_at": scan.created_at.isoformat(),
                "config": scan.config_json,
                "stats": scan.stats_json
            },
            "leads": [
                {
                    "municipality": lead.municipality,
                    "state": lead.state,
                    "population": lead.population,
                    "title": lead.title,
                    "url": lead.url,
                    "date": lead.date,
                    "source_type": lead.source_type,
                    "relevance_score": lead.relevance_score,
                    "lead_type": lead.lead_type,
                    "recommended_action": lead.recommended_action,
                    "notes": lead.notes
                }
                for lead in leads
            ]
        }
    else:
        # HTML export (use existing reporter.py module)
        from src.reporter import generate_html_report

        # Convert leads to format expected by reporter
        lead_data = [
            {
                "municipality": lead.municipality,
                "state": lead.state,
                "population": lead.population,
                "title": lead.title,
                "url": lead.url,
                "date": lead.date,
                "source_type": lead.source_type,
                "relevance_score": lead.relevance_score,
                "lead_type": lead.lead_type,
                "recommended_action": lead.recommended_action,
                "signal_matches": lead.signal_matches_json or {}
            }
            for lead in leads
        ]

        # Generate HTML report
        html_content = generate_html_report(lead_data, scan.stats_json or {})

        return HTMLResponse(content=html_content)


# ============================================================
# ADMIN API ENDPOINTS
# ============================================================

@app.get("/api/admin/waitlist")
async def get_waitlist(
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """List all pending waitlist entries. Admin only."""
    try:
        result = db.execute(text("""
            SELECT email, name, title, municipality, state, current_erp,
                   open_to_contact, company, interest, source, created_at
            FROM waitlist
            ORDER BY created_at DESC
        """))
        rows = result.fetchall()
        return {
            "waitlist": [
                {
                    "email": row[0],
                    "name": row[1],
                    "title": row[2],
                    "municipality": row[3],
                    "state": row[4],
                    "current_erp": row[5],
                    "open_to_contact": row[6],
                    "company": row[7],
                    "interest": row[8],
                    "source": row[9],
                    "created_at": row[10].isoformat() if row[10] else None
                }
                for row in rows
            ]
        }
    except Exception:
        return {"waitlist": []}


@app.post("/api/admin/approve")
async def approve_waitlist_user(
    request: AdminApproveRequest,
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """
    Approve a waitlist applicant and create their account.

    Creates User record, removes from waitlist, sends welcome magic link.
    Admin only.
    """
    import uuid as _uuid

    email = request.email.lower().strip()
    role = request.role

    valid_roles = ("client", "consultant", "admin")
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    # Check if user already exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    # Create user
    new_user = User(id=str(_uuid.uuid4()), email=email, role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Remove from waitlist (best-effort, no error if not found)
    try:
        db.execute(text("DELETE FROM waitlist WHERE email = :email"), {"email": email})
        db.commit()
    except Exception:
        pass

    # Send welcome magic link
    magic_link = create_magic_link(db, email)
    dev_link = None
    if magic_link:
        magic_url = f"{APP_URL}/auth/verify/{magic_link.token}"
        send_magic_link_email(email, magic_url)
        if not RESEND_API_KEY:
            dev_link = magic_url

    response = {
        "success": True,
        "user_id": new_user.id,
        "email": new_user.email,
        "role": new_user.role
    }
    if dev_link:
        response["dev_link"] = dev_link
    return response


@app.get("/api/admin/users")
async def get_all_users(
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """List all users with role and timestamps. Admin only."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None
            }
            for u in users
        ]
    }


@app.patch("/api/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    update: RoleUpdateRequest,
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Update a user's role. Admin only."""
    valid_roles = ("client", "consultant", "admin")
    if update.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = update.role
    db.commit()

    return {"success": True, "user_id": user_id, "role": update.role}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
