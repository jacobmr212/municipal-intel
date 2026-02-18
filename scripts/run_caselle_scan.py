"""
Run production scans for all Caselle territory states.

Usage:
    DATABASE_URL=... python3 scripts/run_caselle_scan.py [--tier small|small-mid|both]

Runs both Small and Small-Mid tier scans, prints live progress and full results.
"""
import os, sys, uuid, time, argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database import SessionLocal, Scan, Lead, User, Municipality, MunicipalSource
from main import run_scan

STATES = ["UT", "CO", "ID", "WY", "MT", "NV", "NM"]
SOURCE_TYPES = ["meeting_minutes", "procurement", "state_portal"]


def create_scan(db, user_id: str, tier: str) -> str:
    scan = Scan(
        id=str(uuid.uuid4()),
        user_id=user_id,
        status="pending",
        config_json={
            "states": STATES,
            "population_tier": tier,
            "source_types": SOURCE_TYPES,
        },
        progress_phase="discovery",
        progress_pct=0,
        progress_message="Starting...",
    )
    db.add(scan)
    db.commit()
    return scan.id


def print_results(scan_id: str, tier: str):
    db = SessionLocal()
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    leads = (
        db.query(Lead)
        .filter(Lead.scan_id == scan_id)
        .order_by(Lead.relevance_score.desc())
        .all()
    )

    print(f"\n{'=' * 70}")
    print(f"SCAN RESULTS — {tier.upper()} tier")
    print(f"{'=' * 70}")
    print(f"Status:  {scan.status}")
    if scan.stats_json:
        s = scan.stats_json
        print(f"Stats:   {s.get('docs_scraped', 0)} docs scraped, {s.get('total_leads', 0)} leads")
        print(f"         HOT: {s.get('leads_hot', 0)}  WARM: {s.get('leads_warm', 0)}  COLD: {s.get('leads_cold', 0)}")

    hot = [l for l in leads if l.lead_type == "hot"]
    warm = [l for l in leads if l.lead_type == "warm"]
    cold = [l for l in leads if l.lead_type == "cold"]

    print(f"\nTotal leads: {len(leads)}  (HOT: {len(hot)}, WARM: {len(warm)}, COLD: {len(cold)})")

    if hot:
        print(f"\n--- HOT LEADS ({len(hot)}) ---")
        for l in hot:
            signals = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"\n  [{l.relevance_score:.0f}] {l.municipality}, {l.state} (pop {l.population:,})")
            print(f"  Title:   {l.title[:80]}")
            print(f"  URL:     {l.url[:80]}")
            print(f"  Date:    {l.date}")
            print(f"  Signals: {signals}")
            print(f"  Action:  {(l.recommended_action or '')[:100]}")

    if warm:
        print(f"\n--- WARM LEADS (top 10 of {len(warm)}) ---")
        for l in warm[:10]:
            signals = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"\n  [{l.relevance_score:.0f}] {l.municipality}, {l.state} (pop {l.population:,})")
            print(f"  Title:   {l.title[:80]}")
            print(f"  URL:     {l.url[:80]}")
            print(f"  Signals: {signals}")
            print(f"  Action:  {(l.recommended_action or '')[:100]}")

    if cold:
        print(f"\n--- COLD LEADS (top 5 of {len(cold)}) ---")
        for l in cold[:5]:
            signals = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"  [{l.relevance_score:.0f}] {l.municipality}, {l.state} — {signals}")

    # By state breakdown
    print(f"\n--- BY STATE ---")
    by_state = {}
    for l in leads:
        by_state.setdefault(l.state, {"hot": 0, "warm": 0, "cold": 0})
        by_state[l.state][l.lead_type] += 1
    for state in sorted(by_state):
        d = by_state[state]
        print(f"  {state}: HOT={d['hot']} WARM={d['warm']} COLD={d['cold']}")

    db.close()
    return leads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["small", "small-mid", "both"], default="both")
    args = parser.parse_args()

    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        print("ERROR: No users in DB")
        sys.exit(1)
    user_id = user.id
    print(f"Running as: {user.email}")

    tiers = ["small", "small-mid"] if args.tier == "both" else [args.tier]

    for tier in tiers:
        print(f"\n{'=' * 70}")
        print(f"STARTING {tier.upper()} TIER SCAN")
        print(f"States: {', '.join(STATES)}")
        print(f"{'=' * 70}\n", flush=True)

        scan_id = create_scan(db, user_id, tier)
        print(f"Scan ID: {scan_id}", flush=True)
        db.close()

        t0 = time.time()
        run_scan(scan_id, {
            "states": STATES,
            "population_tier": tier,
            "source_types": SOURCE_TYPES,
        })
        elapsed = time.time() - t0
        print(f"\nScan time: {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)

        print_results(scan_id, tier)

        # Reopen db for next scan
        db = SessionLocal()


if __name__ == "__main__":
    main()
