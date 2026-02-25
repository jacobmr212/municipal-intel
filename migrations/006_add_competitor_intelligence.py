"""
Migration 006: Add Competitor Intelligence Fields

Adds competitor analysis fields to the leads table:
- competitors_mentioned: JSON list of competitor names detected
- competitive_context: Strategic context summary for sales team
- existing_vendor: Current ERP vendor if detected

These fields enable competitive analysis and strategic positioning.

Run this migration before deploying the competitor intelligence feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add competitor intelligence columns to leads table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='leads' AND column_name='competitors_mentioned'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 006: Add competitor intelligence...")

        # Add new columns
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN competitors_mentioned JSON,
            ADD COLUMN competitive_context TEXT,
            ADD COLUMN existing_vendor VARCHAR(100)
        """))

        # Create index on existing_vendor for filtering
        conn.execute(text("""
            CREATE INDEX idx_leads_existing_vendor ON leads(existing_vendor)
        """))

        conn.commit()

        print("✓ Migration 006 completed successfully")
        print("  - Added competitors_mentioned column (JSON)")
        print("  - Added competitive_context column (TEXT)")
        print("  - Added existing_vendor column (VARCHAR(100))")
        print("  - Created index on existing_vendor")

if __name__ == "__main__":
    run_migration()
