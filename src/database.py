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

    def __repr__(self):
        return f"<Municipality: {self.name}, {self.state} (pop: {self.population:,}, status: {self.domain_status})>"


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

    def __repr__(self):
        return f"<Source: {self.municipality.name if self.municipality else 'Unknown'} - {self.source_type} ({self.platform})>"


class User(Base):
    """
    User account.

    Passwordless authentication via magic links.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

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
    recommended_action = Column(Text, nullable=True)  # Recommended next step for sales team

    # Signal details (stored as JSON)
    signal_matches_json = Column(JSON, nullable=True)  # Full keyword match data with contexts

    # User notes
    notes = Column(Text, nullable=True)

    # Relationships
    scan = relationship("Scan", back_populates="leads")

    def __repr__(self):
        return f"<Lead: {self.municipality}, {self.state} - {self.lead_type.upper()} ({self.relevance_score:.1f})>"


# Database setup
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database: create tables if they don't exist."""
    # Only create directories for SQLite (local development)
    if not os.getenv("DATABASE_URL"):
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    Base.metadata.create_all(bind=engine)

    if os.getenv("DATABASE_URL"):
        print(f"✓ Database initialized at: {os.getenv('DATABASE_URL')[:30]}...")
    else:
        print(f"✓ Database initialized at: {DATABASE_PATH}")


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
