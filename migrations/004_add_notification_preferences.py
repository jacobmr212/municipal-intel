"""
Migration 004: Add Notification Preferences

Adds email alert preferences to the users table:
- email_alerts_enabled: Master switch for all email notifications
- alert_on_hot_leads: Immediate alerts for hot leads
- alert_on_urgent_leads: Immediate alerts for urgent leads (urgency >= 60)
- daily_digest_enabled: Daily summary email
- min_urgency_for_alert: Minimum urgency score threshold

Run this migration before deploying the email alerts feature.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add notification preference columns to users table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='email_alerts_enabled'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 004: Add notification preferences...")

        # Add new columns
        conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN email_alerts_enabled INTEGER DEFAULT 1 NOT NULL,
            ADD COLUMN alert_on_hot_leads INTEGER DEFAULT 1 NOT NULL,
            ADD COLUMN alert_on_urgent_leads INTEGER DEFAULT 1 NOT NULL,
            ADD COLUMN daily_digest_enabled INTEGER DEFAULT 0 NOT NULL,
            ADD COLUMN min_urgency_for_alert INTEGER DEFAULT 60 NOT NULL
        """))

        # Backfill existing users with default values (alerts enabled)
        conn.execute(text("""
            UPDATE users
            SET
                email_alerts_enabled = 1,
                alert_on_hot_leads = 1,
                alert_on_urgent_leads = 1,
                daily_digest_enabled = 0,
                min_urgency_for_alert = 60
            WHERE email_alerts_enabled IS NULL
        """))

        conn.commit()

        print("✓ Migration 004 completed successfully")
        print("  - Added email_alerts_enabled column (INTEGER, default 1)")
        print("  - Added alert_on_hot_leads column (INTEGER, default 1)")
        print("  - Added alert_on_urgent_leads column (INTEGER, default 1)")
        print("  - Added daily_digest_enabled column (INTEGER, default 0)")
        print("  - Added min_urgency_for_alert column (INTEGER, default 60)")
        print("  - Backfilled existing users with email alerts enabled")

if __name__ == "__main__":
    run_migration()
