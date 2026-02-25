"""
Migration 005: Add Lead Status Tracking for ROI

Adds lead status pipeline fields to track sales progress and ROI:
- status: Lead pipeline stage (new → contacted → qualified → proposal → won/lost)
- deal_value: Deal value in USD (if won)
- contacted_date: When sales first reached out
- won_date: When deal closed
- lost_reason: Why deal was lost

These fields enable conversion tracking and ROI analytics.

Run this migration before deploying the lead status tracking feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add lead status tracking columns to leads table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='leads' AND column_name='status'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 005: Add lead status tracking...")

        # Add new columns
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN status VARCHAR(20) DEFAULT 'new' NOT NULL,
            ADD COLUMN deal_value INTEGER,
            ADD COLUMN contacted_date TIMESTAMP,
            ADD COLUMN won_date TIMESTAMP,
            ADD COLUMN lost_reason TEXT
        """))

        # Create index on status for filtering
        conn.execute(text("""
            CREATE INDEX idx_leads_status ON leads(status)
        """))

        # Backfill existing leads with default status
        conn.execute(text("""
            UPDATE leads
            SET status = 'new'
            WHERE status IS NULL
        """))

        conn.commit()

        print("✓ Migration 005 completed successfully")
        print("  - Added status column (VARCHAR(20), default 'new')")
        print("  - Added deal_value column (INTEGER)")
        print("  - Added contacted_date column (TIMESTAMP)")
        print("  - Added won_date column (TIMESTAMP)")
        print("  - Added lost_reason column (TEXT)")
        print("  - Created index on status")
        print("  - Backfilled existing leads with 'new' status")

if __name__ == "__main__":
    run_migration()
