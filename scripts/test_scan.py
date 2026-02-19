"""
Run a test scan directly (without FastAPI) against production Neon DB.

Usage:
    DATABASE_URL=... python3 scripts/test_scan.py
"""
import os, sys, uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "")

from src.database import SessionLocal, Scan, Lead, User

# ── Config ────────────────────────────────────────────────────────────────────
STATES = ["UT"]
POPULATION_TIER = "small"   # 2500-10000

# ── Get or create a test user ─────────────────────────────────────────────────
db = SessionLocal()

user = db.query(User).first()
if not user:
    print("ERROR: No users in DB — run migration first")
    sys.exit(1)
print(f"Running as: {user.email}")

# ── Create scan record ────────────────────────────────────────────────────────
scan = Scan(
    id=str(uuid.uuid4()),
    user_id=user.id,
    status="pending",
    config_json={"states": STATES, "population_tier": POPULATION_TIER, "source_types": ["meeting_minutes", "procurement", "state_portal"]},
    progress_phase="discovery",
    progress_pct=0,
    progress_message="Starting test scan...",
    stats_json=None,
)
db.add(scan)
db.commit()
scan_id = scan.id
print(f"Scan ID: {scan_id}")
db.close()

# ── Run the scan pipeline from main.py ────────────────────────────────────────
# Import the run_scan function from main
from main import run_scan

print(f"\nStarting scan: states={STATES}, tier={POPULATION_TIER}")
print("=" * 60)

run_scan(scan_id, {"states": STATES, "population_tier": POPULATION_TIER, "source_types": ["meeting_minutes", "procurement", "state_portal"]})

# ── Report results ────────────────────────────────────────────────────────────
db = SessionLocal()
scan = db.query(Scan).filter(Scan.id == scan_id).first()
leads = db.query(Lead).filter(Lead.scan_id == scan_id).order_by(Lead.relevance_score.desc()).all()

print(f"\n{'=' * 60}")
print(f"SCAN COMPLETE")
print(f"Status:  {scan.status}")
print(f"Stats:   {scan.stats_json}")
print(f"Leads:   {len(leads)}")

if leads:
    hot = [l for l in leads if l.lead_type == "hot"]
    warm = [l for l in leads if l.lead_type == "warm"]
    cold = [l for l in leads if l.lead_type == "cold"]
    print(f"\n  HOT ({len(hot)}): ", [f"{l.municipality} ({l.relevance_score:.0f})" for l in hot])
    print(f"  WARM ({len(warm)}): ", [f"{l.municipality} ({l.relevance_score:.0f})" for l in warm])
    print(f"  COLD ({len(cold)}): ", [f"{l.municipality} ({l.relevance_score:.0f})" for l in cold])

    print(f"\nTop 5 leads:")
    for l in leads[:5]:
        print(f"\n  [{l.lead_type.upper()}] {l.municipality}, {l.state} — score: {l.relevance_score:.1f}")
        print(f"  Title: {l.title[:80]}")
        print(f"  URL:   {l.url[:80]}")
        print(f"  Action: {l.recommended_action}")

db.close()
