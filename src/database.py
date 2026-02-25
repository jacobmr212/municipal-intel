"""
Database models and connection for Municipal Intel.

Architecture:
- Municipality: Core city data (name, state, population, domain status)
- MunicipalSource: Discovered meeting minutes / procurement URLs

The enrichment pipeline populates these tables offline.
The scan pipeline reads from MunicipalSource to scrape fast.
"""

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import uuid
import hashlib

# Database configuration
# For Vercel: Use PostgreSQL via DATABASE_URL environment variable
# For local development: Use SQLite
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Production: PostgreSQL from environment
    # Vercel Postgres URLs start with postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Local development: SQLite
    DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "municipal_intel.db")
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

Base = declarative_base()


class Municipality(Base):
    """
    Municipality/City entity.

    Stores core data about each city and tracks domain enrichment status.
    domain_status transitions: unverified → verified | dead
    """
    __tablename__ = "municipalities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    state = Column(String(2), nullable=False, index=True)  # Two-letter code: MN, UT, etc.
    population = Column(Integer, nullable=False, default=0, index=True)

    # Domain tracking
    domain = Column(String(200), nullable=True)  # Original domain from database (may be wrong)
    domain_status = Column(String(20), nullable=False, default="unverified", index=True)  # unverified | verified | dead
    domain_verified_at = Column(DateTime, nullable=True)
    resolved_url = Column(String(500), nullable=True)  # Actual working URL after redirects

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sources = relationship("MunicipalSource", back_populates="municipality", cascade="all, delete-orphan")
    entities = relationship("GovernmentEntity", back_populates="municipality", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Municipality: {self.name}, {self.state} (pop: {self.population:,}, status: {self.domain_status})>"


class GovernmentEntity(Base):
    """
    Government Entity within a municipality.

    Represents separate government organizations that may use independent ERP systems:
    - School Districts (separate budgets!)
    - Fire Districts
    - Library Districts
    - Water/Sewer Districts
    - Parks & Recreation Districts
    - County Government

    Each entity is a separate sales opportunity with its own procurement budget.
    """
    __tablename__ = "government_entities"

    id = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    municipality_id = Column(Integer, ForeignKey("municipalities.id"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)  # school_district, fire_district, etc.
    name = Column(String(200), nullable=False)
    domain = Column(String(200), nullable=True)
    url = Column(String(500), nullable=True)
    confidence = Column(Float, nullable=True, index=True)  # 0.0 - 1.0
    notes = Column(Text, nullable=True)

    # Enrichment tracking
    sources_discovered = Column(Integer, nullable=False, default=0)
    last_enriched_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    municipality = relationship("Municipality", back_populates="entities")
    sources = relationship("MunicipalSource", back_populates="entity", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GovernmentEntity: {self.name} ({self.entity_type}) - {self.confidence:.0%} confidence>"


class MunicipalSource(Base):
    """
    Discovered meeting minutes / procurement source URL.

    Each municipality can have multiple sources:
    - Meeting minutes page
    - Procurement/bids page
    - Agenda packets page
    - Budget documents page

    The scan pipeline reads from this table instead of probing URLs.
    """
    __tablename__ = "municipal_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id"), nullable=False, index=True)
    entity_id = Column(String(36), ForeignKey("government_entities.id"), nullable=True, index=True)  # NEW: Link to specific entity

    # Source details
    url = Column(String(500), nullable=False, unique=True)  # The discovered source page URL
    source_type = Column(String(50), nullable=False, index=True)  # meeting_minutes | procurement | budget | job_posting
    platform = Column(String(50), nullable=True)  # civicplus | granicus | boarddocs | html | null
    confidence = Column(Float, nullable=False, default=0.7)  # 0.0 - 1.0

    # Scraping metadata
    last_scraped_at = Column(DateTime, nullable=True)
    last_scrape_success = Column(Integer, nullable=True, default=None)  # Boolean: 1=success, 0=fail, null=never scraped
    scrape_error = Column(Text, nullable=True)  # Last error message if scrape failed

    # Discovery metadata
    discovered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    discovered_by_pattern = Column(String(200), nullable=True)  # Which URL pattern found it: "/AgendaCenter", etc.

    # Relationships
    municipality = relationship("Municipality", back_populates="sources")
    entity = relationship("GovernmentEntity", back_populates="sources")

    def __repr__(self):
        return f"<Source: {self.municipality.name if self.municipality else 'Unknown'} - {self.source_type} ({self.platform})>"


class User(Base):
    """
    User account.

    Passwordless authentication via magic links.
    role: "client" | "consultant" | "admin"
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(String(20), nullable=False, default="client")  # client | consultant | admin
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Notification preferences
    email_alerts_enabled = Column(Integer, nullable=False, default=1)  # 1=enabled, 0=disabled
    alert_on_hot_leads = Column(Integer, nullable=False, default=1)  # Immediate alerts for hot leads
    alert_on_urgent_leads = Column(Integer, nullable=False, default=1)  # Immediate alerts for urgent leads (urgency >= 60)
    daily_digest_enabled = Column(Integer, nullable=False, default=0)  # Daily summary email
    min_urgency_for_alert = Column(Integer, nullable=False, default=60)  # Minimum urgency score to trigger alert

    # Relationships
    scans = relationship("Scan", back_populates="user")
    magic_links = relationship("MagicLink", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User: {self.email}>"


class MagicLink(Base):
    """
    Magic link token for passwordless authentication.

    Tokens expire after 15 minutes and are single-use.
    """
    __tablename__ = "magic_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Integer, nullable=False, default=0)  # 0 = not used, 1 = used

    # Relationships
    user = relationship("User", back_populates="magic_links")

    def __repr__(self):
        return f"<MagicLink: {self.token[:8]}... for {self.user.email if self.user else 'Unknown'}>"


class Scan(Base):
    """
    Scan execution record.

    Tracks scan configuration, progress, status, and results.
    Enables scan history and result persistence.
    """
    __tablename__ = "scans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    # Scan status
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending | running | completed | failed

    # Scan configuration (stored as JSON)
    config_json = Column(JSON, nullable=False)  # {states: [], population_tier: "", source_types: []}

    # Progress tracking
    progress_phase = Column(String(50), nullable=False, default="discovery")  # discovery | scraping | analysis | complete
    progress_pct = Column(Integer, nullable=False, default=0)  # 0-100 within current phase
    progress_message = Column(Text, nullable=True)  # Current status message for UI

    # Statistics (stored as JSON)
    stats_json = Column(JSON, nullable=True)  # {sources_found: 0, docs_scraped: 0, leads_hot: 0, leads_warm: 0, leads_cold: 0}

    # Relationships
    user = relationship("User", back_populates="scans")
    leads = relationship("Lead", back_populates="scan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Scan {self.id[:8]}: {self.status} - {len(self.leads) if self.leads else 0} leads>"


class Lead(Base):
    """
    Lead record from document analysis.

    Each lead represents a municipality with signals indicating potential
    ERP procurement activity.
    """
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False, index=True)

    # Municipality info
    municipality = Column(String(200), nullable=False)
    state = Column(String(2), nullable=False, index=True)
    population = Column(Integer, nullable=False, default=0)

    # Document info
    title = Column(Text, nullable=False)
    url = Column(String(500), nullable=False)
    date = Column(String(50), nullable=True)  # Document/meeting date
    source_type = Column(String(50), nullable=False, index=True)  # meeting_minutes | procurement | budget | job_posting | agenda_packet | audit

    # Lead classification
    relevance_score = Column(Float, nullable=False, default=0.0, index=True)  # 0-100
    lead_type = Column(String(10), nullable=False, index=True)  # hot | warm | cold
    customer_status = Column(String(20), nullable=True, index=True)  # existing_customer | new_opportunity | unknown
    recommended_action = Column(Text, nullable=True)  # Recommended next step for sales team

    # Signal details (stored as JSON)
    signal_matches_json = Column(JSON, nullable=True)  # Full keyword match data with contexts

    # Deduplication tracking
    document_hash = Column(String(32), nullable=True, index=True)  # MD5 hash of document content
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    times_seen = Column(Integer, nullable=False, default=1)  # How many scans found this lead

    # Temporal intelligence (urgency/deadline detection)
    urgency_score = Column(Integer, nullable=False, default=0, index=True)  # 0-100
    deadline_date = Column(DateTime, nullable=True, index=True)  # Extracted deadline date
    days_until_deadline = Column(Integer, nullable=True)  # Days from now to deadline
    decision_stage = Column(String(20), nullable=True)  # exploration | evaluation | procurement | implementation
    fiscal_year = Column(String(10), nullable=True)  # e.g., "FY2025"

    # User notes
    notes = Column(Text, nullable=True)

    # Competitor Intelligence
    competitors_mentioned = Column(JSON, nullable=True)  # ["Tyler Technologies", "CentralSquare"]
    competitive_context = Column(Text, nullable=True)  # Strategic context summary
    existing_vendor = Column(String(100), nullable=True, index=True)  # Current vendor if detected

    # ROI Tracking / Lead Status Pipeline
    status = Column(String(20), nullable=False, default="new", index=True)  # new | contacted | qualified | proposal | won | lost
    deal_value = Column(Integer, nullable=True)  # Deal value in USD (if won)
    contacted_date = Column(DateTime, nullable=True)  # When sales first reached out
    won_date = Column(DateTime, nullable=True)  # When deal closed (if won)
    lost_reason = Column(Text, nullable=True)  # Why deal was lost (if applicable)

    # CRM Sync Tracking
    crm_synced = Column(Integer, nullable=False, default=0, index=True)  # 0 = not synced, 1 = synced
    crm_provider = Column(String(50), nullable=True, index=True)  # salesforce | hubspot
    crm_lead_id = Column(String(100), nullable=True)  # Lead ID in CRM system
    crm_url = Column(String(500), nullable=True)  # Direct URL to view lead in CRM
    crm_synced_at = Column(DateTime, nullable=True)  # Timestamp of last sync
    crm_sync_error = Column(Text, nullable=True)  # Error message if sync failed

    # Relationships
    scan = relationship("Scan", back_populates="leads")

    def __repr__(self):
        return f"<Lead: {self.municipality}, {self.state} - {self.lead_type.upper()} ({self.relevance_score:.1f})>"


class Watchlist(Base):
    """
    Watchlist items - municipalities marked by user for monitoring.

    Users can add municipalities to their watchlist to receive automatic
    updates when new signals are detected.
    """
    __tablename__ = "watchlist"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id"), nullable=False, index=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User")
    municipality = relationship("Municipality")

    def __repr__(self):
        return f"<Watchlist: {self.municipality.name if self.municipality else 'Unknown'}, {self.municipality.state if self.municipality else '??'}>"


class Territory(Base):
    """
    Territory definitions - state/region assignments for users.

    Enables automatic filtering of Feed results based on user's assigned
    geographic coverage areas.
    """
    __tablename__ = "territories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)  # Two-letter state code

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<Territory: {self.user.email if self.user else 'Unknown'} → {self.state}>"


class CachedDocument(Base):
    """
    Document cache for scraped meeting minutes/PDFs.

    Caches document content for 7 days to speed up re-scans and reduce
    load on municipal servers. Keyed by URL hash to handle long URLs.
    """
    __tablename__ = "cached_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url_hash = Column(String(32), unique=True, index=True, nullable=False)  # MD5 hash of URL
    url = Column(String(500), nullable=False)  # Original URL
    content_text = Column(Text, nullable=False)  # Extracted document text
    content_hash = Column(String(32), index=True, nullable=False)  # MD5 hash of content

    # Cache metadata
    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)  # Default: 7 days from scrape
    hit_count = Column(Integer, nullable=False, default=0)  # How many times cache was used

    # Source metadata
    municipality_name = Column(String(200), nullable=True)  # For debugging/logging
    state = Column(String(2), nullable=True, index=True)  # For filtering/cleanup

    def __repr__(self):
        return f"<CachedDocument: {self.municipality_name}, {self.state} - hits: {self.hit_count}>"

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.utcnow() > self.expires_at


class CRMConfig(Base):
    """
    CRM configuration for user accounts.

    Stores encrypted CRM credentials and sync preferences.
    Each user can configure multiple CRM providers (Salesforce, HubSpot, etc.)
    """
    __tablename__ = "crm_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # salesforce | hubspot
    enabled = Column(Integer, nullable=False, default=1)  # 1=enabled, 0=disabled

    # Encrypted credentials (encrypted with user-specific key)
    credentials_encrypted = Column(Text, nullable=False)

    # Field mapping (JSON) - maps Lead model fields to CRM fields
    field_mapping = Column(JSON, nullable=True)

    # Default owner ID in CRM system for assigning leads
    default_owner_id = Column(String(100), nullable=True)

    # Auto-sync preferences
    auto_sync_hot_leads = Column(Integer, nullable=False, default=1)  # Auto-sync hot leads
    auto_sync_warm_leads = Column(Integer, nullable=False, default=0)  # Don't auto-sync warm by default

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<CRMConfig: {self.provider} for {self.user.email if self.user else 'Unknown'}>"


# Database setup
# pool_pre_ping: test connections before use (handles Neon idle SSL drops)
# pool_recycle: recycle connections every 5 min (Neon closes idle after ~5 min)
# pool_size / max_overflow: conservative limits for a shared Neon free tier
if DATABASE_URL and "postgresql" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 10}
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database: create tables if they don't exist."""
    # Only create directories for SQLite (local development)
    if not os.getenv("DATABASE_URL"):
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    try:
        Base.metadata.create_all(bind=engine)
        if os.getenv("DATABASE_URL"):
            print(f"✓ Database initialized at: {os.getenv('DATABASE_URL')[:30]}...")
        else:
            print(f"✓ Database initialized at: {DATABASE_PATH}")
    except Exception as e:
        # Log but don't crash — connections may recover on first request
        print(f"⚠ Database init warning (will retry on first request): {e}")


def get_db():
    """Get a database session (use with context manager)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Quick test / initialization
    init_db()
    print(f"Tables created: {', '.join(Base.metadata.tables.keys())}")
