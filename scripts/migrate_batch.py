"""
Fast batch migration: SQLite → Neon PostgreSQL using execute_values.
"""
import os, sys, sqlite3, psycopg2, psycopg2.extras
from datetime import datetime
from urllib.parse import urlparse

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "municipal_intel.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not os.path.exists(SQLITE_PATH):
    print(f"ERROR: SQLite not found: {SQLITE_PATH}"); sys.exit(1)
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set"); sys.exit(1)

parsed = urlparse(DATABASE_URL)
db_config = {
    "host": parsed.hostname, "port": parsed.port or 5432,
    "dbname": parsed.path.lstrip("/"), "user": parsed.username,
    "password": parsed.password, "sslmode": "require", "connect_timeout": 30,
}

def parse_dt(v):
    if not v: return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(v, fmt)
        except: pass
    return None

print("Connecting to Neon...", flush=True)
pg = psycopg2.connect(**db_config)
pgc = pg.cursor()
print("Connected.", flush=True)

src = sqlite3.connect(SQLITE_PATH)
src.row_factory = sqlite3.Row

# ── Municipalities ────────────────────────────────────────────────────────────
rows = src.execute("SELECT * FROM municipalities").fetchall()
print(f"Source: {len(rows)} municipalities", flush=True)

pgc.execute("SELECT id FROM municipalities")
existing_ids = set(r[0] for r in pgc.fetchall())
print(f"Already in PG: {len(existing_ids)}", flush=True)

now = datetime.utcnow()
muni_data = []
id_map = {}
for r in rows:
    sid = r["id"]
    id_map[sid] = sid
    if sid in existing_ids:
        continue
    muni_data.append((
        sid, r["name"], r["state"], r["population"] or 0,
        r["domain"], r["domain_status"] or "unverified",
        parse_dt(r["domain_verified_at"]), r["resolved_url"],
        parse_dt(r["created_at"]) or now, parse_dt(r["updated_at"]) or now,
    ))

if muni_data:
    psycopg2.extras.execute_values(pgc, """
        INSERT INTO municipalities
            (id, name, state, population, domain, domain_status,
             domain_verified_at, resolved_url, created_at, updated_at)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
    """, muni_data, page_size=500)
    pg.commit()
print(f"✓ Inserted {len(muni_data)} municipalities", flush=True)

# ── Municipal Sources ─────────────────────────────────────────────────────────
srows = src.execute("SELECT * FROM municipal_sources").fetchall()
print(f"Source: {len(srows)} sources", flush=True)

pgc.execute("SELECT url FROM municipal_sources")
existing_urls = set(r[0] for r in pgc.fetchall())
print(f"Already in PG: {len(existing_urls)}", flush=True)

src_data = []
skipped = 0
for r in srows:
    if r["url"] in existing_urls or r["municipality_id"] not in id_map:
        skipped += 1
        continue
    src_data.append((
        r["id"], id_map[r["municipality_id"]], r["url"],
        r["source_type"], r["platform"], r["confidence"] or 0.7,
        parse_dt(r["last_scraped_at"]), r["last_scrape_success"], r["scrape_error"],
        parse_dt(r["discovered_at"]) or now, r["discovered_by_pattern"],
    ))

if src_data:
    psycopg2.extras.execute_values(pgc, """
        INSERT INTO municipal_sources
            (id, municipality_id, url, source_type, platform, confidence,
             last_scraped_at, last_scrape_success, scrape_error,
             discovered_at, discovered_by_pattern)
        VALUES %s
        ON CONFLICT (url) DO NOTHING
    """, src_data, page_size=500)
    pg.commit()
print(f"✓ Inserted {len(src_data)} sources (skipped {skipped})", flush=True)

# ── Summary ───────────────────────────────────────────────────────────────────
pgc.execute("SELECT COUNT(*) FROM municipalities")
total_m = pgc.fetchone()[0]
pgc.execute("SELECT COUNT(*) FROM municipal_sources")
total_s = pgc.fetchone()[0]
pgc.execute("""
    SELECT state, COUNT(*) FROM municipalities
    WHERE domain_status='verified'
    GROUP BY state ORDER BY state
""")
verified = pgc.fetchall()
pgc.execute("""
    SELECT source_type, COUNT(*) FROM municipal_sources
    GROUP BY source_type ORDER BY COUNT(*) DESC
""")
by_type = pgc.fetchall()

print(f"\n=== Production DB ===")
print(f"Municipalities: {total_m}")
print(f"Sources:        {total_s}")
print(f"\nVerified by state:")
for state, cnt in verified:
    print(f"  {state}: {cnt}")
print(f"\nSources by type:")
for st, cnt in by_type:
    print(f"  {st}: {cnt}")

pg.close()
src.close()
print("\nDone!")
