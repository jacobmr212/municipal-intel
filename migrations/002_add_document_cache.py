"""
Migration 002: Add Document Cache Table

Creates the cached_documents table for storing scraped document content
to speed up re-scans and reduce load on municipal servers.

Run this migration before deploying the document caching feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Create cached_documents table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name='cached_documents'
        """))

        if result.fetchone():
            print("✓ Migration already applied (table exists)")
            return

        print("Running migration 002: Add document cache table...")

        # Create cached_documents table
        conn.execute(text("""
            CREATE TABLE cached_documents (
                id VARCHAR(36) PRIMARY KEY,
                url_hash VARCHAR(32) UNIQUE NOT NULL,
                url VARCHAR(500) NOT NULL,
                content_text TEXT NOT NULL,
                content_hash VARCHAR(32) NOT NULL,
                scraped_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                municipality_name VARCHAR(200),
                state VARCHAR(2)
            )
        """))

        # Create indexes
        conn.execute(text("""
            CREATE INDEX idx_cached_documents_url_hash ON cached_documents(url_hash)
        """))

        conn.execute(text("""
            CREATE INDEX idx_cached_documents_expires_at ON cached_documents(expires_at)
        """))

        conn.execute(text("""
            CREATE INDEX idx_cached_documents_state ON cached_documents(state)
        """))

        conn.execute(text("""
            CREATE INDEX idx_cached_documents_content_hash ON cached_documents(content_hash)
        """))

        conn.commit()

        print("✓ Migration 002 completed successfully")
        print("  - Created cached_documents table")
        print("  - Created indexes: url_hash, expires_at, state, content_hash")
        print("  - Cache TTL: 7 days (configured in scraper)")

if __name__ == "__main__":
    run_migration()
