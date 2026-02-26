"""
Municipal Intel - FastAPI Application v2.1

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
import uuid as _uuid
import base64
import resend
import hashlib

from src.database import init_db, get_db, Scan, Lead, Municipality, MunicipalSource, User, Watchlist, Territory, CachedDocument
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
app = FastAPI(title="Municipal Intel", version="2.1")

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
    status: Optional[str] = None  # new | contacted | qualified | proposal | won | lost
    deal_value: Optional[int] = None  # Deal value in USD
    contacted_date: Optional[str] = None  # ISO timestamp
    won_date: Optional[str] = None  # ISO timestamp
    lost_reason: Optional[str] = None


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

    try:
        # Get scan record
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            return

        # Get user's vendor configuration
        user = db.query(User).filter(User.id == scan.user_id).first()
        vendor_name = user.vendor_name if user else None
        vendor_competitors = user.vendor_competitors if user else None

        # Initialize scraper and analyzer with vendor config
        scraper = MunicipalScraper(delay=1.5, timeout=8, max_docs=10, db_session=db, use_cache=True)
        analyzer = DocumentAnalyzer(
            use_llm=False,  # Disable LLM for speed
            vendor_name=vendor_name,
            vendor_competitors=vendor_competitors
        )
        discovery = SourceDiscovery(request_delay=1.0, timeout=8)

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
                                # Calculate document hash for deduplication
                                doc_hash = hashlib.md5(result.document_text.encode()).hexdigest()

                                # Check if we've seen this exact document before
                                existing_lead = db.query(Lead).filter(
                                    Lead.document_hash == doc_hash
                                ).first()

                                if existing_lead:
                                    # Update existing lead - mark as seen again
                                    existing_lead.last_seen = datetime.utcnow()
                                    existing_lead.times_seen += 1

                                    # Update relevance score if this scan found higher score
                                    if result.relevance_score > existing_lead.relevance_score:
                                        existing_lead.relevance_score = result.relevance_score
                                        existing_lead.lead_type = result.lead_type

                                    db.commit()

                                    # Still count for this scan's stats
                                    if existing_lead.lead_type == "hot":
                                        leads_hot += 1
                                    elif existing_lead.lead_type == "warm":
                                        leads_warm += 1
                                    else:
                                        leads_cold += 1
                                else:
                                    # Parse deadline date if present
                                    from dateutil import parser as dateparser
                                    deadline_dt = None
                                    if result.deadline_date:
                                        try:
                                            deadline_dt = dateparser.parse(result.deadline_date)
                                        except:
                                            pass

                                    # Create new lead record
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
                                        },
                                        document_hash=doc_hash,
                                        first_seen=datetime.utcnow(),
                                        last_seen=datetime.utcnow(),
                                        times_seen=1,
                                        # Temporal intelligence fields
                                        urgency_score=result.urgency_score,
                                        deadline_date=deadline_dt,
                                        days_until_deadline=result.days_until_deadline,
                                        decision_stage=result.decision_stage,
                                        fiscal_year=result.fiscal_year,
                                        # Competitor intelligence
                                        competitors_mentioned=result.competitors_mentioned,
                                        competitive_context=result.competitive_context,
                                        existing_vendor=result.existing_vendor
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

        # Send email alerts for hot/urgent leads
        try:
            from src.notifications import send_hot_lead_alert
            import asyncio

            # Get user info
            user = db.query(User).filter(User.id == scan.user_id).first()

            if user and user.email_alerts_enabled:
                # Get user's territories
                territories = db.query(Territory).filter(Territory.user_id == user.id).all()
                territory_states = [t.state for t in territories] if territories else None

                # Get hot/urgent leads from this scan
                alert_criteria = []
                if user.alert_on_hot_leads:
                    alert_criteria.append(Lead.lead_type == "hot")
                if user.alert_on_urgent_leads:
                    alert_criteria.append(Lead.urgency_score >= user.min_urgency_for_alert)

                if alert_criteria:
                    from sqlalchemy import or_
                    alert_leads = db.query(Lead).filter(
                        Lead.scan_id == scan_id,
                        Lead.times_seen == 1,  # Only NEW leads
                        or_(*alert_criteria)
                    ).all()

                    if alert_leads:
                        # Format leads for email
                        leads_data = []
                        for lead in alert_leads[:10]:  # Max 10 in immediate alert
                            leads_data.append({
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
                                "urgency_score": lead.urgency_score,
                                "deadline_date": lead.deadline_date.isoformat() if lead.deadline_date else None,
                                "days_until_deadline": lead.days_until_deadline,
                                "decision_stage": lead.decision_stage,
                                "signal_matches": lead.signal_matches_json
                            })

                        # Send alert (async)
                        asyncio.create_task(send_hot_lead_alert(user.email, leads_data, territory_states))
                        logger.info(f"Triggered email alert for {len(alert_leads)} leads to {user.email}")

        except Exception as e:
            logger.error(f"Failed to send email alerts: {e}")
            # Don't fail the scan if email fails

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
    return {"status": "ok", "version": "2.1.0"}


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
# RESOURCE DOWNLOAD ENDPOINT
# ============================================================

class ResourceDownloadRequest(BaseModel):
    email: str
    name: Optional[str] = None
    title: Optional[str] = None
    municipality: Optional[str] = None


@app.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request):
    """Render the ERP Playbook resource page."""
    return templates.TemplateResponse("resources.html", {"request": request})


@app.get("/playbook/thank-you", response_class=HTMLResponse)
async def playbook_thank_you(request: Request, email: str = ""):
    """Render the playbook download confirmation/thank-you page."""
    return templates.TemplateResponse("playbook_thank_you.html", {
        "request": request,
        "email": email
    })


@app.post("/api/resources/download")
async def download_resource(
    request: ResourceDownloadRequest,
    fastapi_request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle resource download requests. Tracks download in database and sends PDF via email.
    """
    try:
        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS resource_downloads (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT,
                title TEXT,
                municipality TEXT,
                resource_name TEXT NOT NULL,
                downloaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                user_agent TEXT,
                ip_address TEXT
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_resource_downloads_email
            ON resource_downloads(email)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_resource_downloads_resource_name
            ON resource_downloads(resource_name)
        """))

        # Generate unique ID
        download_id = str(_uuid.uuid4())

        # Get user agent and IP
        user_agent = fastapi_request.headers.get("user-agent", "")
        # Get IP from X-Forwarded-For header (Railway uses this)
        ip_address = fastapi_request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip_address:
            ip_address = fastapi_request.client.host if fastapi_request.client else ""

        # Track download
        db.execute(text("""
            INSERT INTO resource_downloads
            (id, email, name, title, municipality, resource_name, user_agent, ip_address)
            VALUES (:id, :email, :name, :title, :municipality, :resource_name, :user_agent, :ip_address)
        """), {
            "id": download_id,
            "email": request.email.lower().strip(),
            "name": request.name,
            "title": request.title,
            "municipality": request.municipality,
            "resource_name": "ERP Replacement Playbook",
            "user_agent": user_agent,
            "ip_address": ip_address
        })
        db.commit()

        # Send email with PDF
        resend_api_key = os.getenv("RESEND_API_KEY")
        app_url = os.getenv("APP_URL", "https://govtechdiagnostic.com")

        if not resend_api_key:
            raise HTTPException(status_code=500, detail="Email service not configured")

        # Read PDF file
        pdf_path = "static/ERP-Replacement-Playbook-GovTech-Diagnostic.pdf"
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=500, detail="Resource file not found")

        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
            pdf_base64 = base64.b64encode(pdf_content).decode()

        # Compose email
        first_name = request.name.split()[0] if request.name else "there"
        email_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px; color: #1A1816;">
            <div style="text-align: center; margin-bottom: 32px;">
                <img src="{app_url}/static/govtech-logo-dark.svg" alt="GovTech Diagnostic" style="height: 48px; margin-bottom: 20px;">
            </div>

            <div style="border-bottom: 2px solid #EDE9E1; margin-bottom: 32px;"></div>

            <p style="color: #3D3A35; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                Hi {first_name},
            </p>

            <p style="color: #3D3A35; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                Your copy of the <strong>Municipal ERP Replacement Playbook</strong> is attached to this email.
            </p>

            <p style="color: #3D3A35; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                This isn't a generic whitepaper. It's a practical, 32-page implementation guide built from patterns we've seen across hundreds of municipal ERP projects. Here's what's inside:
            </p>

            <ul style="color: #3D3A35; font-size: 16px; line-height: 1.8; margin: 0 0 28px 20px; padding: 0;">
                <li style="margin-bottom: 8px;"><span style="color: #1B7A4E; font-weight: 600;">✓</span> 9 phases from "we have a problem" to post-go-live optimization</li>
                <li style="margin-bottom: 8px;"><span style="color: #1B7A4E; font-weight: 600;">✓</span> 6 composite case studies showing what actually goes right and wrong</li>
                <li style="margin-bottom: 8px;"><span style="color: #1B7A4E; font-weight: 600;">✓</span> Cost benchmarks by municipality size ($150K to $15M+)</li>
                <li style="margin-bottom: 8px;"><span style="color: #1B7A4E; font-weight: 600;">✓</span> Ready-to-use templates: readiness assessment, vendor scorecard, TCO worksheet, evaluation criteria, data migration checklist</li>
            </ul>

            <div style="border-top: 2px solid #EDE9E1; border-bottom: 2px solid #EDE9E1; padding: 28px 0; margin: 32px 0;">
                <h2 style="color: #1A1816; font-size: 20px; margin: 0 0 16px 0; font-weight: 600;">Where to Start</h2>

                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
                    If you're <strong>early in the process</strong> — wondering whether it's time to replace your system — start with Phase 1 (Recognize the Problem) and the self-assessment in Appendix A.
                </p>

                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
                    If you're <strong>already building a case</strong> for leadership, jump to Phase 2 (Build the Internal Case) for the stakeholder mapping and business case framework.
                </p>

                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0;">
                    If you're <strong>in active procurement</strong>, Phases 4-6 cover requirements gathering, vendor evaluation, and contract negotiation — including the specific contract protections that save municipalities from the most common gotchas.
                </p>
            </div>

            <div style="background: #F7F5F0; border-radius: 12px; padding: 24px; margin-bottom: 32px;">
                <h2 style="color: #1A1816; font-size: 20px; margin: 0 0 16px 0; font-weight: 600;">Coming Soon: Free ERP Readiness Assessment</h2>
                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0 0 20px 0;">
                    We're building an AI-powered diagnostic that evaluates your municipality's ERP readiness across five dimensions — technology, process, data, organizational, and financial — and delivers a personalized findings report.
                </p>
                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
                    Vendor-neutral. No sales pitch. Free for municipalities.
                </p>
                <a href="{app_url}/#waitlist" style="display: inline-block; background: #1B7A4E; color: #FFFFFF; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px;">
                    Join the Waitlist →
                </a>
            </div>

            <div style="border-top: 2px solid #EDE9E1; padding-top: 28px; margin-top: 32px;">
                <p style="color: #3D3A35; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
                    Questions? Reply to this email — it goes to a real person.
                </p>
                <p style="color: #7A756D; font-size: 14px; margin: 0 0 8px 0;">
                    — The GovTech Diagnostic Team<br>
                    <a href="{app_url}" style="color: #1E3BC0; text-decoration: none;">govtechdiagnostic.com</a>
                </p>
            </div>

            <div style="text-align: center; padding-top: 24px; border-top: 1px solid #EDE9E1; margin-top: 24px;">
                <p style="color: #9C9689; font-size: 12px; margin: 0;">
                    © 2026 GovTech Diagnostic. All rights reserved.
                </p>
            </div>
        </div>
        """

        # Send via Resend
        resend.api_key = resend_api_key
        params = {
            "from": os.getenv("RESEND_FROM_EMAIL", "GovTech Diagnostic <noreply@govtechdiagnostic.com>"),
            "to": [request.email],
            "subject": "Your Municipal ERP Replacement Playbook is ready",
            "html": email_html,
            "attachments": [
                {
                    "filename": "Municipal-ERP-Replacement-Playbook.pdf",
                    "content": pdf_base64
                }
            ]
        }

        resend.Emails.send(params)

        return {"success": True, "message": "Playbook sent successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error processing resource download: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process download request")


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


@app.get("/lead/{lead_id}", response_class=HTMLResponse)
async def lead_detail(request: Request, lead_id: str, user: dict = Depends(require_role(["consultant", "admin"])), db: Session = Depends(get_db)):
    """
    Lead detail page showing full intelligence for a specific lead.

    Displays all analyzed signals, temporal intelligence, competitor data,
    recommended actions, and source documents.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return templates.TemplateResponse("lead_detail.html", {
        "request": request,
        "user": user,
        "lead": lead
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

    # State code to name mapping
    STATE_NAMES = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
        "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
        "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
        "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
        "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
        "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
        "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
        "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
        "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico",
        "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
        "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
        "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"
    }

    rows = (
        db.query(Municipality.state, func.count(MunicipalSource.id).label("source_count"))
        .join(MunicipalSource, MunicipalSource.municipality_id == Municipality.id)
        .group_by(Municipality.state)
        .order_by(Municipality.state)
        .all()
    )

    states = []
    total_sources = 0
    for row in rows:
        state_code = row.state
        source_count = row.source_count
        total_sources += source_count
        states.append({
            "abbr": state_code,
            "name": STATE_NAMES.get(state_code, state_code),
            "source_count": source_count
        })

    return {
        "states": states,
        "total_sources": total_sources
    }


@app.get("/api/feed")
async def get_feed(
    limit: int = 50,
    offset: int = 0,
    # Basic filters
    state: Optional[str] = None,
    lead_type: Optional[str] = None,
    customer_status: Optional[str] = None,
    source_type: Optional[str] = None,
    # Temporal filters
    days: Optional[int] = None,
    new_only: bool = False,
    urgent_only: bool = False,
    min_urgency: Optional[int] = None,
    max_urgency: Optional[int] = None,
    decision_stage: Optional[str] = None,
    has_deadline: Optional[bool] = None,
    deadline_within_days: Optional[int] = None,
    # Population filters
    min_population: Optional[int] = None,
    max_population: Optional[int] = None,
    # Score filters
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    # Competitor filters
    has_competitors: Optional[bool] = None,
    competitor: Optional[str] = None,
    existing_vendor: Optional[str] = None,
    # ROI/Status filters
    status: Optional[str] = None,
    has_deal_value: Optional[bool] = None,
    # Sorting
    sort_by: Optional[str] = "relevance",  # relevance | urgency | deadline | population | date
    sort_order: Optional[str] = "desc",  # asc | desc
    # Search
    search: Optional[str] = None,
    # Grouping
    group_by_municipality: bool = True,  # Group duplicate municipalities (default: true)
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Advanced Feed API endpoint - returns leads with comprehensive filtering.

    **Basic Filters:**
    - state: Filter by state code (e.g., "CA", "TX")
    - lead_type: hot | warm | cold
    - customer_status: existing_customer | new_opportunity
    - source_type: meeting_minutes | procurement | budget | job_posting | agenda_packet | audit

    **Temporal Filters:**
    - days: Leads discovered in last N days
    - new_only: Only newly discovered leads (times_seen == 1)
    - urgent_only: Urgency score >= 60
    - min_urgency / max_urgency: Urgency score range (0-100)
    - decision_stage: exploration | evaluation | procurement | implementation
    - has_deadline: true = only leads with deadlines
    - deadline_within_days: Only leads with deadlines in next N days

    **Population Filters:**
    - min_population / max_population: Population range

    **Score Filters:**
    - min_score / max_score: Relevance score range (0-100)

    **Competitor Filters:**
    - has_competitors: true = only leads mentioning competitors
    - competitor: Filter by specific competitor name (e.g., "Tyler Technologies")
    - existing_vendor: Filter by current vendor

    **ROI/Status Filters:**
    - status: new | contacted | qualified | proposal | won | lost
    - has_deal_value: true = only leads with deal values

    **Sorting:**
    - sort_by: relevance | urgency | deadline | population | date
    - sort_order: asc | desc

    **Search:**
    - search: Full-text search in municipality name or title

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

    # Apply basic filters
    if state:
        query = query.filter(Lead.state == state.upper())
    if lead_type:
        query = query.filter(Lead.lead_type == lead_type.lower())
    if customer_status:
        query = query.filter(Lead.customer_status == customer_status.lower())
    if source_type:
        query = query.filter(Lead.source_type == source_type.lower())

    # Apply temporal filters
    if days:
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Scan.completed_at >= cutoff_date)
    if new_only:
        query = query.filter(Lead.times_seen == 1)
    if urgent_only:
        query = query.filter(Lead.urgency_score >= 60)
    if min_urgency is not None:
        query = query.filter(Lead.urgency_score >= min_urgency)
    if max_urgency is not None:
        query = query.filter(Lead.urgency_score <= max_urgency)
    if decision_stage:
        query = query.filter(Lead.decision_stage == decision_stage.lower())
    if has_deadline is not None:
        if has_deadline:
            query = query.filter(Lead.deadline_date.isnot(None))
        else:
            query = query.filter(Lead.deadline_date.is_(None))
    if deadline_within_days is not None:
        query = query.filter(
            Lead.days_until_deadline.isnot(None),
            Lead.days_until_deadline <= deadline_within_days,
            Lead.days_until_deadline >= 0  # Future deadlines only
        )

    # Apply population filters
    if min_population is not None:
        query = query.filter(Lead.population >= min_population)
    if max_population is not None:
        query = query.filter(Lead.population <= max_population)

    # Apply score filters
    if min_score is not None:
        query = query.filter(Lead.relevance_score >= min_score)
    if max_score is not None:
        query = query.filter(Lead.relevance_score <= max_score)

    # Apply competitor filters
    if has_competitors is not None:
        if has_competitors:
            # PostgreSQL: Check if JSON array is not null and not empty
            from sqlalchemy import func, cast, String
            query = query.filter(
                Lead.competitors_mentioned.isnot(None),
                func.json_array_length(cast(Lead.competitors_mentioned, String)) > 0
            )
        else:
            query = query.filter(
                (Lead.competitors_mentioned.is_(None)) |
                (func.json_array_length(cast(Lead.competitors_mentioned, String)) == 0)
            )
    if competitor:
        # Filter by specific competitor (case-insensitive partial match in JSON array)
        from sqlalchemy import func, cast, String
        query = query.filter(
            func.lower(cast(Lead.competitors_mentioned, String)).contains(competitor.lower())
        )
    if existing_vendor:
        query = query.filter(Lead.existing_vendor == existing_vendor)

    # Apply ROI/Status filters
    if status:
        query = query.filter(Lead.status == status.lower())
    if has_deal_value is not None:
        if has_deal_value:
            query = query.filter(Lead.deal_value.isnot(None), Lead.deal_value > 0)
        else:
            query = query.filter((Lead.deal_value.is_(None)) | (Lead.deal_value == 0))

    # Apply search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Lead.municipality.ilike(search_term)) |
            (Lead.title.ilike(search_term))
        )

    # Get total count for pagination metadata (before grouping)
    total_count = query.count()

    # Apply sorting
    if sort_by == "urgency":
        order_col = Lead.urgency_score
    elif sort_by == "deadline":
        order_col = Lead.days_until_deadline
    elif sort_by == "population":
        order_col = Lead.population
    elif sort_by == "date":
        order_col = Lead.first_seen
    else:  # relevance (default)
        order_col = Lead.relevance_score

    if sort_order == "asc":
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    # Group by municipality if requested
    if group_by_municipality:
        # Get all leads first, then group in Python (simpler than SQL window functions)
        all_leads = query.all()

        # Group by municipality+state
        from collections import defaultdict
        grouped = defaultdict(list)
        for lead in all_leads:
            key = (lead.municipality, lead.state)
            grouped[key].append(lead)

        # For each municipality, pick the best lead and count others
        leads = []
        for (muni, state), muni_leads in grouped.items():
            # Sort by urgency (desc), then score (desc)
            muni_leads.sort(key=lambda l: (l.urgency_score or 0, l.relevance_score), reverse=True)
            best_lead = muni_leads[0]

            # Add document count as metadata
            best_lead._document_count = len(muni_leads)
            best_lead._all_urls = [l.url for l in muni_leads]

            leads.append(best_lead)

        # Re-sort the grouped leads
        leads.sort(key=lambda l: getattr(l, order_col.key, 0) if hasattr(order_col, 'key') else l.relevance_score, reverse=(sort_order == "desc"))

        # Apply pagination after grouping
        total_count = len(leads)
        leads = leads[offset:offset + limit]
    else:
        # Apply pagination without grouping
        leads = query.limit(limit).offset(offset).all()
        # Add document count = 1 for consistency
        for lead in leads:
            lead._document_count = 1
            lead._all_urls = [lead.url]

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
            "scan_id": lead.scan_id,
            "first_seen": lead.first_seen.isoformat() if lead.first_seen else None,
            "last_seen": lead.last_seen.isoformat() if lead.last_seen else None,
            "times_seen": lead.times_seen if lead.times_seen else 1,
            "is_new": lead.times_seen == 1 if lead.times_seen else True,
            # Temporal intelligence
            "urgency_score": lead.urgency_score if lead.urgency_score else 0,
            "deadline_date": lead.deadline_date.isoformat() if lead.deadline_date else None,
            "days_until_deadline": lead.days_until_deadline,
            "decision_stage": lead.decision_stage if lead.decision_stage else "unknown",
            "fiscal_year": lead.fiscal_year,
            # ROI tracking
            "status": lead.status if hasattr(lead, 'status') else "new",
            "deal_value": lead.deal_value if hasattr(lead, 'deal_value') else None,
            "contacted_date": lead.contacted_date.isoformat() if hasattr(lead, 'contacted_date') and lead.contacted_date else None,
            "won_date": lead.won_date.isoformat() if hasattr(lead, 'won_date') and lead.won_date else None,
            "lost_reason": lead.lost_reason if hasattr(lead, 'lost_reason') else None,
            # Competitor intelligence
            "competitors_mentioned": lead.competitors_mentioned if hasattr(lead, 'competitors_mentioned') else [],
            "competitive_context": lead.competitive_context if hasattr(lead, 'competitive_context') else "",
            "existing_vendor": lead.existing_vendor if hasattr(lead, 'existing_vendor') else None,
            # Grouping metadata
            "document_count": getattr(lead, '_document_count', 1),
            "all_urls": getattr(lead, '_all_urls', [lead.url])
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
            # Active filters (for UI to show what's applied)
            "basic": {
                "state": state,
                "lead_type": lead_type,
                "customer_status": customer_status,
                "source_type": source_type,
            },
            "temporal": {
                "days": days,
                "new_only": new_only,
                "urgent_only": urgent_only,
                "min_urgency": min_urgency,
                "max_urgency": max_urgency,
                "decision_stage": decision_stage,
                "has_deadline": has_deadline,
                "deadline_within_days": deadline_within_days,
            },
            "population": {
                "min_population": min_population,
                "max_population": max_population,
            },
            "score": {
                "min_score": min_score,
                "max_score": max_score,
            },
            "competitor": {
                "has_competitors": has_competitors,
                "competitor": competitor,
                "existing_vendor": existing_vendor,
            },
            "roi": {
                "status": status,
                "has_deal_value": has_deal_value,
            },
            "sort": {
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
            "search": search,
            "territories": [t.state for t in territories] if territories else None
        }
    }


@app.get("/api/feed/filter-options")
async def get_filter_options(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get available filter options for the feed.

    Returns distinct values for filterable fields based on user's data.
    Useful for building dynamic filter UI components.

    **Requires authentication.**
    """
    from sqlalchemy import func, distinct

    # Get user's territories
    territories = db.query(Territory).filter(Territory.user_id == user["user_id"]).all()
    territory_states = [t.state for t in territories] if territories else None

    # Base query for user's leads
    base_query = (
        db.query(Lead)
        .join(Scan, Lead.scan_id == Scan.id)
        .filter(Scan.user_id == user["user_id"])
    )

    # Filter by territories if exist
    if territory_states:
        base_query = base_query.filter(Lead.state.in_(territory_states))

    # Get distinct states
    states_query = base_query.with_entities(distinct(Lead.state)).order_by(Lead.state)
    states = [s[0] for s in states_query.all() if s[0]]

    # Get distinct source types
    source_types_query = base_query.with_entities(distinct(Lead.source_type)).order_by(Lead.source_type)
    source_types = [s[0] for s in source_types_query.all() if s[0]]

    # Get distinct decision stages
    decision_stages_query = base_query.with_entities(distinct(Lead.decision_stage)).order_by(Lead.decision_stage)
    decision_stages = [s[0] for s in decision_stages_query.all() if s[0] and s[0] != "unknown"]

    # Get distinct competitors (flatten JSON arrays)
    from collections import Counter
    all_competitors = []
    leads_with_competitors = base_query.filter(Lead.competitors_mentioned.isnot(None)).all()
    for lead in leads_with_competitors:
        if lead.competitors_mentioned:
            all_competitors.extend(lead.competitors_mentioned)
    competitor_counts = Counter(all_competitors)
    competitors = [{"name": comp, "count": count} for comp, count in competitor_counts.most_common(20)]

    # Get distinct existing vendors
    vendors_query = (
        base_query
        .with_entities(Lead.existing_vendor, func.count(Lead.id).label('count'))
        .filter(Lead.existing_vendor.isnot(None))
        .group_by(Lead.existing_vendor)
        .order_by(func.count(Lead.id).desc())
    )
    existing_vendors = [{"name": v[0], "count": v[1]} for v in vendors_query.all()]

    # Get score ranges
    score_stats = (
        base_query
        .with_entities(
            func.min(Lead.relevance_score).label('min_score'),
            func.max(Lead.relevance_score).label('max_score'),
            func.avg(Lead.relevance_score).label('avg_score')
        )
        .first()
    )

    # Get urgency ranges
    urgency_stats = (
        base_query
        .with_entities(
            func.min(Lead.urgency_score).label('min_urgency'),
            func.max(Lead.urgency_score).label('max_urgency'),
            func.avg(Lead.urgency_score).label('avg_urgency')
        )
        .first()
    )

    # Get population ranges
    pop_stats = (
        base_query
        .with_entities(
            func.min(Lead.population).label('min_pop'),
            func.max(Lead.population).label('max_pop'),
            func.avg(Lead.population).label('avg_pop')
        )
        .first()
    )

    return {
        "categorical": {
            "states": states,
            "lead_types": ["hot", "warm", "cold"],
            "customer_statuses": ["existing_customer", "new_opportunity"],
            "source_types": source_types,
            "decision_stages": decision_stages,
            "statuses": ["new", "contacted", "qualified", "proposal", "won", "lost"],
        },
        "competitors": {
            "all": competitors,
            "existing_vendors": existing_vendors,
        },
        "ranges": {
            "score": {
                "min": float(score_stats.min_score) if score_stats.min_score else 0,
                "max": float(score_stats.max_score) if score_stats.max_score else 100,
                "avg": float(score_stats.avg_score) if score_stats.avg_score else 50,
            },
            "urgency": {
                "min": int(urgency_stats.min_urgency) if urgency_stats.min_urgency else 0,
                "max": int(urgency_stats.max_urgency) if urgency_stats.max_urgency else 100,
                "avg": int(urgency_stats.avg_urgency) if urgency_stats.avg_urgency else 0,
            },
            "population": {
                "min": int(pop_stats.min_pop) if pop_stats.min_pop else 0,
                "max": int(pop_stats.max_pop) if pop_stats.max_pop else 1000000,
                "avg": int(pop_stats.avg_pop) if pop_stats.avg_pop else 50000,
            }
        },
        "sort_options": [
            {"value": "relevance", "label": "Relevance Score"},
            {"value": "urgency", "label": "Urgency Score"},
            {"value": "deadline", "label": "Deadline (Soonest First)"},
            {"value": "population", "label": "Population"},
            {"value": "date", "label": "Date Discovered"},
        ],
        "territories": territory_states
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
                "notes": lead.notes,
                "status": lead.status if hasattr(lead, 'status') else "new",
                "deal_value": lead.deal_value if hasattr(lead, 'deal_value') else None,
                "contacted_date": lead.contacted_date.isoformat() if hasattr(lead, 'contacted_date') and lead.contacted_date else None,
                "won_date": lead.won_date.isoformat() if hasattr(lead, 'won_date') and lead.won_date else None
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
    """
    Update lead notes and status tracking fields.

    Supports updating:
    - notes: User notes
    - status: Pipeline stage (new | contacted | qualified | proposal | won | lost)
    - deal_value: Deal value in USD (if won)
    - contacted_date: ISO timestamp of first contact
    - won_date: ISO timestamp of deal close
    - lost_reason: Explanation if deal was lost

    Requires authentication and scan ownership.
    """
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

    # Update fields
    if update.notes is not None:
        lead.notes = update.notes

    if update.status is not None:
        valid_statuses = ["new", "contacted", "qualified", "proposal", "won", "lost"]
        if update.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        lead.status = update.status

    if update.deal_value is not None:
        lead.deal_value = update.deal_value

    if update.contacted_date is not None:
        from datetime import datetime
        lead.contacted_date = datetime.fromisoformat(update.contacted_date.replace('Z', '+00:00'))

    if update.won_date is not None:
        from datetime import datetime
        lead.won_date = datetime.fromisoformat(update.won_date.replace('Z', '+00:00'))

    if update.lost_reason is not None:
        lead.lost_reason = update.lost_reason

    db.commit()

    return {"success": True}


@app.get("/api/vendor-config")
async def get_vendor_config(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's vendor configuration for vendor-neutral scanning.

    Returns:
    - vendor_name: User's ERP vendor (e.g. "Caselle", "Tyler Technologies", null for neutral)
    - vendor_competitors: List of competitor vendors to track
    """
    user_record = db.query(User).filter(User.id == user["user_id"]).first()
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "vendor_name": user_record.vendor_name,
        "vendor_competitors": user_record.vendor_competitors or []
    }


@app.patch("/api/vendor-config")
async def update_vendor_config(
    config: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user's vendor configuration.

    Body:
    - vendor_name: string | null (e.g. "Caselle", "Tyler Technologies")
    - vendor_competitors: string[] (e.g. ["Tyler", "CentralSquare"])
    """
    user_record = db.query(User).filter(User.id == user["user_id"]).first()
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    # Update vendor configuration
    if "vendor_name" in config:
        vendor_name = config["vendor_name"]
        if vendor_name and len(vendor_name) > 100:
            raise HTTPException(status_code=400, detail="Vendor name too long (max 100 chars)")
        user_record.vendor_name = vendor_name if vendor_name else None

    if "vendor_competitors" in config:
        competitors = config["vendor_competitors"]
        if not isinstance(competitors, list):
            raise HTTPException(status_code=400, detail="vendor_competitors must be an array")
        # Validate each competitor is a string
        if not all(isinstance(c, str) for c in competitors):
            raise HTTPException(status_code=400, detail="All competitors must be strings")
        user_record.vendor_competitors = competitors

    db.commit()

    return {
        "success": True,
        "vendor_name": user_record.vendor_name,
        "vendor_competitors": user_record.vendor_competitors or []
    }


@app.get("/api/roi-analytics")
async def get_roi_analytics(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get ROI analytics: conversion rates, total revenue, and pipeline metrics.

    Shows:
    - Total leads by status (new, contacted, qualified, proposal, won, lost)
    - Conversion rates (new → contacted → qualified → proposal → won)
    - Total revenue attributed to the tool (sum of won deal values)
    - Average deal size
    - Average time from discovery to close (for won deals)

    Requires authentication. Users only see analytics for their own leads.
    """
    from datetime import datetime
    from sqlalchemy import func

    # Get all leads for user's scans
    leads_query = (
        db.query(Lead)
        .join(Scan, Lead.scan_id == Scan.id)
        .filter(Scan.user_id == user["user_id"])
    )

    # Total leads
    total_leads = leads_query.count()

    # Leads by status
    status_counts = {}
    for status in ["new", "contacted", "qualified", "proposal", "won", "lost"]:
        count = leads_query.filter(Lead.status == status).count()
        status_counts[status] = count

    # Calculate conversion rates
    conversion_rates = {}
    if status_counts["new"] > 0:
        conversion_rates["new_to_contacted"] = round((status_counts["contacted"] / status_counts["new"]) * 100, 1) if status_counts["new"] > 0 else 0
    if status_counts["contacted"] > 0:
        conversion_rates["contacted_to_qualified"] = round((status_counts["qualified"] / status_counts["contacted"]) * 100, 1)
    if status_counts["qualified"] > 0:
        conversion_rates["qualified_to_proposal"] = round((status_counts["proposal"] / status_counts["qualified"]) * 100, 1)
    if status_counts["proposal"] > 0:
        conversion_rates["proposal_to_won"] = round((status_counts["won"] / status_counts["proposal"]) * 100, 1)

    # Overall win rate (won / total leads)
    win_rate = round((status_counts["won"] / total_leads) * 100, 1) if total_leads > 0 else 0

    # Won deals
    won_leads = leads_query.filter(Lead.status == "won").all()

    # Total revenue
    total_revenue = sum([lead.deal_value for lead in won_leads if lead.deal_value])

    # Average deal size
    deal_values = [lead.deal_value for lead in won_leads if lead.deal_value]
    avg_deal_size = round(sum(deal_values) / len(deal_values)) if deal_values else 0

    # Average time to close (first_seen → won_date)
    time_to_close_days = []
    for lead in won_leads:
        if lead.won_date and lead.first_seen:
            delta = lead.won_date - lead.first_seen
            time_to_close_days.append(delta.days)

    avg_time_to_close = round(sum(time_to_close_days) / len(time_to_close_days)) if time_to_close_days else None

    # Pipeline value (sum of proposal stage deal values)
    proposal_leads = leads_query.filter(Lead.status == "proposal").all()
    pipeline_value = sum([lead.deal_value for lead in proposal_leads if lead.deal_value])

    return {
        "summary": {
            "total_leads": total_leads,
            "total_revenue": total_revenue,
            "avg_deal_size": avg_deal_size,
            "win_rate_pct": win_rate,
            "avg_time_to_close_days": avg_time_to_close,
            "pipeline_value": pipeline_value
        },
        "status_breakdown": status_counts,
        "conversion_rates": conversion_rates,
        "recent_wins": [
            {
                "id": lead.id,
                "municipality": lead.municipality,
                "state": lead.state,
                "deal_value": lead.deal_value,
                "won_date": lead.won_date.isoformat() if lead.won_date else None,
                "days_to_close": (lead.won_date - lead.first_seen).days if lead.won_date and lead.first_seen else None
            }
            for lead in sorted(won_leads, key=lambda l: l.won_date if l.won_date else datetime.min, reverse=True)[:10]
        ]
    }


@app.get("/api/analytics/dashboard")
async def get_analytics_dashboard(
    days: Optional[int] = 30,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive analytics dashboard data.

    Returns key metrics, trends, and visualizations for the specified time period.

    Query params:
    - days: Time period for analytics (default 30, options: 7, 30, 90, 365)

    **Requires authentication.**
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from collections import Counter

    try:
        # Calculate date range
        now = datetime.utcnow()
        start_date = now - timedelta(days=days)

        # Get user's territories
        territories = db.query(Territory).filter(Territory.user_id == user["user_id"]).all()
        territory_states = [t.state for t in territories] if territories else None

        # Base query for user's leads
        base_query = (
            db.query(Lead)
            .join(Scan, Lead.scan_id == Scan.id)
            .filter(
                Scan.user_id == user["user_id"],
                Lead.first_seen >= start_date
            )
        )

        # Filter by territories
        if territory_states:
            base_query = base_query.filter(Lead.state.in_(territory_states))

        all_leads = base_query.all()

        # === OVERVIEW METRICS ===
        total_leads = len(all_leads)
        hot_leads = sum(1 for l in all_leads if l.lead_type == "hot")
        warm_leads = sum(1 for l in all_leads if l.lead_type == "warm")
        cold_leads = sum(1 for l in all_leads if l.lead_type == "cold")
        urgent_leads = sum(1 for l in all_leads if l.urgency_score >= 60)

        # === LEAD TYPE DISTRIBUTION ===
        lead_distribution = {
            "hot": hot_leads,
            "warm": warm_leads,
            "cold": cold_leads,
        }

        # === CUSTOMER STATUS BREAKDOWN ===
        existing_customers = sum(1 for l in all_leads if l.customer_status == "existing_customer")
        new_opportunities = sum(1 for l in all_leads if l.customer_status == "new_opportunity")

        # === SOURCE TYPE BREAKDOWN ===
        source_counts = Counter(l.source_type for l in all_leads)
        source_distribution = dict(source_counts.most_common())

        # === TERRITORY BREAKDOWN ===
        territory_counts = Counter(l.state for l in all_leads)
        territory_distribution = [
            {"state": state, "count": count}
            for state, count in territory_counts.most_common(10)
        ]

        # === URGENCY DISTRIBUTION ===
        urgency_buckets = {
            "critical": sum(1 for l in all_leads if l.urgency_score >= 80),
            "high": sum(1 for l in all_leads if 60 <= l.urgency_score < 80),
            "medium": sum(1 for l in all_leads if 40 <= l.urgency_score < 60),
            "low": sum(1 for l in all_leads if l.urgency_score < 40),
        }

        # === DECISION STAGE DISTRIBUTION ===
        decision_stage_counts = Counter(l.decision_stage for l in all_leads if l.decision_stage and l.decision_stage != "unknown")
        decision_stages = dict(decision_stage_counts)

        # === COMPETITOR INTELLIGENCE ===
        all_competitors = []
        for lead in all_leads:
            if lead.competitors_mentioned:
                all_competitors.extend(lead.competitors_mentioned)
        competitor_counts = Counter(all_competitors)
        top_competitors = [
            {"name": comp, "count": count}
            for comp, count in competitor_counts.most_common(10)
        ]

        existing_vendor_counts = Counter(l.existing_vendor for l in all_leads if l.existing_vendor)
        existing_vendors = [
            {"name": vendor, "count": count}
            for vendor, count in existing_vendor_counts.most_common(10)
        ]

        # === TIME SERIES DATA (daily aggregation) ===
        # Group leads by date
        from datetime import date
        leads_by_date = {}
        for lead in all_leads:
            lead_date = lead.first_seen.date() if lead.first_seen else date.today()
            date_str = lead_date.isoformat()
            if date_str not in leads_by_date:
                leads_by_date[date_str] = {"hot": 0, "warm": 0, "cold": 0, "total": 0}
            leads_by_date[date_str][lead.lead_type] += 1
            leads_by_date[date_str]["total"] += 1

        # Fill in missing dates with zeros
        time_series = []
        current_date = start_date.date()
        end_date = now.date()
        while current_date <= end_date:
            date_str = current_date.isoformat()
            time_series.append({
                "date": date_str,
                "hot": leads_by_date.get(date_str, {}).get("hot", 0),
                "warm": leads_by_date.get(date_str, {}).get("warm", 0),
                "cold": leads_by_date.get(date_str, {}).get("cold", 0),
                "total": leads_by_date.get(date_str, {}).get("total", 0),
            })
            current_date += timedelta(days=1)

        # === PIPELINE METRICS (ROI) ===
        pipeline_counts = Counter(l.status for l in all_leads if hasattr(l, 'status'))
        pipeline_distribution = dict(pipeline_counts)

        # Total revenue from won deals
        total_revenue = sum(l.deal_value for l in all_leads if hasattr(l, 'deal_value') and l.deal_value)

        # Average deal size
        won_deals = [l.deal_value for l in all_leads if hasattr(l, 'status') and l.status == "won" and hasattr(l, 'deal_value') and l.deal_value]
        avg_deal_size = round(sum(won_deals) / len(won_deals)) if won_deals else 0

        # === POPULATION DISTRIBUTION ===
        population_buckets = {
            "small": sum(1 for l in all_leads if l.population < 10000),
            "small_mid": sum(1 for l in all_leads if 10000 <= l.population < 25000),
            "mid": sum(1 for l in all_leads if 25000 <= l.population < 50000),
            "large": sum(1 for l in all_leads if l.population >= 50000),
        }

        # === SCORE DISTRIBUTION ===
        score_buckets = {
            "excellent": sum(1 for l in all_leads if l.relevance_score >= 80),
            "good": sum(1 for l in all_leads if 60 <= l.relevance_score < 80),
            "fair": sum(1 for l in all_leads if 40 <= l.relevance_score < 60),
            "low": sum(1 for l in all_leads if l.relevance_score < 40),
        }

        # === DEADLINE ANALYSIS ===
        critical_deadlines = sum(1 for l in all_leads if l.days_until_deadline and l.days_until_deadline < 7)
        approaching_deadlines = sum(1 for l in all_leads if l.days_until_deadline and 7 <= l.days_until_deadline <= 30)
        future_deadlines = sum(1 for l in all_leads if l.days_until_deadline and l.days_until_deadline > 30)

        # === SCAN HISTORY ===
        recent_scans = (
            db.query(Scan)
            .filter(
                Scan.user_id == user["user_id"],
                Scan.created_at >= start_date
            )
            .order_by(Scan.created_at.desc())
            .limit(10)
            .all()
        )

        scan_history = [
            {
                "id": scan.id,
                "created_at": scan.created_at.isoformat(),
                "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
                "status": scan.status,
                "stats": scan.stats_json,
            }
            for scan in recent_scans
        ]

        return {
            "period": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
            },
            "overview": {
                "total_leads": total_leads,
                "hot_leads": hot_leads,
                "warm_leads": warm_leads,
                "cold_leads": cold_leads,
                "urgent_leads": urgent_leads,
                "existing_customers": existing_customers,
                "new_opportunities": new_opportunities,
            },
            "distributions": {
                "lead_types": lead_distribution,
                "source_types": source_distribution,
                "urgency_levels": urgency_buckets,
                "decision_stages": decision_stages,
                "population_sizes": population_buckets,
                "relevance_scores": score_buckets,
            },
            "competitors": {
                "top_competitors": top_competitors,
                "existing_vendors": existing_vendors,
                "total_competitive_situations": len(all_competitors),
            },
            "territories": territory_distribution,
            "deadlines": {
                "critical": critical_deadlines,
                "approaching": approaching_deadlines,
                "future": future_deadlines,
            },
            "pipeline": {
                "distribution": pipeline_distribution,
                "total_revenue": total_revenue,
                "avg_deal_size": avg_deal_size,
                "won_count": pipeline_distribution.get("won", 0),
            },
            "time_series": time_series,
            "recent_scans": scan_history,
        }

    except Exception as e:
        logger.error(f"Error generating analytics dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leads/{lead_id}/details")
async def get_lead_details(
    lead_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive details for a single lead.

    Returns everything needed for a detailed lead view:
    - Full lead information
    - Signal analysis breakdown
    - Temporal intelligence
    - Competitor intelligence
    - Municipality context
    - Related leads from same municipality
    - Activity timeline
    - Recommended actions

    **Requires authentication and scan ownership.**
    """
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

    # Get municipality info
    municipality = db.query(Municipality).filter(
        Municipality.name == lead.municipality,
        Municipality.state == lead.state
    ).first()

    # Get related leads from same municipality (last 90 days)
    from datetime import datetime, timedelta
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)

    related_leads = (
        db.query(Lead)
        .join(Scan, Lead.scan_id == Scan.id)
        .filter(
            Scan.user_id == user["user_id"],
            Lead.municipality == lead.municipality,
            Lead.state == lead.state,
            Lead.id != lead_id,
            Lead.first_seen >= ninety_days_ago
        )
        .order_by(Lead.first_seen.desc())
        .limit(5)
        .all()
    )

    # Get scan details
    scan_info = {
        "id": scan.id,
        "created_at": scan.created_at.isoformat(),
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "config": scan.config_json,
    }

    # Parse signal matches for detailed breakdown
    signal_breakdown = []
    if lead.signal_matches_json:
        for signal_type, signal_data in lead.signal_matches_json.items():
            signal_breakdown.append({
                "type": signal_type,
                "keyword": signal_data.get("keyword", ""),
                "context": signal_data.get("context", ""),
                "weight": signal_data.get("weight", 0),
            })

    # Build competitive analysis
    competitive_analysis = None
    if lead.competitors_mentioned or lead.existing_vendor:
        competitive_analysis = {
            "competitors_mentioned": lead.competitors_mentioned if hasattr(lead, 'competitors_mentioned') else [],
            "existing_vendor": lead.existing_vendor if hasattr(lead, 'existing_vendor') else None,
            "competitive_context": lead.competitive_context if hasattr(lead, 'competitive_context') else "",
            "is_displacement_opportunity": bool(lead.existing_vendor),
        }

    # Build temporal intelligence
    temporal_intel = {
        "urgency_score": lead.urgency_score if lead.urgency_score else 0,
        "urgency_label": (
            "Critical" if lead.urgency_score >= 80 else
            "High" if lead.urgency_score >= 60 else
            "Medium" if lead.urgency_score >= 40 else
            "Low"
        ),
        "deadline_date": lead.deadline_date.isoformat() if lead.deadline_date else None,
        "days_until_deadline": lead.days_until_deadline,
        "deadline_status": (
            "Urgent - Action Required" if lead.days_until_deadline and lead.days_until_deadline < 7 else
            "Approaching - Plan Now" if lead.days_until_deadline and lead.days_until_deadline < 30 else
            "Future - Monitor" if lead.days_until_deadline else
            "No Deadline"
        ),
        "decision_stage": lead.decision_stage if lead.decision_stage else "unknown",
        "fiscal_year": lead.fiscal_year,
    }

    # Build ROI/status info
    roi_info = {
        "status": lead.status if hasattr(lead, 'status') else "new",
        "deal_value": lead.deal_value if hasattr(lead, 'deal_value') else None,
        "contacted_date": lead.contacted_date.isoformat() if hasattr(lead, 'contacted_date') and lead.contacted_date else None,
        "won_date": lead.won_date.isoformat() if hasattr(lead, 'won_date') and lead.won_date else None,
        "lost_reason": lead.lost_reason if hasattr(lead, 'lost_reason') else None,
    }

    # Build activity timeline
    timeline = [
        {
            "date": lead.first_seen.isoformat() if lead.first_seen else None,
            "event": "Lead Discovered",
            "description": f"Found via {lead.source_type.replace('_', ' ').title()}",
        }
    ]

    if lead.times_seen > 1:
        timeline.append({
            "date": lead.last_seen.isoformat() if lead.last_seen else None,
            "event": "Lead Re-discovered",
            "description": f"Seen {lead.times_seen} times total",
        })

    if hasattr(lead, 'contacted_date') and lead.contacted_date:
        timeline.append({
            "date": lead.contacted_date.isoformat(),
            "event": "First Contact",
            "description": "Sales outreach initiated",
        })

    if hasattr(lead, 'won_date') and lead.won_date:
        timeline.append({
            "date": lead.won_date.isoformat(),
            "event": "Deal Won",
            "description": f"${lead.deal_value:,}" if lead.deal_value else "Deal closed",
        })

    # Sort timeline by date
    timeline.sort(key=lambda x: x["date"] if x["date"] else "", reverse=True)

    # Build municipality context
    municipality_context = None
    if municipality:
        municipality_context = {
            "name": municipality.name,
            "state": municipality.state,
            "population": municipality.population,
            "domain": municipality.resolved_url or municipality.domain,
            "domain_status": municipality.domain_status,
        }

    # Format related leads
    related_leads_formatted = [
        {
            "id": rl.id,
            "title": rl.title,
            "date": rl.date,
            "lead_type": rl.lead_type,
            "relevance_score": rl.relevance_score,
            "urgency_score": rl.urgency_score if rl.urgency_score else 0,
            "first_seen": rl.first_seen.isoformat() if rl.first_seen else None,
        }
        for rl in related_leads
    ]

    return {
        "lead": {
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
            "notes": lead.notes,
            "first_seen": lead.first_seen.isoformat() if lead.first_seen else None,
            "last_seen": lead.last_seen.isoformat() if lead.last_seen else None,
            "times_seen": lead.times_seen if lead.times_seen else 1,
        },
        "scan": scan_info,
        "signal_analysis": {
            "total_signals": len(signal_breakdown),
            "signals": signal_breakdown,
        },
        "temporal_intelligence": temporal_intel,
        "competitive_analysis": competitive_analysis,
        "roi_tracking": roi_info,
        "timeline": timeline,
        "municipality": municipality_context,
        "related_leads": {
            "count": len(related_leads_formatted),
            "leads": related_leads_formatted,
        },
    }


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


@app.get("/api/cache-stats")
async def get_cache_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return cache performance statistics.

    Shows cache size, hit rate, top cached municipalities, and expired entries.
    Helps monitor cache effectiveness and database health.
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta

    # Total cache entries
    total_cached = db.query(func.count(CachedDocument.id)).scalar()

    # Active (non-expired) cache entries
    active_cached = db.query(func.count(CachedDocument.id)).filter(
        CachedDocument.expires_at > datetime.utcnow()
    ).scalar()

    # Expired cache entries
    expired_cached = total_cached - active_cached

    # Total cache hits
    total_hits = db.query(func.sum(CachedDocument.hit_count)).scalar() or 0

    # Average hits per cached document
    avg_hits = total_hits / total_cached if total_cached > 0 else 0

    # Top cached municipalities (by hit count)
    top_cached = db.query(
        CachedDocument.municipality_name,
        CachedDocument.state,
        func.sum(CachedDocument.hit_count).label("total_hits")
    ).group_by(
        CachedDocument.municipality_name,
        CachedDocument.state
    ).order_by(
        func.sum(CachedDocument.hit_count).desc()
    ).limit(10).all()

    # Cache by state distribution
    by_state = db.query(
        CachedDocument.state,
        func.count(CachedDocument.id).label("count")
    ).group_by(
        CachedDocument.state
    ).order_by(
        func.count(CachedDocument.id).desc()
    ).limit(10).all()

    # Recent cache additions (last 24 hours)
    recent_cutoff = datetime.utcnow() - timedelta(days=1)
    recent_additions = db.query(func.count(CachedDocument.id)).filter(
        CachedDocument.scraped_at >= recent_cutoff
    ).scalar()

    return {
        "overview": {
            "total_cached": total_cached,
            "active_cached": active_cached,
            "expired_cached": expired_cached,
            "total_hits": total_hits,
            "avg_hits_per_doc": round(avg_hits, 2),
            "recent_additions_24h": recent_additions
        },
        "top_municipalities": [
            {
                "municipality": m.municipality_name,
                "state": m.state,
                "hits": m.total_hits
            }
            for m in top_cached
        ],
        "by_state": [
            {
                "state": s.state,
                "cached_count": s.count
            }
            for s in by_state
        ]
    }


@app.get("/api/notifications/settings")
async def get_notification_settings(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's notification preferences."""
    user_record = db.query(User).filter(User.id == user["user_id"]).first()

    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "email_alerts_enabled": bool(user_record.email_alerts_enabled),
        "alert_on_hot_leads": bool(user_record.alert_on_hot_leads),
        "alert_on_urgent_leads": bool(user_record.alert_on_urgent_leads),
        "daily_digest_enabled": bool(user_record.daily_digest_enabled),
        "min_urgency_for_alert": user_record.min_urgency_for_alert
    }


@app.patch("/api/notifications/settings")
async def update_notification_settings(
    settings: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update notification preferences.

    Body params (all optional):
    - email_alerts_enabled: bool
    - alert_on_hot_leads: bool
    - alert_on_urgent_leads: bool
    - daily_digest_enabled: bool
    - min_urgency_for_alert: int (0-100)
    """
    user_record = db.query(User).filter(User.id == user["user_id"]).first()

    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    # Update settings
    if "email_alerts_enabled" in settings:
        user_record.email_alerts_enabled = 1 if settings["email_alerts_enabled"] else 0

    if "alert_on_hot_leads" in settings:
        user_record.alert_on_hot_leads = 1 if settings["alert_on_hot_leads"] else 0

    if "alert_on_urgent_leads" in settings:
        user_record.alert_on_urgent_leads = 1 if settings["alert_on_urgent_leads"] else 0

    if "daily_digest_enabled" in settings:
        user_record.daily_digest_enabled = 1 if settings["daily_digest_enabled"] else 0

    if "min_urgency_for_alert" in settings:
        urgency = int(settings["min_urgency_for_alert"])
        if 0 <= urgency <= 100:
            user_record.min_urgency_for_alert = urgency

    db.commit()

    return {
        "success": True,
        "settings": {
            "email_alerts_enabled": bool(user_record.email_alerts_enabled),
            "alert_on_hot_leads": bool(user_record.alert_on_hot_leads),
            "alert_on_urgent_leads": bool(user_record.alert_on_urgent_leads),
            "daily_digest_enabled": bool(user_record.daily_digest_enabled),
            "min_urgency_for_alert": user_record.min_urgency_for_alert
        }
    }


@app.post("/api/send-weekly-digest")
async def send_weekly_digest_endpoint(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate and send weekly digest email for the current user.

    This would typically be called by a cron job/scheduler, but can also
    be manually triggered for testing or on-demand reports.

    Requires authentication.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from collections import Counter

    try:
        user_email = user["email"]

        # Get user's territories
        territories = db.query(Territory).filter(Territory.user_id == user["user_id"]).all()
        territory_states = [t.state for t in territories] if territories else None

        # Calculate date ranges
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        # Query this week's leads
        this_week_query = (
            db.query(Lead)
            .join(Scan, Lead.scan_id == Scan.id)
            .filter(
                Scan.user_id == user["user_id"],
                Scan.completed_at >= week_ago,
                Scan.completed_at <= now,
                Lead.times_seen == 1  # Only new leads
            )
        )

        # Filter by territories if exist
        if territory_states:
            this_week_query = this_week_query.filter(Lead.state.in_(territory_states))

        this_week_leads = this_week_query.all()

        # Query previous week's leads for trend comparison
        prev_week_count = (
            db.query(Lead)
            .join(Scan, Lead.scan_id == Scan.id)
            .filter(
                Scan.user_id == user["user_id"],
                Scan.completed_at >= two_weeks_ago,
                Scan.completed_at < week_ago,
                Lead.times_seen == 1
            )
        )
        if territory_states:
            prev_week_count = prev_week_count.filter(Lead.state.in_(territory_states))
        prev_week_total = prev_week_count.count()

        # Calculate stats
        total_leads = len(this_week_leads)
        hot_leads = sum(1 for l in this_week_leads if l.lead_type == "hot")
        warm_leads = sum(1 for l in this_week_leads if l.lead_type == "warm")
        cold_leads = sum(1 for l in this_week_leads if l.lead_type == "cold")
        urgent_leads = sum(1 for l in this_week_leads if l.urgency_score >= 60)

        # Deadline analysis
        critical_deadlines = sum(1 for l in this_week_leads if l.days_until_deadline and l.days_until_deadline < 7)
        approaching_deadlines = sum(1 for l in this_week_leads if l.days_until_deadline and 7 <= l.days_until_deadline <= 30)

        # Competitor analysis
        all_competitors = []
        for lead in this_week_leads:
            if lead.competitors_mentioned:
                all_competitors.extend(lead.competitors_mentioned)

        competitor_counts = Counter(all_competitors)
        total_unique_competitors = len(competitor_counts)
        top_competitors = competitor_counts.most_common(5)  # [(vendor, count), ...]

        # Territory breakdown
        territory_counts = Counter(l.state for l in this_week_leads)

        # Top leads (by relevance score)
        top_leads = sorted(this_week_leads, key=lambda l: l.relevance_score, reverse=True)[:10]
        top_leads_dicts = [
            {
                "id": l.id,
                "municipality": l.municipality,
                "state": l.state,
                "title": l.title,
                "url": l.url,
                "relevance_score": l.relevance_score,
                "lead_type": l.lead_type,
                "urgency_score": l.urgency_score,
                "days_until_deadline": l.days_until_deadline,
                "decision_stage": l.decision_stage,
                "signal_matches": l.signal_matches_json,
            }
            for l in top_leads
        ]

        # Build weekly summary
        weekly_summary = {
            "total_leads": total_leads,
            "hot_leads": hot_leads,
            "warm_leads": warm_leads,
            "cold_leads": cold_leads,
            "urgent_leads": urgent_leads,
            "prev_week_total": prev_week_total,
            "critical_deadlines": critical_deadlines,
            "approaching_deadlines": approaching_deadlines,
            "competitor_summary": {
                "total_competitors": total_unique_competitors,
                "top_competitors": top_competitors,
            },
            "territory_breakdown": dict(territory_counts),
            "top_leads": top_leads_dicts,
        }

        # Send email
        from src.notifications import send_weekly_digest
        result = await send_weekly_digest(user_email, weekly_summary, territory_states)

        if result:
            return {
                "success": True,
                "message": f"Weekly digest sent to {user_email}",
                "email_id": result.get("id"),
                "summary": {
                    "total_leads": total_leads,
                    "hot_leads": hot_leads,
                    "urgent_leads": urgent_leads,
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send weekly digest")

    except Exception as e:
        logger.error(f"Error sending weekly digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    # Query section statuses and answers
    sections_result = db.execute(text("""
        SELECT "sectionNumber", status, answers
        FROM "AssessmentSection"
        WHERE "assessmentId" = :assessment_id
        ORDER BY "sectionNumber"
    """), {"assessment_id": assessment_id})

    section_data = {row[0]: {"status": row[1], "answers": json.loads(row[2]) if row[2] else {}} for row in sections_result.fetchall()}

    # Define total questions per section
    section_question_counts = {
        "1": 20,
        "2": 10,
        "3a": 10
    }

    # Build sections list with metadata and progress tracking
    sections = []
    for section_num in ["1", "2", "3a"]:
        data = section_data.get(section_num, {"status": "not-started", "answers": {}})
        status = data["status"]
        answers = data["answers"]

        # Calculate question-level progress
        total_questions = section_question_counts.get(section_num, 0)
        answered_questions = len([v for v in answers.values() if v not in [None, "", []]])

        # Determine effective status (upgrade "not-started" to "in-progress" if answers exist)
        if status == "not-started" and answered_questions > 0:
            status = "in-progress"

        section_config = {
            "1": {
                "title": "Organization Profile",
                "description": "Tell us about your municipality and current systems",
                "estimated_minutes": 10,
                "locked": False
            },
            "2": {
                "title": "General Ledger & Chart of Accounts",
                "description": "Assess your GL structure and identify optimization opportunities",
                "estimated_minutes": 7,
                "locked": section_data.get("1", {}).get("status") != "completed",
                "requires": "1"
            },
            "3a": {
                "title": "Payroll & Pay Codes",
                "description": "Document your current pay codes and structure",
                "estimated_minutes": 15,
                "locked": section_data.get("1", {}).get("status") != "completed",
                "requires": "1"
            }
        }

        config = section_config.get(section_num, {})
        sections.append({
            "number": section_num,
            "title": config.get("title", f"Section {section_num}"),
            "description": config.get("description", ""),
            "status": status,
            "locked": config.get("locked", False),
            "requires": config.get("requires"),
            "estimated_minutes": config.get("estimated_minutes", 10),
            "questions_answered": answered_questions,
            "questions_total": total_questions,
            "progress_text": f"{answered_questions} of {total_questions} questions" if answered_questions > 0 and status != "completed" else None
        })

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


@app.get("/api/admin/downloads")
async def get_admin_downloads(
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """
    Get all playbook downloads for admin portal.

    Returns list of downloads with email, name, title, municipality, and download timestamp.
    """
    try:
        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS resource_downloads (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT,
                title TEXT,
                municipality TEXT,
                resource_name TEXT NOT NULL,
                downloaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                user_agent TEXT,
                ip_address TEXT
            )
        """))
        db.commit()

        # Get all downloads, most recent first
        result = db.execute(text("""
            SELECT
                id,
                email,
                name,
                title,
                municipality,
                resource_name,
                downloaded_at,
                ip_address
            FROM resource_downloads
            ORDER BY downloaded_at DESC
        """))

        downloads = []
        for row in result:
            downloads.append({
                "id": row[0],
                "email": row[1],
                "name": row[2],
                "title": row[3],
                "municipality": row[4],
                "resource_name": row[5],
                "downloaded_at": row[6].isoformat() if row[6] else None,
                "ip_address": row[7]
            })

        return {
            "downloads": downloads,
            "total": len(downloads)
        }
    except Exception as e:
        print(f"Error fetching downloads: {e}")
        return {
            "downloads": [],
            "total": 0
        }


@app.get("/assessment/start", response_class=HTMLResponse)
async def start_anonymous_assessment(
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Start anonymous assessment - no authentication required.
    Generates a temporary session ID and returns assessment dashboard in anonymous mode.
    Data will be stored in localStorage until user creates account.
    """
    # If user is already logged in, redirect to normal assessment creation
    if user:
        return RedirectResponse(url="/app", status_code=302)

    # Generate anonymous session ID
    anon_id = f"anon-{str(_uuid.uuid4())}"

    # Build sections list (same as authenticated flow but no database check)
    sections = [
        {
            "number": "1",
            "title": "Organization Profile",
            "description": "Tell us about your municipality and current systems",
            "status": "not-started",
            "locked": False,
            "estimated_minutes": 10
        },
        {
            "number": "2",
            "title": "General Ledger & Chart of Accounts",
            "description": "Assess your GL structure and identify optimization opportunities",
            "status": "not-started",
            "locked": True,  # Will unlock after section 1
            "requires": "1",
            "estimated_minutes": 7
        },
        {
            "number": "3a",
            "title": "Pay Code Inventory",
            "description": "Document your current pay codes and structure",
            "status": "not-started",
            "locked": True,  # Will unlock after section 1
            "requires": "1",
            "estimated_minutes": 15
        }
    ]

    return templates.TemplateResponse("assessment_dashboard.html", {
        "request": request,
        "user": None,  # No user for anonymous
        "assessment_id": anon_id,
        "sections": sections,
        "overall_progress": 0,
        "completed_count": 0,
        "total_sections": len(sections),
        "estimated_time": sum(s["estimated_minutes"] for s in sections),
        "anonymous": True  # Flag for template to handle localStorage
    })


@app.get("/assessment/{assessment_id}/results", response_class=HTMLResponse)
async def assessment_results(
    assessment_id: str,
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Assessment results page.
    For anonymous users: Shows full report WITHOUT AI insights + upsell prompt.
    For authenticated users: Shows full report WITH AI insights.
    """
    is_anonymous = assessment_id.startswith("anon-")

    # For authenticated users, verify ownership
    if not is_anonymous and not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    return templates.TemplateResponse("assessment_results.html", {
        "request": request,
        "user": user,
        "assessment_id": assessment_id,
        "anonymous": is_anonymous
    })


@app.get("/assessment/{assessment_id}/section/{section_number}", response_class=HTMLResponse)
async def assessment_section(
    assessment_id: str,
    section_number: str,
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Render a specific assessment section - supports both authenticated and anonymous users."""
    print(f"=== LOAD SECTION DEBUG ===")
    print(f"Assessment ID: {assessment_id}")
    print(f"Section: {section_number}")
    print(f"User: {user.get('user_id') if user else 'None (anonymous)'}")

    # Check if this is an anonymous assessment
    is_anonymous = assessment_id.startswith("anon-")
    print(f"Is anonymous: {is_anonymous}")

    if not is_anonymous:
        # Authenticated assessment - verify user owns it
        if not user:
            print("ERROR: No user session found for authenticated assessment")
            raise HTTPException(status_code=401, detail="Authentication required")

        result = db.execute(text("""
            SELECT id FROM "Assessment"
            WHERE id = :id AND "userId" = :user_id
        """), {"id": assessment_id, "user_id": user["user_id"]})

        assessment_row = result.fetchone()
        if not assessment_row:
            print(f"ERROR: Assessment not found when loading section. ID={assessment_id}, UserID={user['user_id']}")
            raise HTTPException(status_code=404, detail="Assessment not found")

        print(f"✓ Assessment verified for user")

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
            "title": "Payroll & Pay Codes",
            "description": "Assess payroll complexity and pay code management",
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

    return templates.TemplateResponse("assessment_wizard.html", {
        "request": request,
        "user": user,
        "assessment_id": assessment_id,
        "section_number": section_number,
        "section_title": meta["title"],
        "section_description": meta["description"],
        "section_script": section_script,
        "anonymous": is_anonymous  # Flag for localStorage handling
    })


def generate_section1_script():
    """Generate Section 1: Organization Profile - Complete (20 questions)."""
    return f"""
// Section 1: Organization Profile - Complete (Q1-Q20)
// Group 1: Identity & Scale (Q1-Q4)
// Group 2: Operational Footprint (Q5-Q10)
// Group 3: Current Systems (Q11-Q15)
// Group 4: Change Readiness (Q16-Q20)

const STATES_FULL = [
  {{ value: 'AL', label: 'Alabama' }},
  {{ value: 'AK', label: 'Alaska' }},
  {{ value: 'AZ', label: 'Arizona' }},
  {{ value: 'AR', label: 'Arkansas' }},
  {{ value: 'CA', label: 'California' }},
  {{ value: 'CO', label: 'Colorado' }},
  {{ value: 'CT', label: 'Connecticut' }},
  {{ value: 'DE', label: 'Delaware' }},
  {{ value: 'FL', label: 'Florida' }},
  {{ value: 'GA', label: 'Georgia' }},
  {{ value: 'HI', label: 'Hawaii' }},
  {{ value: 'ID', label: 'Idaho' }},
  {{ value: 'IL', label: 'Illinois' }},
  {{ value: 'IN', label: 'Indiana' }},
  {{ value: 'IA', label: 'Iowa' }},
  {{ value: 'KS', label: 'Kansas' }},
  {{ value: 'KY', label: 'Kentucky' }},
  {{ value: 'LA', label: 'Louisiana' }},
  {{ value: 'ME', label: 'Maine' }},
  {{ value: 'MD', label: 'Maryland' }},
  {{ value: 'MA', label: 'Massachusetts' }},
  {{ value: 'MI', label: 'Michigan' }},
  {{ value: 'MN', label: 'Minnesota' }},
  {{ value: 'MS', label: 'Mississippi' }},
  {{ value: 'MO', label: 'Missouri' }},
  {{ value: 'MT', label: 'Montana' }},
  {{ value: 'NE', label: 'Nebraska' }},
  {{ value: 'NV', label: 'Nevada' }},
  {{ value: 'NH', label: 'New Hampshire' }},
  {{ value: 'NJ', label: 'New Jersey' }},
  {{ value: 'NM', label: 'New Mexico' }},
  {{ value: 'NY', label: 'New York' }},
  {{ value: 'NC', label: 'North Carolina' }},
  {{ value: 'ND', label: 'North Dakota' }},
  {{ value: 'OH', label: 'Ohio' }},
  {{ value: 'OK', label: 'Oklahoma' }},
  {{ value: 'OR', label: 'Oregon' }},
  {{ value: 'PA', label: 'Pennsylvania' }},
  {{ value: 'RI', label: 'Rhode Island' }},
  {{ value: 'SC', label: 'South Carolina' }},
  {{ value: 'SD', label: 'South Dakota' }},
  {{ value: 'TN', label: 'Tennessee' }},
  {{ value: 'TX', label: 'Texas' }},
  {{ value: 'UT', label: 'Utah' }},
  {{ value: 'VT', label: 'Vermont' }},
  {{ value: 'VA', label: 'Virginia' }},
  {{ value: 'WA', label: 'Washington' }},
  {{ value: 'WV', label: 'West Virginia' }},
  {{ value: 'WI', label: 'Wisconsin' }},
  {{ value: 'WY', label: 'Wyoming' }},
  {{ value: 'DC', label: 'District of Columbia' }}
];

const ENTITY_TYPES = [
  {{ value: 'city', label: 'City' }},
  {{ value: 'town', label: 'Town' }},
  {{ value: 'county', label: 'County' }},
  {{ value: 'village', label: 'Village' }},
  {{ value: 'borough', label: 'Borough' }},
  {{ value: 'special_district', label: 'Special District' }},
  {{ value: 'tribal_government', label: 'Tribal Government' }},
  {{ value: 'school_district', label: 'School District' }},
  {{ value: 'regional_authority', label: 'Regional Authority' }},
  {{ value: 'other', label: 'Other' }}
];

const GOVERNANCE_STRUCTURES = [
  {{ value: 'mayor_council_executive', label: 'Mayor-Council (Executive Mayor)' }},
  {{ value: 'mayor_council_ceremonial', label: 'Mayor-Council (Ceremonial Mayor)' }},
  {{ value: 'council_manager', label: 'Council-Manager' }},
  {{ value: 'commission', label: 'Commission' }},
  {{ value: 'town_meeting', label: 'Town Meeting' }},
  {{ value: 'other', label: 'Other' }}
];

const ERP_SYSTEMS = [
  {{ value: 'caselle_clarity', label: 'Caselle Clarity' }},
  {{ value: 'caselle_windows', label: 'Caselle Windows' }},
  {{ value: 'tyler_munis', label: 'Tyler Munis/ERP Pro' }},
  {{ value: 'tyler_incode', label: 'Tyler Incode' }},
  {{ value: 'edmunds_govtech', label: 'Edmunds GovTech' }},
  {{ value: 'bsa', label: 'BS&A' }},
  {{ value: 'springbrook', label: 'Springbrook' }},
  {{ value: 'centralsquare', label: 'Central Square (HTE/Superion)' }},
  {{ value: 'sap', label: 'SAP' }},
  {{ value: 'oracle', label: 'Oracle' }},
  {{ value: 'quickbooks', label: 'QuickBooks' }},
  {{ value: 'sage', label: 'Sage/MAS' }},
  {{ value: 'accufund', label: 'AccuFund' }},
  {{ value: 'sungard', label: 'SunGard/Infor' }},
  {{ value: 'custom', label: 'Custom/Homegrown System' }},
  {{ value: 'spreadsheets', label: 'Spreadsheets/Manual' }},
  {{ value: 'other', label: 'Other (please specify in notes)' }}
];

const PAYROLL_SYSTEMS = [
  {{ value: 'integrated_erp', label: 'Same as ERP (integrated)' }},
  {{ value: 'adp', label: 'ADP' }},
  {{ value: 'paychex', label: 'Paychex' }},
  {{ value: 'paycom', label: 'Paycom' }},
  {{ value: 'paylocity', label: 'Paylocity' }},
  {{ value: 'ukg_kronos', label: 'UKG/Kronos' }},
  {{ value: 'tyler_standalone', label: 'Tyler (standalone)' }},
  {{ value: 'ceridian', label: 'Ceridian/Dayforce' }},
  {{ value: 'custom', label: 'Custom/In-house' }},
  {{ value: 'outsourced', label: 'Outsourced to county/third party' }},
  {{ value: 'other', label: 'Other (please specify in notes)' }}
];

const SERVICES = [
  {{ value: 'water', label: 'Water' }},
  {{ value: 'wastewater', label: 'Wastewater/Sewer' }},
  {{ value: 'stormwater', label: 'Stormwater' }},
  {{ value: 'electric', label: 'Electric Utility' }},
  {{ value: 'gas', label: 'Gas Utility' }},
  {{ value: 'solid_waste', label: 'Solid Waste/Recycling' }},
  {{ value: 'building_permits', label: 'Building Permits & Inspections' }},
  {{ value: 'planning_zoning', label: 'Planning & Zoning' }},
  {{ value: 'code_enforcement', label: 'Code Enforcement' }},
  {{ value: 'municipal_court', label: 'Municipal Court' }},
  {{ value: 'police', label: 'Police Services' }},
  {{ value: 'fire', label: 'Fire Services' }},
  {{ value: 'ems', label: 'EMS/Ambulance' }},
  {{ value: 'parks_rec', label: 'Parks & Recreation' }},
  {{ value: 'library', label: 'Library' }},
  {{ value: 'public_works', label: 'Public Works/Streets' }},
  {{ value: 'transit', label: 'Public Transit' }},
  {{ value: 'airport', label: 'Airport' }},
  {{ value: 'cemetery', label: 'Cemetery' }},
  {{ value: 'animal_control', label: 'Animal Control' }}
];

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

// Define wizard questions
questions = [
  {{
    id: 'q1_state',
    type: 'dropdown',
    text: 'Which state is your organization located in?',
    aiContext: "Let's start with the basics.",
    options: STATES_FULL,
    help: 'We need your state location to assess state-specific compliance requirements and benchmark you against similar municipalities.',
    required: true
  }},
  {{
    id: 'q2_entity_type',
    type: 'single-select',
    text: 'What type of government entity are you?',
    aiContext: 'This helps us tailor recommendations to your organizational structure.',
    options: ENTITY_TYPES,
    autoAdvance: false,
    required: true
  }},
  {{
    id: 'q3_population',
    type: 'single-select',
    text: 'What is the approximate population you serve?',
    aiContext: 'Population size is a key driver of system complexity.',
    help: 'Select the range that best matches your jurisdiction. This helps us understand your operational scale and compare you to similar municipalities.',
    options: [
      {{ value: 'under-5000', label: 'Under 5,000' }},
      {{ value: '5000-25000', label: '5,000 – 25,000' }},
      {{ value: '25000-100000', label: '25,000 – 100,000' }},
      {{ value: '100000-500000', label: '100,000 – 500,000' }},
      {{ value: 'over-500000', label: 'Over 500,000' }}
    ],
    required: true,
    autoAdvance: false
  }},
  {{
    id: 'q4_governance',
    type: 'single-select',
    text: 'What is your governance structure?',
    aiContext: 'Different governance models have different decision-making needs.',
    options: GOVERNANCE_STRUCTURES,
    autoAdvance: false,
    help: 'Your governance structure affects how financial decisions are made and who needs access to the ERP system.',
    required: true
  }},
  {{
    id: 'interstitial_group2',
    type: 'interstitial',
    text: 'Now let\\'s understand your operational scale.',
    aiContext: 'This helps us gauge your organization\\'s size and complexity.',
    required: false
  }},
  {{
    id: 'q5_employee_count',
    type: 'single-select',
    text: 'How many full-time employees does your organization have?',
    aiContext: 'Staffing levels help us understand your operational capacity.',
    help: 'Include all full-time equivalent (FTE) positions. Part-time staff can be counted as 0.5 FTE each.',
    options: [
      {{ value: 'under-25', label: 'Under 25' }},
      {{ value: '25-100', label: '25 – 100' }},
      {{ value: '100-500', label: '100 – 500' }},
      {{ value: '500-1000', label: '500 – 1,000' }},
      {{ value: 'over-1000', label: 'Over 1,000' }}
    ],
    autoAdvance: false,
    required: true
  }},
  {{
    id: 'q6_department_count',
    type: 'single-select',
    text: 'How many departments or divisions does your organization have?',
    aiContext: 'This helps us gauge your organizational complexity.',
    help: 'Count major organizational units like Police, Fire, Public Works, Finance, etc.',
    options: [
      {{ value: 'under-5', label: 'Under 5' }},
      {{ value: '5-10', label: '5 – 10' }},
      {{ value: '10-20', label: '10 – 20' }},
      {{ value: 'over-20', label: 'Over 20' }}
    ],
    autoAdvance: false,
    required: true
  }},
  {{
    id: 'q7_fund_count',
    type: 'single-select',
    text: 'How many funds does your organization manage?',
    aiContext: 'Fund structure is critical for proper financial reporting.',
    help: 'Include all governmental, proprietary, and fiduciary funds (General Fund, Special Revenue, Enterprise, etc.).',
    options: [
      {{ value: 'under-5', label: 'Under 5' }},
      {{ value: '5-10', label: '5 – 10' }},
      {{ value: '10-20', label: '10 – 20' }},
      {{ value: 'over-20', label: 'Over 20' }}
    ],
    autoAdvance: false,
    required: true
  }},
  {{
    id: 'q8_services',
    type: 'multi-select',
    text: 'Which services does your organization provide?',
    aiContext: 'Service mix drives system requirements and operational complexity.',
    options: SERVICES,
    help: 'Select all services your organization provides directly (not contracted out). This helps us understand billing, permitting, and operational needs. Utility services (water, wastewater, electric, gas, stormwater) indicate you likely need utility billing capabilities.',
    required: true
  }},
  {{
    id: 'q9_fiscal_year_end',
    type: 'dropdown',
    text: 'What is your fiscal year end month?',
    aiContext: 'Fiscal year timing affects reporting cycles.',
    options: MONTHS,
    help: 'Most municipalities use June 30 or December 31, but your state may require a different fiscal year.',
    required: true
  }},
  {{
    id: 'q10_annual_budget',
    type: 'single-select',
    text: 'What is your organization\\'s approximate annual budget?',
    aiContext: 'Budget size helps us understand your financial operations scale.',
    help: 'Include all appropriations across all funds. Select "Not sure" if you don\\'t know the exact amount.',
    options: [
      {{ value: 'under-1m', label: 'Under $1 million' }},
      {{ value: '1m-10m', label: '$1M – $10M' }},
      {{ value: '10m-50m', label: '$10M – $50M' }},
      {{ value: '50m-250m', label: '$50M – $250M' }},
      {{ value: 'over-250m', label: 'Over $250M' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    autoAdvance: false,
    required: false
  }},
  {{
    id: 'interstitial_group3',
    type: 'interstitial',
    text: 'Next, we\\'ll look at your current technology stack.',
    aiContext: 'Understanding your existing systems helps us recommend the right solution.',
    required: false
  }},
  {{
    id: 'q11_current_erp',
    type: 'dropdown',
    text: 'What ERP or accounting system do you currently use?',
    aiContext: 'Understanding your current system helps us identify migration challenges.',
    options: ERP_SYSTEMS,
    help: 'Select your primary financial/accounting software. If you use multiple systems, select the main one. Choose "Other" if your system isn\\'t listed.',
    required: true
  }},
  {{
    id: 'q12_current_payroll',
    type: 'dropdown',
    text: 'What payroll system do you currently use?',
    aiContext: 'Payroll integration is a key requirement for most municipalities.',
    options: PAYROLL_SYSTEMS,
    help: 'This could be the same as your ERP system, a separate software, or an outsourced service. Choose "Same as ERP (integrated)" if payroll is built into your accounting system.',
    required: false
  }},
  {{
    id: 'q13_system_count',
    type: 'single-select',
    text: 'Approximately how many different software systems does your organization use?',
    aiContext: 'System sprawl is a common municipal challenge.',
    options: [
      {{ value: '1-3', label: '1-3 systems' }},
      {{ value: '4-6', label: '4-6 systems' }},
      {{ value: '7-10', label: '7-10 systems' }},
      {{ value: '10+', label: 'More than 10 systems' }},
      {{ value: 'unknown', label: 'Not sure' }}
    ],
    autoAdvance: false,
    help: 'Include all major systems: ERP, payroll, utility billing, permitting, asset management, etc.',
    required: true
  }},
  {{
    id: 'q14_integration_issues',
    type: 'single-select',
    text: 'How well do your current systems integrate with each other?',
    aiContext: 'Integration gaps create manual work and data inconsistencies.',
    options: [
      {{ value: 'well_integrated', label: 'Well integrated - data flows automatically' }},
      {{ value: 'some_integration', label: 'Some integration - with manual steps' }},
      {{ value: 'mostly_manual', label: 'Mostly manual - lots of re-entering data' }},
      {{ value: 'completely_siloed', label: 'Completely siloed - no integration' }}
    ],
    autoAdvance: false,
    help: 'Think about how data moves between your accounting, payroll, utility billing, and other systems.',
    required: true
  }},
  {{
    id: 'q15_biggest_pain_point',
    type: 'text',
    text: 'What is your biggest system-related pain point right now?',
    aiContext: 'This helps us prioritize recommendations.',
    placeholder: 'e.g., manual data entry, slow month-end close, poor reporting, etc.',
    help: 'What takes the most time, causes the most frustration, or keeps you up at night?',
    required: false
  }},
  {{
    id: 'interstitial_group4',
    type: 'interstitial',
    text: 'Finally, let\\'s assess your readiness for change.',
    aiContext: 'These questions help us understand your timeline and organizational readiness.',
    required: false
  }},
  {{
    id: 'q16_timeline',
    type: 'single-select',
    text: 'What is your timeline for making a change?',
    aiContext: 'Timeline affects solution options and implementation approach.',
    options: [
      {{ value: 'urgent', label: 'Urgent - within 3-6 months' }},
      {{ value: 'this_year', label: 'This fiscal year' }},
      {{ value: 'next_year', label: 'Next fiscal year' }},
      {{ value: 'exploring', label: 'Just exploring - no specific timeline' }},
      {{ value: 'not_sure', label: 'Not sure yet' }}
    ],
    autoAdvance: false,
    help: 'This helps us understand urgency and recommend appropriate next steps.',
    required: true
  }},
  {{
    id: 'q17_budget_status',
    type: 'single-select',
    text: 'Do you have budget allocated or approved for new software?',
    aiContext: 'Budget readiness is a key factor in implementation planning.',
    options: [
      {{ value: 'approved', label: 'Yes - budget approved' }},
      {{ value: 'requested', label: 'Requested but not yet approved' }},
      {{ value: 'planning', label: 'Planning to request in next budget cycle' }},
      {{ value: 'no_budget', label: 'No budget discussions yet' }},
      {{ value: 'not_sure', label: 'Not sure' }}
    ],
    autoAdvance: false,
    required: true
  }},
  {{
    id: 'q18_internal_champion',
    type: 'single-select',
    text: 'Do you have an internal champion or project lead identified?',
    aiContext: 'Successful implementations need internal leadership.',
    options: [
      {{ value: 'yes', label: 'Yes - identified and committed' }},
      {{ value: 'potential', label: 'Potential person but not formalized' }},
      {{ value: 'no', label: 'Not yet' }}
    ],
    autoAdvance: false,
    help: 'An internal champion is someone who can drive the project, make decisions, and keep stakeholders aligned.',
    required: true
  }},
  {{
    id: 'q19_change_drivers',
    type: 'multi-select',
    text: 'What is driving your interest in new software? (Select all that apply)',
    aiContext: 'Understanding motivations helps us focus on what matters most.',
    options: [
      {{ value: 'outdated_system', label: 'Current system is outdated or unsupported' }},
      {{ value: 'compliance', label: 'Compliance or audit concerns' }},
      {{ value: 'efficiency', label: 'Need to improve efficiency and reduce manual work' }},
      {{ value: 'reporting', label: 'Better reporting and data visibility' }},
      {{ value: 'integration', label: 'Better system integration' }},
      {{ value: 'cost', label: 'Reduce operational costs' }},
      {{ value: 'staff_turnover', label: 'Staff turnover or knowledge loss concerns' }},
      {{ value: 'growth', label: 'Organization growth or service expansion' }},
      {{ value: 'council_mandate', label: 'Council or leadership mandate' }}
    ],
    help: 'Select all major factors driving your consideration of new software.',
    required: true
  }},
  {{
    id: 'q20_implementation_concerns',
    type: 'multi-select',
    text: 'What concerns do you have about implementing new software? (Select all that apply)',
    aiContext: 'Identifying concerns early helps us address them proactively.',
    options: [
      {{ value: 'cost', label: 'Cost and budget constraints' }},
      {{ value: 'disruption', label: 'Disruption to daily operations' }},
      {{ value: 'data_migration', label: 'Data migration and historical data' }},
      {{ value: 'staff_training', label: 'Staff training and adoption' }},
      {{ value: 'timeline', label: 'Implementation timeline' }},
      {{ value: 'vendor_selection', label: 'Choosing the right vendor' }},
      {{ value: 'customization', label: 'System customization needs' }},
      {{ value: 'integration', label: 'Integration with existing systems' }},
      {{ value: 'no_concerns', label: 'No major concerns' }}
    ],
    help: 'Select all that apply. This helps us provide targeted guidance.',
    required: false
  }}
];
"""


def generate_section2_script():
    """Generate Section 2: General Ledger & Chart of Accounts - Complete (6 questions)."""
    return f"""
// Section 2: General Ledger & Chart of Accounts - Complete (Q1-Q6)
// Wizard interface to assess COA structure and identify optimization opportunities

const questions = [
  // Q1: Account Code Count
  {{
    id: 'q1_account_count',
    type: 'dropdown',
    text: 'Approximately how many account codes does your organization use?',
    aiContext: 'Number of account codes in Chart of Accounts - helps identify COA bloat',
    help: 'Your Chart of Accounts (COA) is simply the list of all budget categories your organization uses to track money (like "Police Salaries" or "Park Maintenance"). Don\\'t worry if you\\'re not sure—just make your best estimate.',
    options: [
      {{ value: 'under-500', label: 'Under 500' }},
      {{ value: '500-1000', label: '500-1,000' }},
      {{ value: '1000-2000', label: '1,000-2,000' }},
      {{ value: '2000-5000', label: '2,000-5,000' }},
      {{ value: 'over-5000', label: 'Over 5,000' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q2: Last COA Review
  {{
    id: 'q2_last_review',
    type: 'dropdown',
    text: 'When did someone last conduct a comprehensive review of your Chart of Accounts to clean up old/unused codes?',
    aiContext: 'Frequency of COA maintenance - identifies risk of accumulated bloat',
    help: 'This would be a thorough review—not just adding a new account here and there, but actually going through the whole list to remove outdated codes or consolidate duplicates.',
    options: [
      {{ value: 'within-1-year', label: 'Within the last year' }},
      {{ value: '1-2-years', label: '1-2 years ago' }},
      {{ value: '2-5-years', label: '2-5 years ago' }},
      {{ value: '5-10-years', label: '5-10 years ago' }},
      {{ value: 'over-10-years', label: 'Over 10 years ago' }},
      {{ value: 'never', label: 'Never / Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q3: Inactive Account Percentage
  {{
    id: 'q3_inactive_percentage',
    type: 'dropdown',
    text: 'Roughly what percentage of your account codes had ZERO activity during your last fiscal year?',
    aiContext: 'Percentage of inactive accounts - key indicator of COA health',
    help: '"Inactive accounts" are budget codes that had no money go in or out during your last fiscal year. Having too many inactive accounts is a red flag that your chart could use cleanup. If you\\'re not sure, just make your best guess.',
    options: [
      {{ value: 'under-5', label: 'Under 5%' }},
      {{ value: '5-15', label: '5-15%' }},
      {{ value: '15-30', label: '15-30%' }},
      {{ value: '30-50', label: '30-50%' }},
      {{ value: 'over-50', label: 'Over 50%' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q4: Fund Count
  {{
    id: 'q4_fund_count',
    type: 'dropdown',
    text: 'How many different funds does your municipality operate?',
    aiContext: 'Number of funds - affects reporting complexity',
    help: 'Funds are separate "buckets" of money with their own accounting. Common examples: General Fund, Water/Sewer Fund, Parks Fund, Capital Improvement Fund, etc. Most municipalities have several funds to keep certain money separate.',
    options: [
      {{ value: '1-3', label: '1-3 funds' }},
      {{ value: '4-7', label: '4-7 funds' }},
      {{ value: '8-15', label: '8-15 funds' }},
      {{ value: 'over-15', label: 'Over 15 funds' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q5: Month-End Close Duration
  {{
    id: 'q5_month_close',
    type: 'dropdown',
    text: 'How many business days does it typically take to close the books each month?',
    aiContext: 'Month-end close duration - indicates process efficiency',
    help: '"Month-end close" is when your finance team reconciles accounts, posts adjusting entries, and closes the books for the previous month. A long close process often means complicated account structures or too many manual steps.',
    options: [
      {{ value: 'under-5-days', label: 'Under 5 business days' }},
      {{ value: '5-8-days', label: '5-8 business days' }},
      {{ value: '8-15-days', label: '8-15 business days' }},
      {{ value: 'over-15-days', label: 'Over 15 business days' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q6: Known COA Issues (Multi-Select)
  {{
    id: 'q6_known_issues',
    type: 'multi-select',
    text: 'Are you aware of any specific issues with your current Chart of Accounts?',
    aiContext: 'Known COA pain points reported by user',
    help: 'Select all that apply. If you\\'re not experiencing any particular issues, you can select "No known issues."',
    options: [
      {{ value: 'duplicate-accounts', label: 'Duplicate or similar accounts' }},
      {{ value: 'confusing-names', label: 'Confusing account names' }},
      {{ value: 'high-inactive', label: 'Too many inactive accounts' }},
      {{ value: 'mispostings', label: 'Frequent mispostings' }},
      {{ value: 'reporting-difficulty', label: 'Difficult to generate reports' }},
      {{ value: 'none', label: 'No known issues' }}
    ],
    required: true,
    autoAdvance: false
  }}
];

// === STATE MANAGEMENT ===
let currentQuestionIndex = 0;
let answers = {{}};
let saveIndicatorTimeout = null;

// === SAVE & RESUME ===
function saveToStorage() {{
  const data = {{
    currentQuestionIndex,
    answers,
    lastSaved: new Date().toISOString()
  }};

  if (ANONYMOUS) {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }}

  // Also save to server
  saveProgress('in-progress');

  // Show save indicator
  showSaveIndicator();
}}

function loadFromStorage() {{
  if (!ANONYMOUS) return false;

  try {{
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {{
      const data = JSON.parse(saved);
      currentQuestionIndex = data.currentQuestionIndex || 0;
      answers = data.answers || {{}};
      console.log('Resumed Section 2 from localStorage:', data);
      return true;
    }}
  }} catch (err) {{
    console.error('Failed to load from localStorage:', err);
  }}
  return false;
}}

function showSaveIndicator() {{
  let indicator = document.getElementById('saveIndicator');
  if (!indicator) {{
    indicator = document.createElement('div');
    indicator.id = 'saveIndicator';
    indicator.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: #22C55E;
      color: white;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 600;
      opacity: 0;
      transition: opacity 0.3s;
      z-index: 1000;
    `;
    indicator.textContent = 'Saved';
    document.body.appendChild(indicator);
  }}

  // Clear existing timeout
  if (saveIndicatorTimeout) clearTimeout(saveIndicatorTimeout);

  // Show indicator
  indicator.style.opacity = '1';

  // Hide after 2 seconds
  saveIndicatorTimeout = setTimeout(() => {{
    indicator.style.opacity = '0';
  }}, 2000);
}}

// === NAVIGATION ===
function goToQuestion(index) {{
  if (index < 0 || index >= questions.length) return;

  currentQuestionIndex = index;
  renderQuestion();
  updateProgress();
}}

function nextQuestion() {{
  if (currentQuestionIndex < questions.length - 1) {{
    goToQuestion(currentQuestionIndex + 1);
  }} else {{
    completeSection();
  }}
}}

function previousQuestion() {{
  if (currentQuestionIndex > 0) {{
    goToQuestion(currentQuestionIndex - 1);
  }}
}}

function completeSection() {{
  saveProgress('completed');
  updateProgress(100);

  // Show completion message
  const container = document.getElementById('wizardContainer');
  container.innerHTML = `
    <div style="text-align: center; padding: 3rem 1rem;">
      <div style="font-size: 3rem; margin-bottom: 1rem;">✅</div>
      <h2 style="color: var(--navy); margin-bottom: 1rem;">Section Complete!</h2>
      <p style="color: var(--warm-gray); margin-bottom: 2rem;">
        Great work! Your responses have been saved.
      </p>
      <p style="color: var(--warm-gray); font-size: 0.875rem;">
        Redirecting to dashboard...
      </p>
    </div>
  `;

  setTimeout(() => {{
    window.location.href = '/app';
  }}, 2000);
}}

// === RENDERING ===
function renderQuestion() {{
  const q = questions[currentQuestionIndex];
  const container = document.getElementById('wizardContainer');

  // Fade out
  container.style.opacity = '0';

  setTimeout(() => {{
    container.innerHTML = `
      <div class="wizard-question">
        <div class="question-header">
          <div class="question-number">Question ${{currentQuestionIndex + 1}} of ${{questions.length}}</div>
          <h2 class="question-text">${{q.text}}</h2>
          ${{q.help ? `<p class="question-help">${{q.help}}</p>` : ''}}
        </div>

        <div class="question-input" id="questionInput"></div>

        <div class="question-actions">
          <button
            class="btn-back"
            onclick="previousQuestion()"
            ${{currentQuestionIndex === 0 ? 'disabled' : ''}}
          >
            ← Back
          </button>
          <button
            class="btn-continue"
            id="continueBtn"
            onclick="handleContinue()"
            disabled
          >
            ${{currentQuestionIndex === questions.length - 1 ? 'Complete' : 'Continue'}}
          </button>
        </div>
      </div>
    `;

    // Render input component
    renderInput(q);

    // Fade in
    container.style.opacity = '1';
  }}, 150);
}}

function renderInput(q) {{
  const inputContainer = document.getElementById('questionInput');
  const savedAnswer = answers[q.id];

  if (q.type === 'dropdown') {{
    const select = document.createElement('select');
    select.className = 'question-select';
    select.innerHTML = `
      <option value="">-- Select --</option>
      ${{q.options.map(opt =>
        `<option value="${{opt.value}}" ${{savedAnswer === opt.value ? 'selected' : ''}}>${{opt.label}}</option>`
      ).join('')}}
    `;
    select.addEventListener('change', (e) => {{
      answers[q.id] = e.target.value;
      updateContinueButton();
      saveToStorage();
    }});
    inputContainer.appendChild(select);

    // Enable continue if answer exists
    if (savedAnswer) updateContinueButton();
  }}

  else if (q.type === 'multi-select') {{
    const savedValues = savedAnswer || [];

    const grid = document.createElement('div');
    grid.className = 'choice-grid';

    q.options.forEach(opt => {{
      const card = document.createElement('button');
      card.className = 'choice-card';
      card.textContent = opt.label;
      card.dataset.value = opt.value;

      if (savedValues.includes(opt.value)) {{
        card.classList.add('selected');
      }}

      card.addEventListener('click', () => {{
        card.classList.toggle('selected');

        // Get all selected values
        const selected = Array.from(grid.querySelectorAll('.choice-card.selected'))
          .map(c => c.dataset.value);

        answers[q.id] = selected;
        updateContinueButton();
        saveToStorage();
      }});

      grid.appendChild(card);
    }});

    inputContainer.appendChild(grid);

    // Enable continue if answer exists
    if (savedValues.length > 0) updateContinueButton();
  }}
}}

function updateContinueButton() {{
  const btn = document.getElementById('continueBtn');
  const q = questions[currentQuestionIndex];
  const answer = answers[q.id];

  if (q.type === 'dropdown') {{
    btn.disabled = !answer;
  }} else if (q.type === 'multi-select') {{
    btn.disabled = !answer || answer.length === 0;
  }}
}}

function handleContinue() {{
  const btn = document.getElementById('continueBtn');
  if (btn.disabled) return;

  nextQuestion();
}}

function updateProgress() {{
  const percentage = ((currentQuestionIndex + 1) / questions.length) * 100;
  const progressBar = document.getElementById('progressBar');
  if (progressBar) {{
    progressBar.style.width = percentage + '%';
  }}
}}

// === INITIALIZATION ===
function init() {{
  // Load saved progress
  const resumed = loadFromStorage();

  // Render first/resumed question
  renderQuestion();
  updateProgress();

  if (resumed) {{
    console.log('Resumed Section 2 at Q' + (currentQuestionIndex + 1));
  }}
}}

// Start wizard
setTimeout(init, 300);
"""



def generate_section3a_script():
    """Generate Section 3: Payroll & Pay Codes - Complete (10 questions)."""
    return f"""
// Section 3: Payroll & Pay Codes - Complete (Q1-Q10)
// Wizard interface to assess payroll complexity and pay code management

const questions = [
  // Q1: Pay Code Types Used (Multi-Select)
  {{
    id: 'q1_pay_code_types',
    type: 'multi-select',
    text: 'Which types of pay codes does your organization use?',
    aiContext: 'Types of pay codes in use - indicates payroll complexity',
    help: 'Pay codes are categories in your payroll system like "Regular Pay", "Overtime", "Vacation Pay", etc. Select all that apply.',
    options: [
      {{ value: 'regular-pay', label: 'Regular Pay' }},
      {{ value: 'overtime', label: 'Overtime' }},
      {{ value: 'vacation', label: 'Vacation' }},
      {{ value: 'sick-leave', label: 'Sick Leave' }},
      {{ value: 'comp-time', label: 'Comp Time' }},
      {{ value: 'holiday', label: 'Holiday Pay' }},
      {{ value: 'longevity', label: 'Longevity Pay' }},
      {{ value: 'shift-differential', label: 'Shift Differential' }},
      {{ value: 'standby-oncall', label: 'Standby/On-Call' }},
      {{ value: 'bilingual-pay', label: 'Bilingual Pay' }},
      {{ value: 'certification-pay', label: 'Certification/Education Pay' }},
      {{ value: 'car-allowance', label: 'Car Allowance' }},
      {{ value: 'uniform-allowance', label: 'Uniform Allowance' }},
      {{ value: 'severance', label: 'Severance' }},
      {{ value: 'other', label: 'Other' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q2: Total Pay Code Count
  {{
    id: 'q2_total_pay_codes',
    type: 'dropdown',
    text: 'Approximately how many different pay codes does your organization have in total?',
    aiContext: 'Total number of pay codes - key complexity indicator',
    help: 'This includes all types of pay - regular, overtime, leave, allowances, etc. If you\\'re not sure, your payroll system administrator can help you find this.',
    options: [
      {{ value: 'under-20', label: 'Under 20' }},
      {{ value: '20-50', label: '20-50' }},
      {{ value: '50-100', label: '50-100' }},
      {{ value: '100-200', label: '100-200' }},
      {{ value: 'over-200', label: 'Over 200' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q3: Naming Conventions
  {{
    id: 'q3_naming_conventions',
    type: 'single-select',
    text: 'Do you have standardized naming conventions for pay codes?',
    aiContext: 'Pay code naming standards - impacts maintainability',
    help: 'For example, do all overtime codes start with "OT-" or all leave codes start with "LV-"? Standardized naming makes payroll easier to manage.',
    options: [
      {{ value: 'yes-consistent', label: 'Yes, consistent naming across all codes' }},
      {{ value: 'partial', label: 'Partially - some categories are standardized' }},
      {{ value: 'no', label: 'No standardized naming' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q4: Overtime Pay Codes
  {{
    id: 'q4_overtime_codes',
    type: 'dropdown',
    text: 'How many different pay codes do you have for overtime?',
    aiContext: 'Overtime code count - often unnecessarily complex',
    help: 'Examples: time-and-a-half, double-time, callback overtime, etc. Some organizations have separate codes for each department or bargaining unit.',
    options: [
      {{ value: '1-2', label: '1-2 codes' }},
      {{ value: '3-5', label: '3-5 codes' }},
      {{ value: '6-10', label: '6-10 codes' }},
      {{ value: 'over-10', label: 'Over 10 codes' }},
      {{ value: 'none', label: 'We don\\'t use overtime codes' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q5: Leave/Time Off Codes
  {{
    id: 'q5_leave_codes',
    type: 'dropdown',
    text: 'How many different pay codes do you have for leave/time off (vacation, sick, etc.)?',
    aiContext: 'Leave code count - another common bloat area',
    help: 'Includes vacation, sick leave, comp time, personal days, bereavement, jury duty, etc.',
    options: [
      {{ value: '1-3', label: '1-3 codes' }},
      {{ value: '4-6', label: '4-6 codes' }},
      {{ value: '7-10', label: '7-10 codes' }},
      {{ value: 'over-10', label: 'Over 10 codes' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q6: Retirement Eligibility Tracking
  {{
    id: 'q6_retirement_tracking',
    type: 'single-select',
    text: 'Do you track which pay codes are eligible for retirement contributions?',
    aiContext: 'Retirement eligibility tracking - compliance requirement',
    help: 'Some types of pay (like certain allowances) might not count toward retirement. Tracking this correctly is important for compliance.',
    options: [
      {{ value: 'yes-all', label: 'Yes, for all pay codes' }},
      {{ value: 'yes-some', label: 'Yes, but only for some codes' }},
      {{ value: 'no', label: 'No, we don\\'t track this' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q7: Bargaining Unit Duplication
  {{
    id: 'q7_bargaining_unit_duplication',
    type: 'single-select',
    text: 'Do different bargaining units or departments have separate pay codes for the same type of pay?',
    aiContext: 'Pay code duplication across units - common bloat pattern',
    help: 'For example, do you have "Police Overtime", "Fire Overtime", "Public Works Overtime" as separate codes instead of one "Overtime" code?',
    options: [
      {{ value: 'yes-many', label: 'Yes, many duplicate codes across units' }},
      {{ value: 'yes-some', label: 'Yes, some duplication exists' }},
      {{ value: 'no', label: 'No, codes are shared across units' }},
      {{ value: 'not-applicable', label: 'We only have one bargaining unit' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q8: Frequency of Adding New Codes
  {{
    id: 'q8_new_code_frequency',
    type: 'dropdown',
    text: 'How often do you add new pay codes to your system?',
    aiContext: 'Pay code growth rate - indicates governance',
    help: 'Frequent additions without cleanup lead to bloat over time.',
    options: [
      {{ value: 'rarely', label: 'Rarely (less than once per year)' }},
      {{ value: 'annually', label: 'Annually during contract negotiations' }},
      {{ value: 'quarterly', label: 'A few times per year' }},
      {{ value: 'monthly', label: 'Monthly or more often' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q9: Pay Code Cleanup
  {{
    id: 'q9_cleanup_recent',
    type: 'single-select',
    text: 'Have you reviewed and removed unused pay codes in the last 12 months?',
    aiContext: 'Recent cleanup activity - maintenance practice',
    help: 'Regular cleanup prevents accumulation of obsolete pay codes that clutter reports and cause confusion.',
    options: [
      {{ value: 'yes-comprehensive', label: 'Yes, comprehensive review and cleanup' }},
      {{ value: 'yes-partial', label: 'Yes, but only partial cleanup' }},
      {{ value: 'no', label: 'No cleanup in the last year' }},
      {{ value: 'never', label: 'Never done a cleanup' }},
      {{ value: 'not-sure', label: 'Not sure' }}
    ],
    required: true,
    autoAdvance: false
  }},

  // Q10: Biggest Pay Code Challenges (Multi-Select)
  {{
    id: 'q10_challenges',
    type: 'multi-select',
    text: 'What are your biggest challenges with pay code management?',
    aiContext: 'User-reported pain points',
    help: 'Select all that apply. This helps us identify specific areas for improvement.',
    options: [
      {{ value: 'too-many-codes', label: 'Too many pay codes - hard to find the right one' }},
      {{ value: 'unclear-naming', label: 'Unclear code names - staff confused about which to use' }},
      {{ value: 'duplicate-codes', label: 'Duplicate or overlapping codes' }},
      {{ value: 'incorrect-usage', label: 'Staff frequently use wrong codes' }},
      {{ value: 'reporting-difficult', label: 'Difficult to generate payroll reports' }},
      {{ value: 'retirement-tracking', label: 'Trouble tracking retirement eligibility' }},
      {{ value: 'contract-changes', label: 'Hard to update codes when contracts change' }},
      {{ value: 'system-limitations', label: 'Payroll system limitations' }},
      {{ value: 'no-challenges', label: 'No significant challenges' }}
    ],
    required: true,
    autoAdvance: false
  }}
];

// === STATE MANAGEMENT ===
let currentQuestionIndex = 0;
let answers = {{}};
let saveIndicatorTimeout = null;

// === SAVE & RESUME ===
function saveToStorage() {{
  const data = {{
    currentQuestionIndex,
    answers,
    lastSaved: new Date().toISOString()
  }};

  if (ANONYMOUS) {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }}

  // Also save to server
  saveProgress('in-progress');

  // Show save indicator
  showSaveIndicator();
}}

function loadFromStorage() {{
  if (!ANONYMOUS) return false;

  try {{
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {{
      const data = JSON.parse(saved);
      currentQuestionIndex = data.currentQuestionIndex || 0;
      answers = data.answers || {{}};
      console.log('Resumed Section 3 from localStorage:', data);
      return true;
    }}
  }} catch (err) {{
    console.error('Failed to load from localStorage:', err);
  }}
  return false;
}}

function showSaveIndicator() {{
  let indicator = document.getElementById('saveIndicator');
  if (!indicator) {{
    indicator = document.createElement('div');
    indicator.id = 'saveIndicator';
    indicator.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: #22C55E;
      color: white;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 600;
      opacity: 0;
      transition: opacity 0.3s;
      z-index: 1000;
    `;
    indicator.textContent = 'Saved';
    document.body.appendChild(indicator);
  }}

  // Clear existing timeout
  if (saveIndicatorTimeout) clearTimeout(saveIndicatorTimeout);

  // Show indicator
  indicator.style.opacity = '1';

  // Hide after 2 seconds
  saveIndicatorTimeout = setTimeout(() => {{
    indicator.style.opacity = '0';
  }}, 2000);
}}

// === NAVIGATION ===
function goToQuestion(index) {{
  if (index < 0 || index >= questions.length) return;

  currentQuestionIndex = index;
  renderQuestion();
  updateProgress();
}}

function nextQuestion() {{
  if (currentQuestionIndex < questions.length - 1) {{
    goToQuestion(currentQuestionIndex + 1);
  }} else {{
    completeSection();
  }}
}}

function previousQuestion() {{
  if (currentQuestionIndex > 0) {{
    goToQuestion(currentQuestionIndex - 1);
  }}
}}

function completeSection() {{
  saveProgress('completed');
  updateProgress(100);

  // Show completion message
  const container = document.getElementById('wizardContainer');
  container.innerHTML = `
    <div style="text-align: center; padding: 3rem 1rem;">
      <div style="font-size: 3rem; margin-bottom: 1rem;">✅</div>
      <h2 style="color: var(--navy); margin-bottom: 1rem;">Section Complete!</h2>
      <p style="color: var(--warm-gray); margin-bottom: 2rem;">
        Great work! Your responses have been saved.
      </p>
      <p style="color: var(--warm-gray); font-size: 0.875rem;">
        Redirecting to dashboard...
      </p>
    </div>
  `;

  setTimeout(() => {{
    window.location.href = '/app';
  }}, 2000);
}}

// === RENDERING ===
function renderQuestion() {{
  const q = questions[currentQuestionIndex];
  const container = document.getElementById('wizardContainer');

  // Fade out
  container.style.opacity = '0';

  setTimeout(() => {{
    container.innerHTML = `
      <div class="wizard-question">
        <div class="question-header">
          <div class="question-number">Question ${{currentQuestionIndex + 1}} of ${{questions.length}}</div>
          <h2 class="question-text">${{q.text}}</h2>
          ${{q.help ? `<p class="question-help">${{q.help}}</p>` : ''}}
        </div>

        <div class="question-input" id="questionInput"></div>

        <div class="question-actions">
          <button
            class="btn-back"
            onclick="previousQuestion()"
            ${{currentQuestionIndex === 0 ? 'disabled' : ''}}
          >
            ← Back
          </button>
          <button
            class="btn-continue"
            id="continueBtn"
            onclick="handleContinue()"
            disabled
          >
            ${{currentQuestionIndex === questions.length - 1 ? 'Complete' : 'Continue'}}
          </button>
        </div>
      </div>
    `;

    // Render input component
    renderInput(q);

    // Fade in
    container.style.opacity = '1';
  }}, 150);
}}

function renderInput(q) {{
  const inputContainer = document.getElementById('questionInput');
  const savedAnswer = answers[q.id];

  if (q.type === 'dropdown') {{
    const select = document.createElement('select');
    select.className = 'question-select';
    select.innerHTML = `
      <option value="">-- Select --</option>
      ${{q.options.map(opt =>
        `<option value="${{opt.value}}" ${{savedAnswer === opt.value ? 'selected' : ''}}>${{opt.label}}</option>`
      ).join('')}}
    `;
    select.addEventListener('change', (e) => {{
      answers[q.id] = e.target.value;
      updateContinueButton();
      saveToStorage();
    }});
    inputContainer.appendChild(select);

    // Enable continue if answer exists
    if (savedAnswer) updateContinueButton();
  }}

  else if (q.type === 'single-select') {{
    const grid = document.createElement('div');
    grid.className = 'choice-grid';

    q.options.forEach(opt => {{
      const card = document.createElement('button');
      card.className = 'choice-card';
      card.textContent = opt.label;
      card.dataset.value = opt.value;

      if (savedAnswer === opt.value) {{
        card.classList.add('selected');
      }}

      card.addEventListener('click', () => {{
        // Deselect all others
        grid.querySelectorAll('.choice-card').forEach(c => c.classList.remove('selected'));
        // Select this one
        card.classList.add('selected');
        answers[q.id] = opt.value;
        updateContinueButton();
        saveToStorage();
      }});

      grid.appendChild(card);
    }});

    inputContainer.appendChild(grid);

    // Enable continue if answer exists
    if (savedAnswer) updateContinueButton();
  }}

  else if (q.type === 'multi-select') {{
    const savedValues = savedAnswer || [];

    const grid = document.createElement('div');
    grid.className = 'choice-grid';

    q.options.forEach(opt => {{
      const card = document.createElement('button');
      card.className = 'choice-card';
      card.textContent = opt.label;
      card.dataset.value = opt.value;

      if (savedValues.includes(opt.value)) {{
        card.classList.add('selected');
      }}

      card.addEventListener('click', () => {{
        card.classList.toggle('selected');

        // Get all selected values
        const selected = Array.from(grid.querySelectorAll('.choice-card.selected'))
          .map(c => c.dataset.value);

        answers[q.id] = selected;
        updateContinueButton();
        saveToStorage();
      }});

      grid.appendChild(card);
    }});

    inputContainer.appendChild(grid);

    // Enable continue if answer exists
    if (savedValues.length > 0) updateContinueButton();
  }}
}}

function updateContinueButton() {{
  const btn = document.getElementById('continueBtn');
  const q = questions[currentQuestionIndex];
  const answer = answers[q.id];

  if (q.type === 'dropdown' || q.type === 'single-select') {{
    btn.disabled = !answer;
  }} else if (q.type === 'multi-select') {{
    btn.disabled = !answer || answer.length === 0;
  }}
}}

function handleContinue() {{
  const btn = document.getElementById('continueBtn');
  if (btn.disabled) return;

  nextQuestion();
}}

function updateProgress() {{
  const percentage = ((currentQuestionIndex + 1) / questions.length) * 100;
  const progressBar = document.getElementById('progressBar');
  if (progressBar) {{
    progressBar.style.width = percentage + '%';
  }}
}}

// === INITIALIZATION ===
function init() {{
  // Load saved progress
  const resumed = loadFromStorage();

  // Render first/resumed question
  renderQuestion();
  updateProgress();

  if (resumed) {{
    console.log('Resumed Section 3 at Q' + (currentQuestionIndex + 1));
  }}
}}

// Start wizard
setTimeout(init, 300);
"""




# ============================================================
# ASSESSMENT API ENDPOINTS
# ============================================================

@app.post("/api/assessments")
async def create_assessment(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get or create an assessment for the current user.
    Reuses existing 'draft' assessment if one exists (1 assessment per user policy).
    """
    import uuid as _uuid
    from datetime import datetime
    import traceback

    # Debug: Print user dict structure
    print(f"DEBUG: User dict = {user}")

    try:
        # Get user_id safely
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            raise ValueError(f"No user ID found in user dict. Keys: {list(user.keys())}")

        # Check if user already has a draft assessment
        existing = db.execute(text("""
            SELECT id, status FROM "Assessment"
            WHERE "userId" = :user_id AND status = 'draft'
            ORDER BY "createdAt" DESC
            LIMIT 1
        """), {"user_id": user_id}).fetchone()

        if existing:
            # Reuse existing draft assessment
            print(f"Reusing existing draft assessment: {existing[0]}")
            return {"id": existing[0], "status": existing[1], "reused": True}

        # No existing draft, create new assessment
        assessment_id = str(_uuid.uuid4())
        db.execute(text("""
            INSERT INTO "Assessment" (id, "userId", status, "createdAt", "updatedAt")
            VALUES (:id, :user_id, 'draft', :now, :now)
        """), {
            "id": assessment_id,
            "user_id": user_id,
            "now": datetime.utcnow()
        })
        db.commit()

        print(f"Created new draft assessment: {assessment_id}")
        return {"id": assessment_id, "status": "draft", "reused": False}
    except Exception as e:
        db.rollback()
        print(f"ERROR creating assessment: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create assessment: {str(e)}")


@app.post("/api/assessments/transfer")
async def transfer_anonymous_assessment(
    assessment_data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Transfer anonymous assessment data from localStorage to database.
    Called when a user creates an account after completing anonymous assessment.
    """
    from datetime import datetime
    import traceback

    try:
        # Generate new assessment ID (replace anon- ID with real UUID)
        new_assessment_id = str(_uuid.uuid4())
        user_id = user.get("user_id") or user.get("id")

        if not user_id:
            raise ValueError("No user ID found")

        # Extract sections data from localStorage format
        sections_data = assessment_data.get("sections", {})

        # Create Assessment record
        db.execute(text("""
            INSERT INTO "Assessment" (id, "userId", status, "createdAt", "updatedAt")
            VALUES (:id, :user_id, 'draft', :now, :now)
        """), {
            "id": new_assessment_id,
            "user_id": user_id,
            "now": datetime.utcnow()
        })

        # Create AssessmentSection records for each section
        for section_num, section_data in sections_data.items():
            answers = section_data.get("answers", {})
            status = section_data.get("status", "draft")

            if answers:  # Only save sections with answers
                db.execute(text("""
                    INSERT INTO "AssessmentSection"
                    ("assessmentId", "sectionNumber", answers, status, "createdAt", "updatedAt")
                    VALUES (:assessment_id, :section_number, :answers, :status, :now, :now)
                """), {
                    "assessment_id": new_assessment_id,
                    "section_number": section_num,
                    "answers": json.dumps(answers),
                    "status": status,
                    "now": datetime.utcnow()
                })

        db.commit()

        return {
            "success": True,
            "assessment_id": new_assessment_id,
            "message": "Assessment data transferred successfully"
        }

    except Exception as e:
        db.rollback()
        print(f"ERROR transferring assessment: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to transfer assessment: {str(e)}")


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
    from datetime import datetime
    import traceback

    print(f"=== SAVE SECTION DEBUG ===")
    print(f"Assessment ID: {assessment_id}")
    print(f"Section: {request.section_number}")
    print(f"User dict: {user}")
    print(f"User ID: {user.get('user_id')}")
    print(f"Answers count: {len(request.answers)}")

    try:
        # Verify assessment belongs to user
        user_id = user.get("user_id")
        if not user_id:
            print(f"ERROR: No user_id found in user dict. Keys: {list(user.keys())}")
            raise HTTPException(status_code=401, detail="User ID not found in session")

        result = db.execute(text("""
            SELECT id FROM "Assessment"
            WHERE id = :id AND "userId" = :user_id
        """), {"id": assessment_id, "user_id": user_id})

        assessment_row = result.fetchone()
        if not assessment_row:
            print(f"ERROR: Assessment not found. ID={assessment_id}, UserID={user_id}")
            # Check if assessment exists at all
            check = db.execute(text('SELECT id, "userId" FROM "Assessment" WHERE id = :id'), {"id": assessment_id}).fetchone()
            if check:
                print(f"  Assessment exists but belongs to different user: {check[1]}")
            else:
                print(f"  Assessment does not exist in database")
            raise HTTPException(status_code=404, detail="Assessment not found")

        # Upsert section with proper timestamp handling
        section_id = str(_uuid.uuid4())
        now = datetime.utcnow()

        db.execute(text("""
            INSERT INTO "AssessmentSection" (id, "assessmentId", "sectionNumber", status, answers, "createdAt", "updatedAt")
            VALUES (:id, :assessment_id, :section_number, :status, :answers, :created_at, :updated_at)
            ON CONFLICT ("assessmentId", "sectionNumber")
            DO UPDATE SET
                status = EXCLUDED.status,
                answers = EXCLUDED.answers,
                "updatedAt" = :updated_at
        """), {
            "id": section_id,
            "assessment_id": assessment_id,
            "section_number": request.section_number,
            "status": request.status,
            "answers": json.dumps(request.answers),
            "created_at": now,
            "updated_at": now
        })

        # If section 1, also update organizationProfile
        if request.section_number == "1":
            db.execute(text("""
                UPDATE "Assessment"
                SET "organizationProfile" = :profile, "updatedAt" = :updated_at
                WHERE id = :assessment_id
            """), {
                "profile": json.dumps(request.answers),
                "assessment_id": assessment_id,
                "updated_at": now
            })

        db.commit()

        print(f"✓ Section saved successfully: {request.section_number}")
        return {"success": True, "section_number": request.section_number, "status": request.status}

    except HTTPException:
        db.rollback()
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        db.rollback()
        print(f"ERROR saving assessment section: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save section: {str(e)}")


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


# ─────────────────────────────────────────────────────────────────────────────
# CRM Integration Endpoints
# ─────────────────────────────────────────────────────────────────────────────


class CRMConfigRequest(BaseModel):
    """Request model for CRM configuration."""
    provider: str  # 'salesforce' or 'hubspot'
    enabled: bool = True
    credentials: dict  # Provider-specific credentials
    field_mapping: Optional[dict] = None
    default_owner_id: Optional[str] = None
    auto_sync_hot_leads: bool = True
    auto_sync_warm_leads: bool = False


class CRMSyncRequest(BaseModel):
    """Request model for syncing leads to CRM."""
    lead_ids: List[str]  # List of lead IDs to sync
    provider: str  # 'salesforce' or 'hubspot'
    update_existing: bool = True  # Update if lead already exists in CRM


@app.post("/api/crm/config")
async def create_crm_config(
    config_request: CRMConfigRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create or update CRM configuration for user.

    Stores encrypted credentials and sync preferences.
    """
    from src.database import CRMConfig
    import json
    from cryptography.fernet import Fernet
    import base64

    try:
        # Check if config already exists for this user/provider
        existing = db.query(CRMConfig).filter(
            CRMConfig.user_id == user["user_id"],
            CRMConfig.provider == config_request.provider
        ).first()

        # Simple encryption using Fernet (in production, use user-specific key from env)
        # For MVP, use a shared key (should move to user-specific keys later)
        encryption_key = os.getenv("CRM_ENCRYPTION_KEY")
        if not encryption_key:
            # Generate a key if not set (not ideal for production)
            encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
            logger.warning("No CRM_ENCRYPTION_KEY set - using temp key (credentials won't persist across restarts)")

        fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        credentials_encrypted = fernet.encrypt(json.dumps(config_request.credentials).encode()).decode()

        if existing:
            # Update existing config
            existing.enabled = 1 if config_request.enabled else 0
            existing.credentials_encrypted = credentials_encrypted
            existing.field_mapping = config_request.field_mapping
            existing.default_owner_id = config_request.default_owner_id
            existing.auto_sync_hot_leads = 1 if config_request.auto_sync_hot_leads else 0
            existing.auto_sync_warm_leads = 1 if config_request.auto_sync_warm_leads else 0
            existing.updated_at = datetime.utcnow()

            db.commit()
            config_id = existing.id

        else:
            # Create new config
            new_config = CRMConfig(
                user_id=user["user_id"],
                provider=config_request.provider,
                enabled=1 if config_request.enabled else 0,
                credentials_encrypted=credentials_encrypted,
                field_mapping=config_request.field_mapping,
                default_owner_id=config_request.default_owner_id,
                auto_sync_hot_leads=1 if config_request.auto_sync_hot_leads else 0,
                auto_sync_warm_leads=1 if config_request.auto_sync_warm_leads else 0
            )

            db.add(new_config)
            db.commit()
            config_id = new_config.id

        return {
            "success": True,
            "config_id": config_id,
            "provider": config_request.provider,
            "message": f"{config_request.provider.title()} CRM configured successfully"
        }

    except Exception as e:
        logger.error(f"Failed to save CRM config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/crm/config")
async def get_crm_configs(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all CRM configurations for current user (credentials excluded)."""
    from src.database import CRMConfig

    configs = db.query(CRMConfig).filter(
        CRMConfig.user_id == user["user_id"]
    ).all()

    return {
        "configs": [
            {
                "id": config.id,
                "provider": config.provider,
                "enabled": bool(config.enabled),
                "auto_sync_hot_leads": bool(config.auto_sync_hot_leads),
                "auto_sync_warm_leads": bool(config.auto_sync_warm_leads),
                "created_at": config.created_at.isoformat(),
                "updated_at": config.updated_at.isoformat()
            }
            for config in configs
        ]
    }


@app.delete("/api/crm/config/{config_id}")
async def delete_crm_config(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a CRM configuration."""
    from src.database import CRMConfig

    config = db.query(CRMConfig).filter(
        CRMConfig.id == config_id,
        CRMConfig.user_id == user["user_id"]
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="CRM config not found")

    db.delete(config)
    db.commit()

    return {"success": True, "message": "CRM config deleted"}


@app.post("/api/crm/sync")
async def sync_leads_to_crm(
    sync_request: CRMSyncRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sync selected leads to CRM system.

    Returns sync results for each lead.
    """
    from src.database import CRMConfig, Lead
    from src.crm import get_crm_provider
    from cryptography.fernet import Fernet
    import json

    try:
        # Get CRM config
        crm_config = db.query(CRMConfig).filter(
            CRMConfig.user_id == user["user_id"],
            CRMConfig.provider == sync_request.provider,
            CRMConfig.enabled == 1
        ).first()

        if not crm_config:
            raise HTTPException(
                status_code=404,
                detail=f"No active {sync_request.provider} configuration found"
            )

        # Decrypt credentials
        encryption_key = os.getenv("CRM_ENCRYPTION_KEY")
        if not encryption_key:
            raise HTTPException(
                status_code=500,
                detail="CRM encryption key not configured"
            )

        fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        credentials = json.loads(fernet.decrypt(crm_config.credentials_encrypted.encode()).decode())

        # Initialize CRM provider
        provider = get_crm_provider(sync_request.provider, credentials)

        # Authenticate
        if not provider.authenticate():
            raise HTTPException(
                status_code=401,
                detail=f"Failed to authenticate with {sync_request.provider}"
            )

        # Sync each lead
        results = []
        for lead_id in sync_request.lead_ids:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()

            if not lead:
                results.append({
                    "lead_id": lead_id,
                    "success": False,
                    "error": "Lead not found"
                })
                continue

            # Map lead data to CRM format
            lead_data = provider.map_lead_data(lead)

            # Sync to CRM
            sync_result = provider.sync_lead(lead_data, update_existing=sync_request.update_existing)

            # Update lead with sync status
            if sync_result.success:
                lead.crm_synced = 1
                lead.crm_provider = sync_request.provider
                lead.crm_lead_id = sync_result.crm_lead_id
                lead.crm_url = sync_result.crm_url
                lead.crm_synced_at = sync_result.synced_at
                lead.crm_sync_error = None
            else:
                lead.crm_sync_error = sync_result.error_message

            db.commit()

            results.append({
                "lead_id": lead_id,
                "municipality": f"{lead.municipality}, {lead.state}",
                "success": sync_result.success,
                "crm_lead_id": sync_result.crm_lead_id,
                "crm_url": sync_result.crm_url,
                "error": sync_result.error_message
            })

        # Summary
        successful = sum(1 for r in results if r["success"])
        failed = len(results) - successful

        return {
            "success": True,
            "summary": {
                "total": len(results),
                "successful": successful,
                "failed": failed
            },
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CRM sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/crm/sync-status")
async def get_crm_sync_status(
    scan_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get CRM sync status summary.

    Optionally filter by scan_id.
    """
    from src.database import Lead, Scan
    from sqlalchemy import func

    # Build base query
    query = db.query(Lead).join(Scan).filter(Scan.user_id == user["user_id"])

    if scan_id:
        query = query.filter(Lead.scan_id == scan_id)

    # Get counts
    total_leads = query.count()
    synced_leads = query.filter(Lead.crm_synced == 1).count()
    failed_syncs = query.filter(Lead.crm_sync_error.isnot(None)).count()

    # Get breakdown by provider
    provider_breakdown = db.query(
        Lead.crm_provider,
        func.count(Lead.id).label('count')
    ).join(Scan).filter(
        Scan.user_id == user["user_id"],
        Lead.crm_synced == 1
    ).group_by(Lead.crm_provider).all()

    return {
        "total_leads": total_leads,
        "synced": synced_leads,
        "not_synced": total_leads - synced_leads,
        "failed": failed_syncs,
        "sync_rate": round((synced_leads / total_leads * 100), 1) if total_leads > 0 else 0,
        "by_provider": {
            row.crm_provider: row.count
            for row in provider_breakdown
            if row.crm_provider
        }
    }


# ============================================================
# DEAD DOMAIN MANAGEMENT
# ============================================================

class DomainUpdateRequest(BaseModel):
    new_domain: str
    reenrich: bool = False


@app.get("/api/dead-domains")
async def get_dead_domains(
    state: Optional[str] = None,
    min_population: Optional[int] = None,
    max_population: Optional[int] = None,
    exclude_cdp: bool = False,
    limit: Optional[int] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of municipalities with dead domains.

    Query params:
    - state: Filter by state code (e.g., CA, TX)
    - min_population: Minimum population filter
    - max_population: Maximum population filter (useful for targeting small towns)
    - exclude_cdp: Exclude CDPs (Census Designated Places) - unincorporated areas
    - limit: Maximum number of results

    Returns list of municipalities with dead domains for manual correction.

    Pro tip: Small towns (2.5K-25K) are often the most valuable targets!
    """
    query = db.query(Municipality).filter(Municipality.domain_status == 'dead')

    if state:
        query = query.filter(Municipality.state == state.upper())

    if min_population:
        query = query.filter(Municipality.population >= min_population)

    if max_population:
        query = query.filter(Municipality.population <= max_population)

    if exclude_cdp:
        query = query.filter(~Municipality.name.like('%CDP%'))

    query = query.order_by(Municipality.population.desc())

    if limit:
        query = query.limit(limit)

    results = query.all()

    return {
        "total": len(results),
        "municipalities": [
            {
                "id": m.id,
                "name": m.name,
                "state": m.state,
                "population": m.population,
                "dead_domain": m.domain,
                "resolved_url": m.resolved_url
            }
            for m in results
        ]
    }


@app.patch("/api/municipalities/{municipality_id}/domain")
async def update_municipality_domain(
    municipality_id: str,
    request: DomainUpdateRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update domain for a municipality.

    If reenrich=true, will clear existing sources and re-run enrichment.
    """
    # Find municipality
    muni = db.query(Municipality).filter(Municipality.id == municipality_id).first()

    if not muni:
        raise HTTPException(status_code=404, detail="Municipality not found")

    # Store old values
    old_domain = muni.domain
    old_status = muni.domain_status

    # Update domain
    muni.domain = request.new_domain
    muni.domain_status = 'unverified'  # Will be verified during enrichment
    muni.resolved_url = None  # Clear cached URL

    db.commit()

    result = {
        "success": True,
        "municipality": {
            "id": muni.id,
            "name": muni.name,
            "state": muni.state,
            "old_domain": old_domain,
            "new_domain": request.new_domain,
            "old_status": old_status,
            "new_status": muni.domain_status
        },
        "reenrichment": None
    }

    # Re-enrich if requested
    if request.reenrich:
        # Clear existing sources
        db.execute(text("""
            DELETE FROM municipal_sources
            WHERE municipality_id = :muni_id
        """), {"muni_id": muni.id})
        db.commit()

        # Run enrichment in background
        def reenrich_municipality():
            try:
                from src.discovery import SourceDiscovery
                discovery = SourceDiscovery()

                # Refresh municipality from database
                db_session = next(get_db())
                fresh_muni = db_session.query(Municipality).filter(
                    Municipality.id == municipality_id
                ).first()

                if fresh_muni:
                    enrichment_results = discovery.discover_municipality(fresh_muni)
                    logger.info(f"Re-enrichment complete for {fresh_muni.name}, {fresh_muni.state}: {enrichment_results}")
                    db_session.close()
            except Exception as e:
                logger.error(f"Re-enrichment failed for {municipality_id}: {e}")

        background_tasks.add_task(reenrich_municipality)
        result["reenrichment"] = "started"

    return result


@app.get("/api/dead-domains/export")
async def export_dead_domains_csv(
    state: Optional[str] = None,
    min_population: Optional[int] = None,
    max_population: Optional[int] = None,
    exclude_cdp: bool = False,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export dead domains to CSV for batch research.

    Query params:
    - state: Filter by state
    - min_population: Minimum population
    - max_population: Maximum population (for targeting small towns)
    - exclude_cdp: Exclude CDPs (Census Designated Places)

    Returns CSV file with columns: Municipality, State, Population, Dead Domain, Corrected Domain, Notes
    """
    import csv
    from io import StringIO

    query = db.query(Municipality).filter(Municipality.domain_status == 'dead')

    if state:
        query = query.filter(Municipality.state == state.upper())

    if min_population:
        query = query.filter(Municipality.population >= min_population)

    if max_population:
        query = query.filter(Municipality.population <= max_population)

    if exclude_cdp:
        query = query.filter(~Municipality.name.like('%CDP%'))

    query = query.order_by(Municipality.state, Municipality.population.desc())
    results = query.all()

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Municipality ID', 'Municipality', 'State', 'Population',
        'Dead Domain', 'Corrected Domain', 'Notes'
    ])

    # Write data
    for muni in results:
        writer.writerow([
            muni.id,
            muni.name,
            muni.state,
            muni.population or 0,
            muni.domain or '',
            '',  # Empty column for manual correction
            ''   # Empty column for notes
        ])

    # Return as downloadable file
    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=dead_domains_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@app.get("/api/dead-domains/stats")
async def get_dead_domain_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics about dead domains by state.
    """
    from sqlalchemy import func

    stats = db.query(
        Municipality.state,
        func.count(Municipality.id).label('dead_count')
    ).filter(
        Municipality.domain_status == 'dead'
    ).group_by(Municipality.state).order_by(func.count(Municipality.id).desc()).all()

    total_dead = sum(s.dead_count for s in stats)

    # Get high-priority (pop > 50K)
    high_priority = db.query(func.count(Municipality.id)).filter(
        Municipality.domain_status == 'dead',
        Municipality.population >= 50000
    ).scalar()

    return {
        "total_dead": total_dead,
        "high_priority": high_priority,
        "by_state": [
            {"state": s.state, "count": s.dead_count}
            for s in stats
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
