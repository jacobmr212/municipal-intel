"""
Database models and connection for Municipal Intel.

Architecture:
- Municipality: Core city data (name, state, population, domain status)
- MunicipalSource: Discovered meeting minutes / procurement URLs

The enrichment pipeline populates these tables offline.
The scan pipeline reads from MunicipalSource to scrape fast.
"""

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

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


# Database setup
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database: create tables if they don't exist."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)
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
