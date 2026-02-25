#!/usr/bin/env python3
"""
Migration 008: Add Government Entities Table

Adds support for discovering multiple government entities per municipality:
- School districts
- Fire districts
- Libraries
- Water/sewer districts
- Parks & recreation
- County government

Each entity is a separate sales opportunity with its own ERP budget!
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text

def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        sys.exit(1)

    engine = create_engine(database_url)

    print("=" * 70)
    print("MIGRATION 008: Add Government Entities Table")
    print("=" * 70)

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'government_entities'
            );
        """))
        exists = result.scalar()

        if exists:
            print("✓ government_entities table already exists — skipping")
            return

        # Create government_entities table
        print("\n1. Creating government_entities table...")
        conn.execute(text("""
            CREATE TABLE government_entities (
                id VARCHAR(36) PRIMARY KEY,
                municipality_id VARCHAR(36) NOT NULL REFERENCES municipalities(id) ON DELETE CASCADE,
                entity_type VARCHAR(50) NOT NULL,
                name VARCHAR(200) NOT NULL,
                domain VARCHAR(200),
                url VARCHAR(500),
                confidence FLOAT,
                notes TEXT,
                sources_discovered INTEGER DEFAULT 0,
                last_enriched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))
        print("  ✓ government_entities table created")

        # Create indexes
        print("\n2. Creating indexes...")
        conn.execute(text("""
            CREATE INDEX idx_government_entities_municipality_id
            ON government_entities(municipality_id);
        """))
        print("  ✓ Index on municipality_id")

        conn.execute(text("""
            CREATE INDEX idx_government_entities_entity_type
            ON government_entities(entity_type);
        """))
        print("  ✓ Index on entity_type")

        conn.execute(text("""
            CREATE INDEX idx_government_entities_confidence
            ON government_entities(confidence);
        """))
        print("  ✓ Index on confidence")

        # Add entity_id column to municipal_sources to link sources to specific entities
        print("\n3. Adding entity_id to municipal_sources...")
        conn.execute(text("""
            ALTER TABLE municipal_sources
            ADD COLUMN entity_id VARCHAR(36) REFERENCES government_entities(id) ON DELETE CASCADE;
        """))
        print("  ✓ entity_id column added")

        conn.execute(text("""
            CREATE INDEX idx_municipal_sources_entity_id
            ON municipal_sources(entity_id);
        """))
        print("  ✓ Index on entity_id")

        conn.commit()

        print("\n" + "=" * 70)
        print("✅ Migration 008 completed successfully!")
        print("=" * 70)
        print("\nNew capabilities:")
        print("  • Discover school districts (separate ERP budgets!)")
        print("  • Discover fire districts")
        print("  • Discover library districts")
        print("  • Discover water/sewer districts")
        print("  • Discover parks & recreation districts")
        print("  • Discover county government")
        print("\nEach entity = separate sales opportunity! 💰")
        print()


if __name__ == "__main__":
    run_migration()
