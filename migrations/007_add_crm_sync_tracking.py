"""
Migration 007: Add CRM Sync Tracking

Adds CRM synchronization tracking fields to the leads table:
- crm_synced: Boolean flag indicating if lead was synced to CRM
- crm_provider: Which CRM system ('salesforce', 'hubspot', etc.)
- crm_lead_id: The lead's ID in the CRM system
- crm_url: Direct URL to view lead in CRM
- crm_synced_at: Timestamp of last sync
- crm_sync_error: Error message if sync failed

Also adds CRM configuration table for storing user CRM settings.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add CRM sync tracking columns and configuration table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='leads' AND column_name='crm_synced'
        """))

        if result.fetchone():
            print("✓ Migration already applied (columns exist)")
            return

        print("Running migration 007: Add CRM sync tracking...")

        # Add CRM tracking columns to leads table
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN crm_synced INTEGER DEFAULT 0 NOT NULL,
            ADD COLUMN crm_provider VARCHAR(50),
            ADD COLUMN crm_lead_id VARCHAR(100),
            ADD COLUMN crm_url VARCHAR(500),
            ADD COLUMN crm_synced_at TIMESTAMP,
            ADD COLUMN crm_sync_error TEXT
        """))

        # Create index on crm_synced for filtering
        conn.execute(text("""
            CREATE INDEX idx_leads_crm_synced ON leads(crm_synced)
        """))

        # Create index on crm_provider for filtering
        conn.execute(text("""
            CREATE INDEX idx_leads_crm_provider ON leads(crm_provider)
        """))

        # Create CRM configuration table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_configs (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL,
                enabled INTEGER DEFAULT 1 NOT NULL,
                credentials_encrypted TEXT NOT NULL,
                field_mapping JSON,
                default_owner_id VARCHAR(100),
                auto_sync_hot_leads INTEGER DEFAULT 1 NOT NULL,
                auto_sync_warm_leads INTEGER DEFAULT 0 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, provider)
            )
        """))

        # Create index on user_id for lookups
        conn.execute(text("""
            CREATE INDEX idx_crm_configs_user_id ON crm_configs(user_id)
        """))

        conn.commit()

        print("✓ Migration 007 completed successfully")
        print("  - Added CRM sync tracking columns to leads")
        print("  - Created indexes on crm_synced and crm_provider")
        print("  - Created crm_configs table for user CRM settings")

if __name__ == "__main__":
    run_migration()
