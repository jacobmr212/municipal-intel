"""
Migrate local SQLite enrichment data to production Neon PostgreSQL.

Uses psycopg2 directly (bypasses SQLAlchemy pool issues on Mac).
Copies municipalities and municipal_sources, preserving FK relationships.
Only migrates records that don't already exist in the target DB.
"""

import os
import sys
import sqlite3
from datetime import datetime

# ── Source: local SQLite ─────────────────────────────────────────────────────
SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "municipal_intel.db")

if not os.path.exists(SQLITE_PATH):
    print(f"ERROR: SQLite DB not found at {SQLITE_PATH}")
    sys.exit(1)

# ── Target: production Postgres (must be set in env) ─────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set.")
    sys.exit(1)

import psycopg2
from urllib.parse import urlparse

# Parse the DATABASE_URL
url = DATABASE_URL.replace("postgres://", "postgresql://")
parsed = urlparse(url)
# Strip query string params for psycopg2
db_config = {
    "host": parsed.hostname,
    "port": parsed.port or 5432,
    "dbname": parsed.path.lstrip("/"),
    "user": parsed.username,
    "password": parsed.password,
    "sslmode": "require",
    "connect_timeout": 15,
}


def get_pg():
    return psycopg2.connect(**db_config)


def migrate():
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {parsed.hostname}/{parsed.path.lstrip('/')}")

    # ── Connect to SQLite ────────────────────────────────────────────────────
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row

    # ── Connect to Postgres ──────────────────────────────────────────────────
    print("\nConnecting to Neon PostgreSQL...")
    pg = get_pg()
    pgc = pg.cursor()
    print("Connected.")

    def parse_dt(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(v, fmt)
            except (ValueError, TypeError):
                pass
        return None

    try:
        # ── Step 1: Municipalities ───────────────────────────────────────────
        src_munis = src.execute("SELECT * FROM municipalities").fetchall()
        print(f"\nSource municipalities: {len(src_munis)}")

        pgc.execute("SELECT id FROM municipalities")
        existing_ids = set(r[0] for r in pgc.fetchall())
        print(f"Already in target: {len(existing_ids)}")

        inserted_munis = 0
        muni_id_map = {}

        for row in src_munis:
            sid = row["id"]
            muni_id_map[sid] = sid

            if sid in existing_ids:
                continue

            pgc.execute("""
                INSERT INTO municipalities
                    (id, name, state, population, domain, domain_status,
                     domain_verified_at, resolved_url, created_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                sid,
                row["name"],
                row["state"],
                row["population"] or 0,
                row["domain"],
                row["domain_status"] or "unverified",
                parse_dt(row["domain_verified_at"]),
                row["resolved_url"],
                parse_dt(row["created_at"]) or datetime.utcnow(),
                parse_dt(row["updated_at"]) or datetime.utcnow(),
            ))
            inserted_munis += 1

        pg.commit()
        print(f"✓ Municipalities inserted: {inserted_munis}")

        # ── Step 2: Municipal Sources ────────────────────────────────────────
        src_sources = src.execute("SELECT * FROM municipal_sources").fetchall()
        print(f"\nSource municipal_sources: {len(src_sources)}")

        pgc.execute("SELECT url FROM municipal_sources")
        existing_urls = set(r[0] for r in pgc.fetchall())
        print(f"Already in target: {len(existing_urls)}")

        inserted_sources = 0
        skipped_sources = 0

        for row in src_sources:
            url_val = row["url"]
            municipality_id = row["municipality_id"]

            if url_val in existing_urls:
                skipped_sources += 1
                continue

            if municipality_id not in muni_id_map:
                skipped_sources += 1
                continue

            pgc.execute("""
                INSERT INTO municipal_sources
                    (id, municipality_id, url, source_type, platform, confidence,
                     last_scraped_at, last_scrape_success, scrape_error,
                     discovered_at, discovered_by_pattern)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (
                row["id"],
                muni_id_map[municipality_id],
                url_val,
                row["source_type"],
                row["platform"],
                row["confidence"] or 0.7,
                parse_dt(row["last_scraped_at"]),
                row["last_scrape_success"],
                row["scrape_error"],
                parse_dt(row["discovered_at"]) or datetime.utcnow(),
                row["discovered_by_pattern"],
            ))
            inserted_sources += 1

        pg.commit()
        print(f"✓ Sources inserted: {inserted_sources} (skipped: {skipped_sources})")

        # ── Step 3: Summary ──────────────────────────────────────────────────
        pgc.execute("SELECT COUNT(*) FROM municipalities")
        total_munis = pgc.fetchone()[0]

        pgc.execute("SELECT COUNT(*) FROM municipal_sources")
        total_sources = pgc.fetchone()[0]

        pgc.execute("""
            SELECT state, COUNT(*) as cnt
            FROM municipalities
            WHERE domain_status = 'verified'
            GROUP BY state
            ORDER BY state
        """)
        verified = pgc.fetchall()

        pgc.execute("""
            SELECT source_type, COUNT(*) as cnt
            FROM municipal_sources
            GROUP BY source_type
            ORDER BY cnt DESC
        """)
        by_type = pgc.fetchall()

        print(f"\n=== Production DB After Migration ===")
        print(f"Total municipalities: {total_munis}")
        print(f"Total sources:        {total_sources}")
        print(f"\nVerified municipalities by state:")
        for state, cnt in verified:
            print(f"  {state}: {cnt}")
        print(f"\nSources by type:")
        for stype, cnt in by_type:
            print(f"  {stype}: {cnt}")

    except Exception as e:
        pg.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        src.close()
        pgc.close()
        pg.close()


if __name__ == "__main__":
    migrate()
