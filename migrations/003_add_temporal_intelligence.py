"""
Migration 003: Add Temporal Intelligence Fields

Adds urgency_score, deadline_date, days_until_deadline, decision_stage, and fiscal_year
columns to the leads table for temporal intelligence and urgency detection.

Run this migration before deploying the temporal intelligence feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add temporal intelligence columns to leads table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='leads' AND column_name='urgency_score'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 003: Add temporal intelligence fields...")

        # Add new columns
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN urgency_score INTEGER DEFAULT 0 NOT NULL,
            ADD COLUMN deadline_date TIMESTAMP,
            ADD COLUMN days_until_deadline INTEGER,
            ADD COLUMN decision_stage VARCHAR(20),
            ADD COLUMN fiscal_year VARCHAR(10)
        """))

        # Create indexes for frequently queried fields
        conn.execute(text("""
            CREATE INDEX idx_leads_urgency_score ON leads(urgency_score)
        """))

        conn.execute(text("""
            CREATE INDEX idx_leads_deadline_date ON leads(deadline_date)
        """))

        # Backfill existing leads with default values
        conn.execute(text("""
            UPDATE leads
            SET urgency_score = 0, decision_stage = 'unknown'
            WHERE urgency_score IS NULL OR decision_stage IS NULL
        """))

        conn.commit()

        print("✓ Migration 003 completed successfully")
        print("  - Added urgency_score column (INTEGER, default 0)")
        print("  - Added deadline_date column (TIMESTAMP)")
        print("  - Added days_until_deadline column (INTEGER)")
        print("  - Added decision_stage column (VARCHAR(20))")
        print("  - Added fiscal_year column (VARCHAR(10))")
        print("  - Created indexes on urgency_score and deadline_date")
        print("  - Backfilled existing leads with default values")

if __name__ == "__main__":
    run_migration()
