"""
Migration 001: Add Lead Deduplication Fields

Adds document_hash, first_seen, last_seen, and times_seen columns to the leads table
for deduplication tracking across multiple scans.

Run this migration before deploying the deduplication feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add deduplication columns to leads table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='leads' AND column_name='document_hash'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 001: Add lead deduplication fields...")

        # Add new columns
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN document_hash VARCHAR(32),
            ADD COLUMN first_seen TIMESTAMP DEFAULT NOW(),
            ADD COLUMN last_seen TIMESTAMP DEFAULT NOW(),
            ADD COLUMN times_seen INTEGER DEFAULT 1
        """))

        # Create index on document_hash for fast lookups
        conn.execute(text("""
            CREATE INDEX idx_leads_document_hash ON leads(document_hash)
        """))

        # Backfill existing leads with current timestamp
        conn.execute(text("""
            UPDATE leads
            SET first_seen = NOW(), last_seen = NOW(), times_seen = 1
            WHERE first_seen IS NULL
        """))

        conn.commit()

        print("✓ Migration 001 completed successfully")
        print("  - Added document_hash column (VARCHAR(32))")
        print("  - Added first_seen column (TIMESTAMP)")
        print("  - Added last_seen column (TIMESTAMP)")
        print("  - Added times_seen column (INTEGER)")
        print("  - Created index on document_hash")
        print("  - Backfilled existing leads")

if __name__ == "__main__":
    run_migration()
