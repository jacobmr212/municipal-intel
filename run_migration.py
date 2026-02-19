#!/usr/bin/env python3
"""
Run database migrations for the Assessment platform.
Executes SQL files in the migrations/ directory.
"""

import os
import sys
from sqlalchemy import create_engine, text

def run_migration():
    """Execute the assessment tables migration."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    # Read migration file
    migration_file = "migrations/001_create_assessment_tables.sql"
    print(f"Reading migration: {migration_file}")

    with open(migration_file, 'r') as f:
        sql_content = f.read()

    # Execute migration
    print("Executing migration...")
    try:
        with engine.begin() as conn:
            # Split on semicolons and execute each statement
            statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

            for i, statement in enumerate(statements, 1):
                if statement:
                    print(f"  Executing statement {i}/{len(statements)}...")
                    conn.execute(text(statement))

        print("✅ Migration completed successfully!")

        # Verify tables exist
        print("\nVerifying tables...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('Assessment', 'AssessmentSection')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]

            if tables:
                print(f"✅ Found tables: {', '.join(tables)}")
            else:
                print("⚠️  Warning: Tables not found after migration")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
