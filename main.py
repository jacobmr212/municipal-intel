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

from src.database import init_db, get_db, Scan, Lead, Municipality, MunicipalSource, User, Watchlist, Territory
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
from src.ai_client import analyze_coa_structure, analyze_pay_codes

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


class AssessmentCreateRequest(BaseModel):
    pass  # No body needed, just creates blank assessment


class AssessmentSectionSaveRequest(BaseModel):
    section_number: str  # "1", "3a", etc.
    answers: dict  # JSON of all answers for this section
    status: str = "in-progress"  # not-started | in-progress | completed


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


@app.get("/robots.txt", response_class=FileResponse)
async def robots():
    """Serve robots.txt for search engine crawlers."""
    return FileResponse("static/robots.txt", media_type="text/plain")


@app.get("/sitemap.xml", response_class=FileResponse)
async def sitemap():
    """Serve sitemap.xml for search engines."""
    return FileResponse("static/sitemap.xml", media_type="application/xml")


@app.get("/og-image.png", response_class=FileResponse)
async def og_image():
    """Serve Open Graph image for social media previews."""
    return FileResponse("static/og-image.png", media_type="image/png")


@app.get("/favicon.ico", response_class=FileResponse)
async def favicon():
    """Serve favicon for browser tabs."""
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@app.get("/apple-touch-icon.png", response_class=FileResponse)
async def apple_touch_icon():
    """Serve Apple touch icon for iOS devices."""
    return FileResponse("static/apple-touch-icon.png", media_type="image/png")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.1"}


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


def send_waitlist_notification(request: WaitlistRequest):
    """Send email notification to admin when someone joins the waitlist."""
    if not RESEND_API_KEY:
        print(f"[DEV MODE] Waitlist signup: {request.email} ({request.source})")
        return False

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        # Build details based on source type
        if request.source == 'municipality':
            source_label = "Municipality Official"
            details = f"""
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.name or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Title:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.title or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Municipality:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.municipality or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>State:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.state or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Current ERP:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.current_erp or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Open to Contact:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{'Yes' if request.open_to_contact else 'No' if request.open_to_contact is False else 'Not specified'}</td></tr>
            """
        elif request.source == 'consultant':
            source_label = "Consultant"
            details = f"""
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.name or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Company:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.company or 'Not provided'}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Interest:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.interest or 'Not provided'}</td></tr>
            """
        else:
            source_label = "Unknown"
            details = f"""
            <tr><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;"><strong>Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #E5E1DC;">{request.name or 'Not provided'}</td></tr>
            """

        admin_email = os.getenv("ADMIN_EMAIL", "jacob@govtechdiagnostic.com")

        params = {
            "from": "GovTech Diagnostic <noreply@govtechdiagnostic.com>",
            "to": [admin_email],
            "subject": f"New Waitlist Signup: {source_label}",
            "html": f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #1A1816; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
                    .header {{ font-size: 24px; font-weight: 600; margin-bottom: 24px; color: #2B4AE0; }}
                    .badge {{ display: inline-block; background: #4ADE80; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-bottom: 16px; }}
                    .badge.consultant {{ background: #FBBF24; color: #000; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 24px 0; background: #F9F8F6; border-radius: 8px; overflow: hidden; }}
                    .footer {{ margin-top: 40px; padding-top: 24px; border-top: 1px solid #E5E1DC; font-size: 14px; color: #5C574F; }}
                    .cta {{ display: inline-block; background: #2B4AE0; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; margin-top: 16px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">New Waitlist Signup</div>
                    <div class="badge {'consultant' if request.source == 'consultant' else ''}">{source_label}</div>
                    <p><strong>Email:</strong> {request.email}</p>
                    <table>
                        {details}
                    </table>
                    <a href="{APP_URL}/admin" class="cta">View in Admin Dashboard</a>
                    <div class="footer">
                        GovTech Diagnostic<br>
                        Automated Waitlist Notification
                    </div>
                </div>
            </body>
            </html>
            """
        }

        resend.Emails.send(params)
        return True

    except Exception as e:
        print(f"Error sending waitlist notification: {e}")
        return False


@app.post("/api/waitlist")
async def join_waitlist(request: WaitlistRequest, db: Session = Depends(get_db)):
    """Add email to waitlist. Returns 200 even on duplicate to avoid leaking whether an email exists."""
    is_new_signup = False
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

        # Check if this is a new signup (not a duplicate)
        existing = db.execute(
            text("SELECT email FROM waitlist WHERE email = :email"),
            {"email": request.email.lower().strip()}
        ).fetchone()

        if not existing:
            is_new_signup = True

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

        # Send notification email only for new signups
        if is_new_signup:
            send_waitlist_notification(request)

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


@app.get("/scanner", response_class=HTMLResponse)
async def scanner(request: Request, user: dict = Depends(require_role(["consultant", "admin"]))):
    """
    Dedicated scanner page for consultants and admins.
    Full-width interface for configuring and running scans across municipal sources.

    Features:
      - Dynamic state selector (all 49 covered states)
      - Population tier filter
      - Source type selection
      - Real-time scan progress
      - Live results table
    """
    return templates.TemplateResponse("scanner.html", {
        "request": request,
        "user": user
    })


@app.get("/test-assessment")
async def test_assessment(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quick test route to create assessment and redirect - bypasses JavaScript."""
    import uuid as _uuid
    from datetime import datetime

    assessment_id = str(_uuid.uuid4())

    # Get user_id safely
    user_id = user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=500, detail=f"No user ID in user dict. Keys: {list(user.keys())}")

    db.execute(text("""
        INSERT INTO "Assessment" (id, "userId", status, "createdAt", "updatedAt")
        VALUES (:id, :user_id, 'draft', :now, :now)
    """), {
        "id": assessment_id,
        "user_id": user_id,
        "now": datetime.utcnow()
    })
    db.commit()

    return RedirectResponse(url=f"/assessment/{assessment_id}", status_code=303)


@app.get("/admin/v2", response_class=HTMLResponse)
async def admin_v2(request: Request, user: dict = Depends(require_role("admin"))):
    """
    New admin interface (v2) with enhanced features:
      - 5 tabs: Overview, Waitlist, Users, Scans, Analytics
      - Search and filter functionality
      - Bulk actions
      - Better data visualization
    """
    return templates.TemplateResponse("admin_v2.html", {
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


@app.get("/api/feed")
async def get_feed(
    limit: int = 50,
    offset: int = 0,
    state: Optional[str] = None,
    lead_type: Optional[str] = None,
    customer_status: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Feed API endpoint - returns recent leads from all scans.

    Filters by user's territories if any exist.
    Supports pagination and filtering.

    Query parameters:
    - limit: Number of results to return (default 50, max 200)
    - offset: Pagination offset (default 0)
    - state: Filter by state code (optional)
    - lead_type: Filter by lead_type: hot | warm | cold (optional)
    - customer_status: Filter by customer_status: existing_customer | new_opportunity (optional)

    **Requires authentication.**
    """
    # Enforce max limit
    limit = min(limit, 200)

    # Start with base query joining leads with scans
    query = (
        db.query(Lead)
        .join(Scan, Lead.scan_id == Scan.id)
        .filter(Scan.status == "completed")
    )

    # Filter by user's territories if any exist
    territories = db.query(Territory).filter(Territory.user_id == user["user_id"]).all()
    if territories:
        territory_states = [t.state for t in territories]
        query = query.filter(Lead.state.in_(territory_states))

    # Apply optional filters
    if state:
        query = query.filter(Lead.state == state.upper())
    if lead_type:
        query = query.filter(Lead.lead_type == lead_type.lower())
    if customer_status:
        query = query.filter(Lead.customer_status == customer_status.lower())

    # Get total count for pagination metadata
    total_count = query.count()

    # Order by relevance score descending and apply pagination
    leads = (
        query
        .order_by(Lead.relevance_score.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Format response
    results = []
    for lead in leads:
        results.append({
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
            "customer_status": lead.customer_status,
            "recommended_action": lead.recommended_action,
            "signal_matches": lead.signal_matches_json,
            "notes": lead.notes,
            "scan_id": lead.scan_id
        })

    return {
        "leads": results,
        "pagination": {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        },
        "filters": {
            "state": state,
            "lead_type": lead_type,
            "customer_status": customer_status,
            "territories": [t.state for t in territories] if territories else None
        }
    }


# =============================================================================
# WATCHLIST ENDPOINTS
# =============================================================================

@app.get("/api/watchlist")
async def get_watchlist(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's watchlist with full municipality details.

    Returns list of watchlist items with municipality data.
    """
    watchlist_items = (
        db.query(Watchlist)
        .filter(Watchlist.user_id == user["user_id"])
        .order_by(Watchlist.created_at.desc())
        .all()
    )

    results = []
    for item in watchlist_items:
        muni = item.municipality
        results.append({
            "id": item.id,
            "municipality_id": item.municipality_id,
            "municipality": muni.name if muni else "Unknown",
            "state": muni.state if muni else "??",
            "population": muni.population if muni else 0,
            "notes": item.notes,
            "created_at": item.created_at.isoformat()
        })

    return {"watchlist": results}


@app.post("/api/watchlist")
async def add_to_watchlist(
    municipality_id: int,
    notes: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a municipality to user's watchlist.

    Request body: {"municipality_id": 123, "notes": "optional"}
    """
    # Check if municipality exists
    muni = db.query(Municipality).filter(Municipality.id == municipality_id).first()
    if not muni:
        raise HTTPException(status_code=404, detail="Municipality not found")

    # Check if already on watchlist
    existing = (
        db.query(Watchlist)
        .filter(
            Watchlist.user_id == user["user_id"],
            Watchlist.municipality_id == municipality_id
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Municipality already on watchlist")

    # Add to watchlist
    watchlist_item = Watchlist(
        user_id=user["user_id"],
        municipality_id=municipality_id,
        notes=notes
    )
    db.add(watchlist_item)
    db.commit()
    db.refresh(watchlist_item)

    return {
        "id": watchlist_item.id,
        "municipality": muni.name,
        "state": muni.state,
        "message": "Added to watchlist"
    }


@app.delete("/api/watchlist/{watchlist_id}")
async def remove_from_watchlist(
    watchlist_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a municipality from user's watchlist.
    """
    watchlist_item = (
        db.query(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == user["user_id"]
        )
        .first()
    )

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    db.delete(watchlist_item)
    db.commit()

    return {"message": "Removed from watchlist"}


# =============================================================================
# TERRITORY ENDPOINTS
# =============================================================================

@app.get("/api/territory")
async def get_territories(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's territory assignments.

    Returns list of states assigned to the user.
    """
    territories = (
        db.query(Territory)
        .filter(Territory.user_id == user["user_id"])
        .order_by(Territory.state.asc())
        .all()
    )

    results = []
    for territory in territories:
        results.append({
            "id": territory.id,
            "state": territory.state,
            "created_at": territory.created_at.isoformat()
        })

    return {"territories": results}


@app.post("/api/territory")
async def add_territory(
    state: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a state to user's territory.

    Request body: {"state": "CA"}
    """
    # Validate state code
    state = state.upper().strip()
    if len(state) != 2:
        raise HTTPException(status_code=400, detail="Invalid state code (must be 2 letters)")

    # Check if already assigned
    existing = (
        db.query(Territory)
        .filter(
            Territory.user_id == user["user_id"],
            Territory.state == state
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="State already in territory")

    # Add territory
    territory = Territory(
        user_id=user["user_id"],
        state=state
    )
    db.add(territory)
    db.commit()
    db.refresh(territory)

    return {
        "id": territory.id,
        "state": territory.state,
        "message": "State added to territory"
    }


@app.delete("/api/territory/{territory_id}")
async def remove_territory(
    territory_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a state from user's territory.
    """
    territory = (
        db.query(Territory)
        .filter(
            Territory.id == territory_id,
            Territory.user_id == user["user_id"]
        )
        .first()
    )

    if not territory:
        raise HTTPException(status_code=404, detail="Territory not found")

    db.delete(territory)
    db.commit()

    return {"message": "State removed from territory"}


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
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update lead notes. Requires authentication and scan ownership."""
    # Get lead and verify it exists
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Verify lead belongs to user's scan
    scan = db.query(Scan).filter(
        Scan.id == lead.scan_id,
        Scan.user_id == user["user_id"]
    ).first()

    if not scan:
        raise HTTPException(status_code=403, detail="Access denied")

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
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get municipalities for frontend selectors.
    Requires authentication.

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
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate and download export report.
    Requires authentication and scan ownership.

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


@app.get("/api/admin/analytics")
async def get_admin_analytics(
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive admin analytics for Assessment platform.

    Returns:
    - Overview statistics (total assessments, completed, in-progress, draft)
    - Section interest tracking (which locked sections users want most)
    - Section completion rates
    - User demographics
    - Recent activity
    - User growth trends
    """
    try:
        # Overview statistics
        overview_result = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'in-progress' THEN 1 END) as in_progress,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as draft
            FROM "Assessment"
        """))
        overview_row = overview_result.fetchone()

        total_users_result = db.execute(text('SELECT COUNT(*) FROM users'))
        total_users = total_users_result.fetchone()[0]

        anonymous_count_result = db.execute(text('SELECT COUNT(DISTINCT "sessionId") FROM "AnonymousAssessment"'))
        anonymous_count = anonymous_count_result.fetchone()[0]

        # Section interest tracking - NEW FEATURE
        # Tracks which locked sections (4-8) users are most interested in
        section_interest_result = db.execute(text("""
            SELECT
                a.id as assessment_id,
                a."userId",
                a."interestedSections",
                u.email,
                a."organizationProfile"
            FROM "Assessment" a
            JOIN users u ON a."userId" = u.id
            WHERE a."interestedSections" IS NOT NULL
            AND jsonb_array_length(a."interestedSections") > 0
        """))

        # Process section interest data
        section_interest_counts = {}
        section_interest_details = {}

        for row in section_interest_result:
            interested_sections = row[2] if row[2] else []
            user_email = row[3]
            org_profile = row[4] if row[4] else {}

            for section_num in interested_sections:
                # Count
                if section_num not in section_interest_counts:
                    section_interest_counts[section_num] = 0
                section_interest_counts[section_num] += 1

                # Details
                if section_num not in section_interest_details:
                    section_interest_details[section_num] = []

                section_interest_details[section_num].append({
                    "userEmail": user_email,
                    "organization": org_profile.get('organization') if isinstance(org_profile, dict) else None,
                    "state": org_profile.get('state') if isinstance(org_profile, dict) else None,
                })

        # Section completion rates
        section_completion_result = db.execute(text("""
            SELECT
                "sectionNumber",
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed
            FROM "AssessmentSection"
            GROUP BY "sectionNumber"
            ORDER BY "sectionNumber"
        """))

        section_completion = {}
        for row in section_completion_result:
            section_num = row[0]
            total = row[1]
            completed = row[2]
            section_completion[section_num] = {
                "total": total,
                "completed": completed,
                "completion_rate": round((completed / total * 100) if total > 0 else 0, 1)
            }

        # Demographics (state distribution)
        demographics_result = db.execute(text("""
            SELECT
                a."organizationProfile"->>'state' as state,
                COUNT(*) as count
            FROM "Assessment" a
            WHERE a."organizationProfile"->>'state' IS NOT NULL
            GROUP BY a."organizationProfile"->>'state'
            ORDER BY count DESC
            LIMIT 10
        """))

        state_distribution = {}
        for row in demographics_result:
            state = row[0]
            count = row[1]
            if state:
                state_distribution[state] = count

        # Recent activity (last 10 assessments)
        recent_activity_result = db.execute(text("""
            SELECT
                a.id,
                a.status,
                a."createdAt",
                u.email,
                a."organizationProfile"->>'organization' as organization,
                a."organizationProfile"->>'state' as state
            FROM "Assessment" a
            JOIN users u ON a."userId" = u.id
            ORDER BY a."createdAt" DESC
            LIMIT 10
        """))

        recent_activity = []
        for row in recent_activity_result:
            recent_activity.append({
                "assessmentId": row[0],
                "status": row[1],
                "createdAt": row[2].isoformat() if row[2] else None,
                "userEmail": row[3],
                "organization": row[4],
                "state": row[5]
            })

        # User growth (assessments created per week, last 12 weeks)
        user_growth_result = db.execute(text("""
            SELECT
                DATE_TRUNC('week', "createdAt") as week,
                COUNT(*) as count
            FROM "Assessment"
            WHERE "createdAt" >= NOW() - INTERVAL '12 weeks'
            GROUP BY week
            ORDER BY week
        """))

        user_growth = []
        for row in user_growth_result:
            user_growth.append({
                "week": row[0].isoformat() if row[0] else None,
                "count": row[1]
            })

        return {
            "overview": {
                "totalAssessments": overview_row[0],
                "completed": overview_row[1],
                "inProgress": overview_row[2],
                "draft": overview_row[3],
                "totalUsers": total_users,
                "anonymousCount": anonymous_count
            },
            "sectionInterest": {
                "counts": section_interest_counts,
                "details": section_interest_details
            },
            "sectionCompletion": section_completion,
            "demographics": {
                "stateDistribution": state_distribution
            },
            "recentActivity": recent_activity,
            "userGrowth": user_growth
        }

    except Exception as e:
        # Return empty data structure if Assessment tables don't exist yet
        # This allows the endpoint to work even before first assessment is created
        return {
            "overview": {
                "totalAssessments": 0,
                "completed": 0,
                "inProgress": 0,
                "draft": 0,
                "totalUsers": total_users if 'total_users' in locals() else 0,
                "anonymousCount": 0
            },
            "sectionInterest": {
                "counts": {},
                "details": {}
            },
            "sectionCompletion": {},
            "demographics": {
                "stateDistribution": {}
            },
            "recentActivity": [],
            "userGrowth": [],
            "error": str(e)
        }


# ============================================================
# ASSESSMENT PAGES
# ============================================================

@app.get("/assessment/{assessment_id}", response_class=HTMLResponse)
async def assessment_dashboard(
    assessment_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assessment dashboard showing all sections."""
    # Verify assessment belongs to user
    result = db.execute(text("""
        SELECT id, status FROM "Assessment"
        WHERE id = :id AND "userId" = :user_id
    """), {"id": assessment_id, "user_id": user["user_id"]})

    assessment_row = result.fetchone()
    if not assessment_row:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Query section statuses
    sections_result = db.execute(text("""
        SELECT "sectionNumber", status
        FROM "AssessmentSection"
        WHERE "assessmentId" = :assessment_id
        ORDER BY "sectionNumber"
    """), {"assessment_id": assessment_id})

    section_statuses = {row[0]: row[1] for row in sections_result.fetchall()}

    # Build sections list with metadata
    sections = [
        {
            "number": "1",
            "title": "Organization Profile",
            "description": "Tell us about your municipality and current systems",
            "status": section_statuses.get("1", "not-started"),
            "locked": False,
            "estimated_minutes": 10
        },
        {
            "number": "2",
            "title": "General Ledger & Chart of Accounts",
            "description": "Assess your GL structure and identify optimization opportunities",
            "status": section_statuses.get("2", "not-started"),
            "locked": section_statuses.get("1") != "completed",
            "requires": "1",
            "estimated_minutes": 7
        },
        {
            "number": "3a",
            "title": "Pay Code Inventory",
            "description": "Document your current pay codes and structure",
            "status": section_statuses.get("3a", "not-started"),
            "locked": section_statuses.get("1") != "completed",
            "requires": "1",
            "estimated_minutes": 15
        }
    ]

    # Calculate progress
    completed_count = sum(1 for s in sections if s["status"] == "completed")
    total_sections = len(sections)
    overall_progress = int((completed_count / total_sections) * 100) if total_sections > 0 else 0

    # Calculate estimated time remaining
    estimated_time = sum(
        s["estimated_minutes"]
        for s in sections
        if s["status"] != "completed" and not s["locked"]
    )

    return templates.TemplateResponse("assessment_dashboard.html", {
        "request": request,
        "user": user,
        "assessment_id": assessment_id,
        "sections": sections,
        "overall_progress": overall_progress,
        "completed_count": completed_count,
        "total_sections": total_sections,
        "estimated_time": estimated_time
    })


@app.get("/assessment/{assessment_id}/section/{section_number}", response_class=HTMLResponse)
async def assessment_section(
    assessment_id: str,
    section_number: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Render a specific assessment section."""
    # Verify assessment belongs to user
    result = db.execute(text("""
        SELECT id FROM "Assessment"
        WHERE id = :id AND "userId" = :user_id
    """), {"id": assessment_id, "user_id": user["user_id"]})

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Section metadata
    sections_meta = {
        "1": {
            "title": "Organization Profile",
            "description": "Tell us about your municipality and current systems",
            "script": "section1_script.js"
        },
        "2": {
            "title": "General Ledger & Chart of Accounts",
            "description": "Assess your GL structure and identify optimization opportunities",
            "script": "section2_script.js"
        },
        "3a": {
            "title": "Pay Code Inventory",
            "description": "Document your current pay codes and structure",
            "script": "section3a_script.js"
        }
    }

    meta = sections_meta.get(section_number, {
        "title": f"Section {section_number}",
        "description": "Coming soon",
        "script": ""
    })

    # Generate section-specific script inline
    section_script = ""
    if section_number == "1":
        section_script = generate_section1_script()
    elif section_number == "2":
        section_script = generate_section2_script()
    elif section_number == "3a":
        section_script = generate_section3a_script()

    return templates.TemplateResponse("assessment.html", {
        "request": request,
        "user": user,
        "assessment_id": assessment_id,
        "section_number": section_number,
        "section_title": meta["title"],
        "section_description": meta["description"],
        "section_script": section_script
    })


def generate_section1_script():
    """Generate Section 1 conversational script with all 13 questions."""
    # Load retirement systems data
    import json
    with open('data/retirement_systems.json', 'r') as f:
        retirement_systems = json.load(f)

    retirement_systems_json = json.dumps(retirement_systems)

    return f"""
// Section 1: Organization Profile
// Full version with 13 questions

const STATES = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
  "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
  "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
  "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
  "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
];

const RETIREMENT_SYSTEMS = {retirement_systems_json};

const MONTHS = [
  {{ value: '01', label: 'January' }},
  {{ value: '02', label: 'February' }},
  {{ value: '03', label: 'March' }},
  {{ value: '04', label: 'April' }},
  {{ value: '05', label: 'May' }},
  {{ value: '06', label: 'June' }},
  {{ value: '07', label: 'July' }},
  {{ value: '08', label: 'August' }},
  {{ value: '09', label: 'September' }},
  {{ value: '10', label: 'October' }},
  {{ value: '11', label: 'November' }},
  {{ value: '12', label: 'December' }}
];

// Track union groups for chip builder
let unionGroups = [];

// Start the conversation
setTimeout(() => {{
  addMessage('assistant', 'Welcome! Let\\'s start by learning about your organization.');
  setTimeout(() => {{
    currentStep = 'state';
    addMessage('assistant', 'Which state are you in?', 'select', {{
      options: STATES.map(s => ({{ value: s, label: s }}))
    }});
  }}, 800);
}}, 500);

// Handle user input
window.handleUserInput = function(step, value) {{
  if (step === 'state') {{
    setTimeout(() => {{
      addMessage('assistant', `Great! You're in ${{value}}.`);
      setTimeout(() => {{
        currentStep = 'entity_type';
        addMessage('assistant', 'What type of government entity are you?', 'choice-buttons', {{
          options: [
            {{ value: 'city', label: 'City' }},
            {{ value: 'county', label: 'County' }},
            {{ value: 'town', label: 'Town' }},
            {{ value: 'village', label: 'Village' }}
          ]
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'entity_type') {{
    setTimeout(() => {{
      addMessage('assistant', `Got it, you're a ${{value}}.`);
      setTimeout(() => {{
        currentStep = 'population';
        addMessage('assistant', 'What is your population?', 'text-input', {{
          inputType: 'number',
          placeholder: 'e.g., 15000'
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'population') {{
    setTimeout(() => {{
      addMessage('assistant', `Population: ${{parseInt(value).toLocaleString()}}`);
      setTimeout(() => {{
        currentStep = 'organization';
        addMessage('assistant', 'What is the name of your organization?', 'text-input', {{
          inputType: 'text',
          placeholder: 'e.g., City of Springfield'
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'organization') {{
    setTimeout(() => {{
      addMessage('assistant', `Perfect! Nice to meet you, ${{value}}.`);
      setTimeout(() => {{
        currentStep = 'retirement_system';
        const selectedState = answers['state'];
        const retirementOptions = RETIREMENT_SYSTEMS[selectedState] || [];
        addMessage('assistant', 'Which retirement system do your employees participate in?', 'select', {{
          options: retirementOptions
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'retirement_system') {{
    setTimeout(() => {{
      const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
      addMessage('assistant', `Got it, you use ${{label}}.`);
      setTimeout(() => {{
        currentStep = 'fiscal_year_month';
        addMessage('assistant', 'When does your fiscal year start? First, select the month:', 'select', {{
          options: MONTHS
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'fiscal_year_month') {{
    setTimeout(() => {{
      const monthLabel = MONTHS.find(m => m.value === value)?.label || value;
      addMessage('assistant', `${{monthLabel}} — got it.`);
      setTimeout(() => {{
        currentStep = 'fiscal_year_day';
        const days = Array.from({{ length: 31 }}, (_, i) => ({{ value: String(i + 1), label: String(i + 1) }}));
        addMessage('assistant', 'And which day of the month?', 'select', {{
          options: days
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'fiscal_year_day') {{
    setTimeout(() => {{
      const month = answers['fiscal_year_month'];
      const monthLabel = MONTHS.find(m => m.value === month)?.label || month;
      addMessage('assistant', `Fiscal year starts: ${{monthLabel}} ${{value}}`);
      setTimeout(() => {{
        currentStep = 'department_count';
        addMessage('assistant', 'How many departments does your organization have?', 'text-input', {{
          inputType: 'number',
          placeholder: 'e.g., 12'
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'department_count') {{
    setTimeout(() => {{
      addMessage('assistant', `${{value}} departments — noted.`);
      setTimeout(() => {{
        currentStep = 'has_unions';
        addMessage('assistant', 'Does your organization have unionized employees?', 'choice-buttons', {{
          options: [
            {{ value: 'yes', label: 'Yes' }},
            {{ value: 'no', label: 'No' }}
          ]
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'has_unions') {{
    if (value === 'yes') {{
      setTimeout(() => {{
        addMessage('assistant', 'Understood. We\\'ll need to track union groups.');
        setTimeout(() => {{
          currentStep = 'union_groups';
          addMessage('assistant', 'Please list your union groups (e.g., "Police Union", "Firefighters Local 123"). Type one and press Enter, then add more. Type "done" when finished.', 'text-input', {{
            inputType: 'text',
            placeholder: 'e.g., Police Union'
          }});
        }}, 800);
      }}, 600);
    }} else {{
      // Skip union groups
      answers['union_groups'] = [];
      setTimeout(() => {{
        addMessage('assistant', 'No unions — got it.');
        setTimeout(() => {{
          currentStep = 'tax_jurisdictions';
          addMessage('assistant', 'How many tax jurisdictions do you operate in?', 'text-input', {{
            inputType: 'number',
            placeholder: 'e.g., 3'
          }});
        }}, 800);
      }}, 600);
    }}
  }}
  else if (step === 'union_groups') {{
    if (value.toLowerCase() === 'done') {{
      answers['union_groups'] = unionGroups;
      setTimeout(() => {{
        if (unionGroups.length === 0) {{
          addMessage('assistant', 'No union groups added.');
        }} else {{
          addMessage('assistant', `Union groups: ${{unionGroups.join(', ')}}`);
        }}
        setTimeout(() => {{
          currentStep = 'tax_jurisdictions';
          addMessage('assistant', 'How many tax jurisdictions do you operate in?', 'text-input', {{
            inputType: 'number',
            placeholder: 'e.g., 3'
          }});
        }}, 800);
      }}, 600);
    }} else {{
      // Add to union groups
      unionGroups.push(value);
      setTimeout(() => {{
        addMessage('assistant', `Added "${{value}}". Add another or type "done".`);
        setTimeout(() => {{
          addMessage('assistant', '', 'text-input', {{
            inputType: 'text',
            placeholder: 'e.g., Firefighters Local 123 or "done"'
          }});
        }}, 500);
      }}, 400);
    }}
  }}
  else if (step === 'tax_jurisdictions') {{
    setTimeout(() => {{
      addMessage('assistant', `${{value}} tax jurisdictions — noted.`);
      setTimeout(() => {{
        currentStep = 'current_erp';
        addMessage('assistant', 'What ERP system are you currently using?', 'text-input', {{
          inputType: 'text',
          placeholder: 'e.g., Tyler Munis, SAP, Excel'
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'current_erp') {{
    setTimeout(() => {{
      addMessage('assistant', `Current system: ${{value}}`);
      setTimeout(() => {{
        currentStep = 'employee_count';
        addMessage('assistant', 'How many employees does your organization have?', 'text-input', {{
          inputType: 'number',
          placeholder: 'e.g., 250'
        }});
      }}, 800);
    }}, 600);
  }}
  else if (step === 'employee_count') {{
    setTimeout(() => {{
      addMessage('assistant', `${{parseInt(value).toLocaleString()}} employees — perfect.`);
      setTimeout(() => {{
        addMessage('assistant', 'That\\'s all the questions for Section 1! Let me save your responses...');
        setTimeout(() => {{
          // Save progress
          saveProgress('completed');
          updateProgress(100);
          setTimeout(() => {{
            addMessage('assistant', 'Section 1 complete! Returning to dashboard...');
            setTimeout(() => {{
              window.location.href = '/app';
            }}, 2000);
          }}, 800);
        }}, 1000);
      }}, 800);
    }}, 600);
  }}

  // Update progress
  const allSteps = [
    'state', 'entity_type', 'population', 'organization', 'retirement_system',
    'fiscal_year_month', 'fiscal_year_day', 'department_count', 'has_unions',
    'union_groups', 'tax_jurisdictions', 'current_erp', 'employee_count'
  ];

  // Calculate progress (skip union_groups if no unions)
  let relevantSteps = allSteps;
  if (answers['has_unions'] === 'no') {{
    relevantSteps = allSteps.filter(s => s !== 'union_groups');
  }}

  const currentIndex = relevantSteps.indexOf(currentStep);
  const progress = currentIndex >= 0 ? ((currentIndex + 1) / relevantSteps.length) * 100 : 0;
  updateProgress(progress);

  // Auto-save
  saveProgress();
}};
"""


def generate_section2_script():
    """Generate Section 2 conversational script for GL & COA assessment."""
    return """
// Section 2: General Ledger & Chart of Accounts
// Conversational flow to assess COA structure and identify optimization opportunities

// Start the conversation
setTimeout(() => {
  addMessage('assistant', 'Welcome to Section 2: General Ledger & Chart of Accounts!');
  setTimeout(() => {
    addMessage('assistant', 'This section helps identify bloat, inefficiencies, and optimization opportunities in your COA structure. It takes about 5-7 minutes.');
    setTimeout(() => {
      currentStep = 'account_count';
      addMessage('assistant', 'Let\\'s start. Approximately how many GL accounts do you have in total?', 'select', {
        options: [
          { value: 'under-500', label: 'Under 500' },
          { value: '500-1000', label: '500-1,000' },
          { value: '1000-2000', label: '1,000-2,000' },
          { value: '2000-5000', label: '2,000-5,000' },
          { value: 'over-5000', label: 'Over 5,000' },
          { value: 'not-sure', label: 'Not sure' }
        ]
      });
    }, 800);
  }, 800);
}, 500);

// Handle user input
window.handleUserInput = function(step, value) {
  if (step === 'account_count') {
    answers['account_count'] = value;
    const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
    addMessage('user', label);

    setTimeout(() => {
      if (value === '2000-5000' || value === 'over-5000') {
        addMessage('assistant', 'That\\'s quite a few accounts. This could indicate COA bloat, which we\\'ll explore more.');
      } else if (value === 'under-500') {
        addMessage('assistant', 'That\\'s a lean structure. For small municipalities, this is typically ideal.');
      } else {
        addMessage('assistant', 'That\\'s in the normal range for most municipalities.');
      }

      setTimeout(() => {
        currentStep = 'last_review';
        addMessage('assistant', 'When was your Chart of Accounts last comprehensively reviewed?', 'select', {
          options: [
            { value: 'within-1-year', label: 'Within the last year' },
            { value: '1-2-years', label: '1-2 years ago' },
            { value: '2-5-years', label: '2-5 years ago' },
            { value: '5-10-years', label: '5-10 years ago' },
            { value: 'over-10-years', label: 'Over 10 years ago' },
            { value: 'never', label: 'Never / Not sure' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'last_review') {
    answers['last_review'] = value;
    const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
    addMessage('user', label);

    setTimeout(() => {
      if (value === '5-10-years' || value === 'over-10-years' || value === 'never') {
        addMessage('assistant', '⚠️ COAs that haven\\'t been reviewed in 5+ years almost always have significant bloat and structural issues.');
      } else if (value === 'within-1-year' || value === '1-2-years') {
        addMessage('assistant', 'Great! Regular reviews keep your COA clean and efficient.');
      }

      setTimeout(() => {
        currentStep = 'inactive_percentage';
        addMessage('assistant', 'Approximately what percentage of your GL accounts had NO transaction activity last fiscal year?', 'select', {
          options: [
            { value: 'under-5', label: 'Under 5%' },
            { value: '5-15', label: '5-15%' },
            { value: '15-30', label: '15-30%' },
            { value: '30-50', label: '30-50%' },
            { value: 'over-50', label: 'Over 50%' },
            { value: 'not-sure', label: 'Not sure' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'inactive_percentage') {
    answers['inactive_percentage'] = value;
    const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
    addMessage('user', label);

    setTimeout(() => {
      if (value === '15-30' || value === '30-50' || value === 'over-50') {
        addMessage('assistant', '⚠️ High percentages of inactive accounts signal COA bloat. Well-maintained municipal COAs typically have fewer than 10% inactive accounts.');
      } else if (value === 'under-5') {
        addMessage('assistant', 'Excellent! A low percentage of inactive accounts indicates a well-maintained COA.');
      }

      setTimeout(() => {
        currentStep = 'fund_count';
        addMessage('assistant', 'How many funds does your municipality operate?', 'select', {
          options: [
            { value: '1-3', label: '1-3 funds' },
            { value: '4-7', label: '4-7 funds' },
            { value: '8-15', label: '8-15 funds' },
            { value: 'over-15', label: 'Over 15 funds' },
            { value: 'not-sure', label: 'Not sure' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'fund_count') {
    answers['fund_count'] = value;
    const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
    addMessage('user', label);

    setTimeout(() => {
      if (value === 'over-15') {
        addMessage('assistant', 'A large number of funds can complicate reporting. We\\'ll note this for our analysis.');
      }

      setTimeout(() => {
        currentStep = 'month_close';
        addMessage('assistant', 'How long does your typical month-end close process take?', 'select', {
          options: [
            { value: 'under-5-days', label: 'Under 5 business days' },
            { value: '5-8-days', label: '5-8 business days' },
            { value: '8-15-days', label: '8-15 business days' },
            { value: 'over-15-days', label: 'Over 15 business days' },
            { value: 'not-sure', label: 'Not sure' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'month_close') {
    answers['month_close'] = value;
    const label = document.getElementById('selectInput')?.options[document.getElementById('selectInput')?.selectedIndex]?.text || value;
    addMessage('user', label);

    setTimeout(() => {
      if (value === '8-15-days' || value === 'over-15-days') {
        addMessage('assistant', '⚠️ Extended close cycles often stem from COA complexity, reconciliation difficulties, or manual processes.');
      } else if (value === 'under-5-days') {
        addMessage('assistant', 'Excellent! A quick close indicates efficient processes.');
      }

      setTimeout(() => {
        currentStep = 'known_issues';
        addMessage('assistant', 'Finally, are you aware of any specific issues with your current Chart of Accounts? (You can select "No known issues" if not)', 'multi-select-start', {
          categories: [
            { value: 'duplicate-accounts', label: 'Duplicate or similar accounts' },
            { value: 'confusing-names', label: 'Confusing account names' },
            { value: 'high-inactive', label: 'Too many inactive accounts' },
            { value: 'mispostings', label: 'Frequent mispostings' },
            { value: 'reporting-difficulty', label: 'Difficult to generate reports' },
            { value: 'none', label: 'No known issues' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'known_issues_confirmed') {
    // Multi-select completed via handleCategoryConfirm
    setTimeout(() => {
      addMessage('assistant', 'Great! I have all the information I need.');
      setTimeout(() => {
        addMessage('assistant', 'Let me analyze your COA structure using AI...');
        currentStep = 'analyzing';

        // Call AI analysis API
        fetch(`/api/assessments/${ASSESSMENT_ID}/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            section_number: '2',
            data: {
              account_count: answers['account_count'],
              last_review: answers['last_review'],
              inactive_percentage: answers['inactive_percentage'],
              fund_count: answers['fund_count'],
              month_close: answers['month_close'],
              known_issues: answers['known_issues'] || []
            }
          })
        })
        .then(r => r.json())
        .then(result => {
          if (result.analysis && result.analysis.summary) {
            setTimeout(() => {
              addMessage('assistant', '✨ **Analysis Complete**');
              setTimeout(() => {
                addMessage('assistant', result.analysis.summary);
                setTimeout(() => {
                  if (result.analysis.findings && result.analysis.findings.length > 0) {
                    addMessage('assistant', `I've identified ${result.analysis.findings.length} finding${result.analysis.findings.length > 1 ? 's' : ''} that you should be aware of:`);
                    result.analysis.findings.forEach((finding, idx) => {
                      setTimeout(() => {
                        const severityEmoji = {
                          'critical': '🚨',
                          'high': '⚠️',
                          'medium': '⚡',
                          'low': 'ℹ️'
                        }[finding.severity] || '•';
                        addMessage('assistant', `${severityEmoji} **${finding.title}**\\n\\n${finding.description}\\n\\n**Impact:** ${finding.impact}\\n\\n**Recommendation:** ${finding.recommendation}`);
                      }, idx * 1000);
                    });
                  }
                  setTimeout(() => {
                    finishSection();
                  }, (result.analysis.findings?.length || 0) * 1000 + 1500);
                }, 800);
              }, 600);
            }, 1000);
          } else {
            addMessage('assistant', 'AI analysis is currently unavailable, but your responses have been saved.');
            setTimeout(() => {
              finishSection();
            }, 1500);
          }
        })
        .catch(err => {
          console.error('AI analysis error:', err);
          addMessage('assistant', 'Unable to complete AI analysis, but your responses have been saved.');
          setTimeout(() => {
            finishSection();
          }, 1500);
        });
      }, 800);
    }, 600);
  }

  // Auto-save
  saveProgress();
};

// Override handleCategoryConfirm for known issues
window.handleCategoryConfirm = function() {
  answers['known_issues'] = selectedCategories;

  const categoryLabels = selectedCategories.map(c =>
    document.querySelectorAll('.category-btn[data-category="' + c + '"]')[0]?.textContent || c
  ).join(', ');

  if (selectedCategories.length === 0 || (selectedCategories.length === 1 && selectedCategories[0] === 'none')) {
    addMessage('user', 'No known issues');
  } else {
    addMessage('user', `Selected: ${categoryLabels}`);
  }

  currentStep = 'known_issues_confirmed';
  window.handleUserInput('known_issues_confirmed', selectedCategories);
};

function finishSection() {
  addMessage('assistant', 'Section 2 complete! Returning to dashboard...');
  saveProgress('completed');
  updateProgress(100);
  setTimeout(() => {
    window.location.href = '/app';
  }, 2000);
}
"""


def generate_section3a_script():
    """Generate Section 3A conversational script for pay code inventory."""
    return """
// Section 3A: Pay Code Inventory
// Conversational flow for collecting pay code details

const PAY_CODE_CATEGORIES = [
  { value: 'regular-pay', label: 'Regular Pay' },
  { value: 'overtime', label: 'Overtime' },
  { value: 'vacation', label: 'Vacation' },
  { value: 'sick-leave', label: 'Sick Leave' },
  { value: 'comp-time', label: 'Comp Time' },
  { value: 'holiday', label: 'Holiday Pay' },
  { value: 'longevity', label: 'Longevity Pay' },
  { value: 'shift-differential', label: 'Shift Differential' },
  { value: 'standby-oncall', label: 'Standby/On-Call' },
  { value: 'bilingual-pay', label: 'Bilingual Pay' },
  { value: 'certification-pay', label: 'Certification/Education Pay' },
  { value: 'car-allowance', label: 'Car Allowance' },
  { value: 'uniform-allowance', label: 'Uniform Allowance' },
  { value: 'severance', label: 'Severance' },
  { value: 'other', label: 'Other' }
];

const CALCULATION_METHODS = [
  { value: 'hourly-rate', label: 'Hourly Rate (hours × rate)' },
  { value: 'salary-flat', label: 'Salary/Flat Amount per Period' },
  { value: 'flat-amount', label: 'One-Time Flat Amount' },
  { value: 'percent-base', label: 'Percentage of Base Pay' },
  { value: 'percent-gross', label: 'Percentage of Gross' },
  { value: 'other-formula', label: 'Other Formula/Method' }
];

// Track selected categories and pay codes
let selectedCategories = [];
let currentCategoryIndex = 0;
let currentCategory = null;
let payCodesByCategory = {}; // { 'overtime': [{name, gl, method, ...}] }
let currentPayCode = {};

// Start the conversation
setTimeout(() => {
  addMessage('assistant', 'Welcome to Section 3A: Pay Code Inventory!');
  setTimeout(() => {
    addMessage('assistant', 'We\\'ll document your pay code structure to identify consolidation opportunities and configuration issues.');
    setTimeout(() => {
      currentStep = 'category_selection';
      addMessage('assistant', 'First, which types of pay codes does your organization use? Select all that apply:', 'multi-select-start', {
        categories: PAY_CODE_CATEGORIES
      });
    }, 800);
  }, 800);
}, 500);

// Handle category selection (multi-select pattern)
window.handleCategoryToggle = function(category) {
  if (selectedCategories.includes(category)) {
    selectedCategories = selectedCategories.filter(c => c !== category);
  } else {
    selectedCategories.push(category);
  }
  // Update UI to show selected state
  const categoryBtns = document.querySelectorAll('.category-btn');
  categoryBtns.forEach(btn => {
    if (btn.dataset.category === category) {
      btn.classList.toggle('selected');
    }
  });
};

window.handleCategoryConfirm = function() {
  if (selectedCategories.length === 0) {
    alert('Please select at least one pay code category.');
    return;
  }

  answers['selectedCategories'] = selectedCategories;
  const categoryLabels = selectedCategories.map(c =>
    PAY_CODE_CATEGORIES.find(cat => cat.value === c)?.label || c
  ).join(', ');

  addMessage('user', `Selected: ${categoryLabels}`);

  setTimeout(() => {
    addMessage('assistant', `Great! You selected ${selectedCategories.length} categor${selectedCategories.length > 1 ? 'ies' : 'y'}.`);
    setTimeout(() => {
      addMessage('assistant', 'Now let\\'s document the pay codes in each category. I\\'ll walk you through them one at a time.');
      setTimeout(() => {
        currentCategory = selectedCategories[0];
        currentCategoryIndex = 0;
        payCodesByCategory[currentCategory] = [];
        startPayCodeCollection(currentCategory);
      }, 800);
    }, 600);
  }, 600);
};

function startPayCodeCollection(category) {
  const categoryLabel = PAY_CODE_CATEGORIES.find(c => c.value === category)?.label || category;
  currentStep = 'pay_code_name';
  currentPayCode = { category: category };

  setTimeout(() => {
    addMessage('assistant', `Let\\'s start with ${categoryLabel}. What\\'s the name of the first pay code?`, 'text-input', {
      inputType: 'text',
      placeholder: 'e.g., OT - Time and a Half'
    });
  }, 600);
}

// Handle user input
window.handleUserInput = function(step, value) {
  if (step === 'pay_code_name') {
    currentPayCode.name = value;
    answers[currentStep] = value;
    addMessage('user', value);

    setTimeout(() => {
      addMessage('assistant', `"${value}" — got it.`);
      setTimeout(() => {
        currentStep = 'gl_account';
        addMessage('assistant', 'What GL account is this pay code mapped to?', 'text-input', {
          inputType: 'text',
          placeholder: 'e.g., 01-100-5100 or 5100'
        });
      }, 800);
    }, 600);
  }
  else if (step === 'gl_account') {
    currentPayCode.glAccount = value;
    answers[currentStep] = value;
    addMessage('user', value);

    setTimeout(() => {
      addMessage('assistant', 'How is this pay code calculated?', 'select', {
        options: CALCULATION_METHODS
      });
      currentStep = 'calculation_method';
    }, 600);
  }
  else if (step === 'calculation_method') {
    currentPayCode.calculationMethod = value;
    const label = CALCULATION_METHODS.find(m => m.value === value)?.label || value;
    answers[currentStep] = value;
    addMessage('user', label);

    setTimeout(() => {
      addMessage('assistant', 'Is this pay code pensionable (counts toward retirement)?', 'choice-buttons', {
        options: [
          { value: 'yes', label: 'Yes' },
          { value: 'no', label: 'No' },
          { value: 'unsure', label: 'Unsure' }
        ]
      });
      currentStep = 'is_pensionable';
    }, 600);
  }
  else if (step === 'is_pensionable') {
    currentPayCode.isPensionable = value;
    answers[currentStep] = value;
    addMessage('user', value.charAt(0).toUpperCase() + value.slice(1));

    setTimeout(() => {
      addMessage('assistant', 'Is this included in the FLSA overtime calculation base?', 'choice-buttons', {
        options: [
          { value: 'yes', label: 'Yes' },
          { value: 'no', label: 'No' },
          { value: 'unsure', label: 'Unsure' }
        ]
      });
      currentStep = 'is_flsa_base';
    }, 600);
  }
  else if (step === 'is_flsa_base') {
    currentPayCode.isFlsaBase = value;
    answers[currentStep] = value;
    addMessage('user', value.charAt(0).toUpperCase() + value.slice(1));

    // Save this pay code
    payCodesByCategory[currentCategory].push({ ...currentPayCode });

    setTimeout(() => {
      addMessage('assistant', `Pay code "${currentPayCode.name}" saved.`);
      setTimeout(() => {
        currentStep = 'add_another';
        const categoryLabel = PAY_CODE_CATEGORIES.find(c => c.value === currentCategory)?.label;
        addMessage('assistant', `Do you have another ${categoryLabel} pay code to add?`, 'choice-buttons', {
          options: [
            { value: 'yes', label: 'Yes, add another' },
            { value: 'no', label: 'No, move to next category' }
          ]
        });
      }, 800);
    }, 600);
  }
  else if (step === 'add_another') {
    if (value === 'yes') {
      addMessage('user', 'Yes, add another');
      currentPayCode = { category: currentCategory };
      setTimeout(() => {
        currentStep = 'pay_code_name';
        addMessage('assistant', 'What\\'s the name of the next pay code?', 'text-input', {
          inputType: 'text',
          placeholder: 'e.g., OT - Double Time'
        });
      }, 600);
    } else {
      addMessage('user', 'No, move to next category');

      // Move to next category or finish
      currentCategoryIndex++;
      if (currentCategoryIndex < selectedCategories.length) {
        currentCategory = selectedCategories[currentCategoryIndex];
        payCodesByCategory[currentCategory] = [];
        setTimeout(() => {
          startPayCodeCollection(currentCategory);
        }, 600);
      } else {
        // All categories complete
        setTimeout(() => {
          finishSection();
        }, 600);
      }
    }
  }

  // Auto-save
  saveProgress();
};

function finishSection() {
  // Calculate totals
  let totalPayCodes = 0;
  for (let cat in payCodesByCategory) {
    totalPayCodes += payCodesByCategory[cat].length;
  }

  answers['payCodesByCategory'] = payCodesByCategory;
  answers['totalPayCodes'] = totalPayCodes;

  addMessage('assistant', `Excellent! You\\'ve documented ${totalPayCodes} pay codes across ${selectedCategories.length} categories.`);

  setTimeout(() => {
    addMessage('assistant', 'In the full version, I\\'ll analyze these for consolidation opportunities and compliance issues.');
    setTimeout(() => {
      saveProgress('completed');
      updateProgress(100);
      setTimeout(() => {
        addMessage('assistant', 'Section 3A complete! Returning to dashboard...');
        setTimeout(() => {
          window.location.href = '/app';
        }, 2000);
      }, 800);
    }, 1000);
  }, 800);
}
"""


# ============================================================
# ASSESSMENT API ENDPOINTS
# ============================================================

@app.post("/api/assessments")
async def create_assessment(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new assessment for the current user."""
    import uuid as _uuid
    from datetime import datetime
    import traceback

    # Debug: Print user dict structure
    print(f"DEBUG: User dict = {user}")

    try:
        assessment_id = str(_uuid.uuid4())

        # Get user_id safely
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            raise ValueError(f"No user ID found in user dict. Keys: {list(user.keys())}")

        db.execute(text("""
            INSERT INTO "Assessment" (id, "userId", status, "createdAt", "updatedAt")
            VALUES (:id, :user_id, 'draft', :now, :now)
        """), {
            "id": assessment_id,
            "user_id": user_id,
            "now": datetime.utcnow()
        })
        db.commit()

        return {"id": assessment_id, "status": "draft"}
    except Exception as e:
        db.rollback()
        print(f"ERROR creating assessment: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create assessment: {str(e)}")


@app.get("/api/assessments")
async def list_assessments(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all assessments for the current user."""
    result = db.execute(text("""
        SELECT id, status, "createdAt", "updatedAt"
        FROM "Assessment"
        WHERE "userId" = :user_id
        ORDER BY "createdAt" DESC
    """), {"user_id": user["user_id"]})

    assessments = []
    for row in result:
        assessments.append({
            "id": row[0],
            "status": row[1],
            "createdAt": row[2].isoformat() if row[2] else None,
            "updatedAt": row[3].isoformat() if row[3] else None
        })

    return {"assessments": assessments}


@app.get("/api/assessments/{assessment_id}")
async def get_assessment(
    assessment_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific assessment with all sections."""
    # Get assessment
    result = db.execute(text("""
        SELECT id, status, "organizationProfile", "createdAt", "updatedAt"
        FROM "Assessment"
        WHERE id = :id AND "userId" = :user_id
    """), {"id": assessment_id, "user_id": user["user_id"]})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Get sections
    sections_result = db.execute(text("""
        SELECT "sectionNumber", status, answers
        FROM "AssessmentSection"
        WHERE "assessmentId" = :assessment_id
        ORDER BY "sectionNumber"
    """), {"assessment_id": assessment_id})

    sections = []
    for section_row in sections_result:
        sections.append({
            "sectionNumber": section_row[0],
            "status": section_row[1],
            "answers": section_row[2] or {}
        })

    return {
        "id": row[0],
        "status": row[1],
        "organizationProfile": row[2] or {},
        "createdAt": row[3].isoformat() if row[3] else None,
        "updatedAt": row[4].isoformat() if row[4] else None,
        "sections": sections
    }


@app.post("/api/assessments/{assessment_id}/section")
async def save_assessment_section(
    assessment_id: str,
    request: AssessmentSectionSaveRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save answers for a specific section."""
    import uuid as _uuid

    # Verify assessment belongs to user
    result = db.execute(text("""
        SELECT id FROM "Assessment"
        WHERE id = :id AND "userId" = :user_id
    """), {"id": assessment_id, "user_id": user["user_id"]})

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Upsert section
    section_id = str(_uuid.uuid4())
    db.execute(text("""
        INSERT INTO "AssessmentSection" (id, "assessmentId", "sectionNumber", status, answers)
        VALUES (:id, :assessment_id, :section_number, :status, :answers)
        ON CONFLICT ("assessmentId", "sectionNumber")
        DO UPDATE SET
            status = EXCLUDED.status,
            answers = EXCLUDED.answers
    """), {
        "id": section_id,
        "assessment_id": assessment_id,
        "section_number": request.section_number,
        "status": request.status,
        "answers": json.dumps(request.answers)
    })

    # If section 1, also update organizationProfile
    if request.section_number == "1":
        db.execute(text("""
            UPDATE "Assessment"
            SET "organizationProfile" = :profile
            WHERE id = :assessment_id
        """), {
            "profile": json.dumps(request.answers),
            "assessment_id": assessment_id
        })

    db.commit()

    return {"success": True}


class AIAnalysisRequest(BaseModel):
    section_number: str
    data: dict  # Section-specific data to analyze


@app.post("/api/assessments/{assessment_id}/analyze")
async def analyze_with_ai(
    assessment_id: str,
    request: AIAnalysisRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze assessment data using Claude AI."""
    # Verify assessment belongs to user
    result = db.execute(text("""
        SELECT "organizationProfile" FROM "Assessment"
        WHERE id = :id AND "userId" = :user_id
    """), {"id": assessment_id, "user_id": user["user_id"]})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Assessment not found")

    org_profile = json.loads(row[0]) if row[0] else {}

    # Get state from organization profile
    state = org_profile.get("state", "Unknown")

    # Route to appropriate analysis function
    if request.section_number == "2":
        # COA Analysis
        analysis = await analyze_coa_structure(
            account_count=request.data.get("account_count", "unknown"),
            last_review=request.data.get("last_review", "unknown"),
            state=state,
            inactive_percentage=request.data.get("inactive_percentage", "unknown")
        )
    elif request.section_number == "3a":
        # Pay Code Analysis
        analysis = await analyze_pay_codes(
            pay_codes_by_category=request.data.get("payCodesByCategory", {}),
            state=state,
            retirement_system=org_profile.get("retirement_system", "Unknown")
        )
    else:
        return {"error": "AI analysis not available for this section"}

    if not analysis:
        return {"error": "AI analysis unavailable (API key not configured)"}

    return {"analysis": analysis}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
