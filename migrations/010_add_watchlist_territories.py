#!/usr/bin/env python3
"""
Migration 010: Add watchlist and territories tables

Creates two tables for user-specific features:
- watchlist: Municipalities marked by user for monitoring
- territories: State/region assignments for users (filters Feed)

Usage:
    railway run python3 migrations/010_add_watchlist_territories.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Create watchlist and territories tables."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create engine
    engine = create_engine(database_url)

    print("=" * 70)
    print("MIGRATION 010: Add watchlist and territories tables")
    print("=" * 70)
    print()

    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()

        try:
            # Check if tables already exist
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('watchlist', 'territories');
            """))

            existing_tables = [row[0] for row in result]

            # Create watchlist table
            if 'watchlist' not in existing_tables:
                print("Creating watchlist table...")
                conn.execute(text("""
                    CREATE TABLE watchlist (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        municipality_id INTEGER NOT NULL REFERENCES municipalities(id) ON DELETE CASCADE,
                        notes TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                print("  ✓ Created watchlist table")

                # Create indexes
                conn.execute(text("""
                    CREATE INDEX idx_watchlist_user_id ON watchlist(user_id);
                """))
                conn.execute(text("""
                    CREATE INDEX idx_watchlist_municipality_id ON watchlist(municipality_id);
                """))
                conn.execute(text("""
                    CREATE INDEX idx_watchlist_created_at ON watchlist(created_at);
                """))
                print("  ✓ Created watchlist indexes")

                # Unique constraint: user can only watch a municipality once
                conn.execute(text("""
                    CREATE UNIQUE INDEX idx_watchlist_unique_user_municipality
                    ON watchlist(user_id, municipality_id);
                """))
                print("  ✓ Created unique constraint on watchlist")
            else:
                print("✓ watchlist table already exists — skipping")

            # Create territories table
            if 'territories' not in existing_tables:
                print("\nCreating territories table...")
                conn.execute(text("""
                    CREATE TABLE territories (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        state VARCHAR(2) NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                print("  ✓ Created territories table")

                # Create indexes
                conn.execute(text("""
                    CREATE INDEX idx_territories_user_id ON territories(user_id);
                """))
                conn.execute(text("""
                    CREATE INDEX idx_territories_state ON territories(state);
                """))
                print("  ✓ Created territories indexes")

                # Unique constraint: user can only have a state once
                conn.execute(text("""
                    CREATE UNIQUE INDEX idx_territories_unique_user_state
                    ON territories(user_id, state);
                """))
                print("  ✓ Created unique constraint on territories")
            else:
                print("✓ territories table already exists — skipping")

            # Commit transaction
            trans.commit()

            print("\n✅ Migration 010 completed successfully!")
            print()

        except Exception as e:
            # Rollback on error
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run_migration()
