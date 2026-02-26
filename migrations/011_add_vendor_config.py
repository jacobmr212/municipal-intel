#!/usr/bin/env python3
"""
Migration 011: Add vendor configuration to users table

Adds vendor_name and vendor_competitors columns to enable vendor-neutral scanning.
Users can configure their ERP vendor and competitors for personalized lead classification.

Usage:
    railway run python3 migrations/011_add_vendor_config.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Add vendor configuration columns to users table."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("=" * 70)
    print("MIGRATION 011: Add vendor configuration to users")
    print("=" * 70)
    print()

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            # Check if columns already exist
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name IN ('vendor_name', 'vendor_competitors');
            """))

            existing_columns = [row[0] for row in result]

            if 'vendor_name' not in existing_columns:
                print("Adding vendor_name column to users table...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN vendor_name VARCHAR(100);
                """))
                print("  ✓ Added vendor_name column")
            else:
                print("✓ vendor_name column already exists — skipping")

            if 'vendor_competitors' not in existing_columns:
                print("Adding vendor_competitors column to users table...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN vendor_competitors JSON;
                """))
                print("  ✓ Added vendor_competitors column")
            else:
                print("✓ vendor_competitors column already exists — skipping")

            # Optional: Set default vendor for existing consultant/admin users
            # This maintains backward compatibility with Caselle-focused setup
            print("\nSetting default vendor for existing consultant/admin users...")
            result = conn.execute(text("""
                UPDATE users
                SET vendor_name = 'Caselle',
                    vendor_competitors = '["Tyler Technologies", "CentralSquare", "Infor", "SAP"]'::json
                WHERE (role = 'consultant' OR role = 'admin')
                AND vendor_name IS NULL;
            """))
            print(f"  ✓ Updated {result.rowcount} users with default Caselle configuration")

            # Commit transaction
            trans.commit()

            print("\n✅ Migration 011 completed successfully!")
            print("\nUsers can now configure their vendor in scanner settings.")
            print("Existing consultants defaulted to Caselle for backward compatibility.")
            print()

        except Exception as e:
            # Rollback on error
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run_migration()
