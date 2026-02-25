#!/usr/bin/env python3
"""
Migration 009: Add customer_status column to leads table

Adds customer_status field to track whether lead is an existing Caselle customer
or a new opportunity. This enables prioritization of retention vs acquisition.

Usage:
    railway run python3 migrations/009_add_customer_status.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Add customer_status column to leads table."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("=" * 70)
    print("MIGRATION 009: Add customer_status to leads")
    print("=" * 70)
    print()

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'leads'
                AND column_name = 'customer_status';
            """))

            if result.fetchone():
                print("✓ customer_status column already exists — skipping")
                trans.commit()
                return

            print("Adding customer_status column to leads table...")

            # Add customer_status column
            # Values: 'existing_customer' | 'new_opportunity' | null (unknown)
            conn.execute(text("""
                ALTER TABLE leads
                ADD COLUMN customer_status VARCHAR(20);
            """))
            print("  ✓ Added customer_status column")

            # Create index for filtering
            conn.execute(text("""
                CREATE INDEX idx_leads_customer_status
                ON leads(customer_status);
            """))
            print("  ✓ Created index on customer_status")

            # Update existing leads based on signal analysis
            # If "direct_mentions" signal is present → existing_customer
            # Otherwise → new_opportunity
            conn.execute(text("""
                UPDATE leads
                SET customer_status = CASE
                    WHEN signal_matches_json::text LIKE '%direct_mentions%'
                    THEN 'existing_customer'
                    ELSE 'new_opportunity'
                END
                WHERE customer_status IS NULL;
            """))

            result = conn.execute(text("""
                SELECT customer_status, COUNT(*)
                FROM leads
                WHERE customer_status IS NOT NULL
                GROUP BY customer_status;
            """))

            print("\n  Updated existing leads:")
            for row in result:
                print(f"    - {row[0]}: {row[1]} leads")

            # Commit transaction
            trans.commit()

            print("\n✅ Migration 009 completed successfully!")
            print()

        except Exception as e:
            # Rollback on error
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run_migration()
