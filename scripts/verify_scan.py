"""
Standalone verification scan for CO + ID.

Does not import main.py (avoids FastAPI dependency).
Inlines run_scan logic directly.

Run:
    DATABASE_URL=... python3 scripts/verify_scan.py [--states CO ID] [--tier small|small-mid|both]
"""
import os, sys, uuid, time, argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database import SessionLocal, Scan, Lead, Municipality, MunicipalSource, User
from src.scraper import MunicipalScraper
from src.analyzer import DocumentAnalyzer
from src.discovery import SourceDiscovery

POPULATION_TIERS = {
    "micro":      (0,       2500),
    "small":      (2500,    10000),
    "small-mid":  (10000,   25000),
    "mid-market": (25000,   75000),
    "upper-mid":  (75000,   150000),
    "large":      (150000,  999999999),
}


def get_population_range(tier: str) -> tuple:
    return POPULATION_TIERS.get(tier, (0, 999999999))


def update_scan_progress(db, scan_id, phase, pct, message):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if scan:
        scan.progress_phase = phase
        scan.progress_pct = pct
        scan.progress_message = message
        db.commit()
    print(f"  [{pct:3d}%] {phase}: {message}", flush=True)


def run_scan(scan_id: str, config: dict):
    db = SessionLocal()

    scraper = MunicipalScraper(delay=1.5, timeout=8, max_docs=10)
    analyzer = DocumentAnalyzer(use_llm=False)
    discovery = SourceDiscovery(request_delay=1.0, timeout=8)

    try:
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            return

        scan.status = "running"
        db.commit()

        states = config.get("states", [])
        population_tier = config.get("population_tier", "small")
        source_types = config.get("source_types", ["meeting_minutes", "procurement"])

        pop_min, pop_max = get_population_range(population_tier)

        update_scan_progress(db, scan_id, "discovery", 0, "Loading municipalities...")

        municipalities = db.query(Municipality).filter(
            Municipality.state.in_(states),
            Municipality.population >= pop_min,
            Municipality.population <= pop_max
        ).all()

        # Snapshot municipality data into plain tuples immediately.
        # SQLAlchemy expires all loaded objects on commit (expire_on_commit=True),
        # so after db.commit() or db.close() the ORM objects become detached/expired.
        # Using plain tuples avoids lazy-load failures when the session cycles.
        muni_rows = [(m.id, m.name, m.state, m.population) for m in municipalities]
        total_cities = len(muni_rows)
        update_scan_progress(db, scan_id, "discovery", 10, f"Found {total_cities} cities to scan")

        sources_found = 0
        docs_scraped = 0
        leads_hot = 0
        leads_warm = 0
        leads_cold = 0

        for idx, (muni_id, muni_name, muni_state, muni_pop) in enumerate(muni_rows):
            progress_pct = 10 + int((idx / total_cities) * 80)
            update_scan_progress(db, scan_id, "scraping", progress_pct, f"Scanning {muni_name}, {muni_state}...")

            enriched_sources = db.query(MunicipalSource).filter(
                MunicipalSource.municipality_id == muni_id
            ).all()

            if not enriched_sources:
                continue

            # Collect source data before closing DB — scraping can take minutes
            # and Neon will drop idle SSL connections, causing PendingRollbackError.
            source_snapshots = [
                (s.url, s.source_type, s.platform, s.confidence,
                 s.municipality_id, muni_name, muni_state, muni_pop)
                for s in enriched_sources
            ]
            sources_found += len(enriched_sources)
            db.close()
            db = None

            for (src_url, src_type, src_platform, src_conf,
                 src_muni_id, muni_name, muni_state, muni_pop) in source_snapshots:

                # Rebuild a lightweight source object for the scraper.
                # The scraper accesses source.municipality.name/.state so we
                # include a mock municipality to avoid lazy-load on closed session.
                class _Muni:
                    pass
                muni_mock = _Muni()
                muni_mock.name = muni_name
                muni_mock.state = muni_state
                muni_mock.population = muni_pop

                class _Src:
                    pass
                src = _Src()
                src.url = src_url
                src.source_type = src_type
                src.platform = src_platform
                src.confidence = src_conf
                src.municipality_id = src_muni_id
                src.municipality = muni_mock

                try:
                    scraped_docs = scraper.scrape_source(src)
                    docs_scraped += len(scraped_docs)

                    new_leads = []
                    for doc in scraped_docs:
                        result = analyzer.analyze_document(
                            doc,
                            population=muni_pop,
                            min_score=30,
                            source_type=src_type
                        )

                        if result:
                            new_leads.append(Lead(
                                scan_id=scan_id,
                                municipality=result.municipality,
                                state=result.state,
                                population=result.population,
                                title=result.title,
                                url=result.url,
                                date=result.date,
                                source_type=result.source_type,
                                relevance_score=result.relevance_score,
                                lead_type=result.lead_type,
                                recommended_action=result.recommended_action,
                                signal_matches_json={
                                    m.signal_type: {
                                        "keyword": m.keyword,
                                        "context": m.context,
                                        "weight": m.weight
                                    }
                                    for m in result.signal_matches
                                }
                            ))

                    # Reopen DB only when ready to write
                    if new_leads:
                        db = SessionLocal()
                        for lead in new_leads:
                            db.add(lead)
                            db.commit()
                            if lead.lead_type == "hot":
                                leads_hot += 1
                            elif lead.lead_type == "warm":
                                leads_warm += 1
                            else:
                                leads_cold += 1
                        db.close()
                        db = None

                except Exception as e:
                    print(f"    Error scraping {src_url}: {str(e)[:80]}")
                    continue

            # Reopen DB for next city's progress update
            db = SessionLocal()

        update_scan_progress(db, scan_id, "complete", 100, "Scan complete")

        # Re-fetch scan from current session (original session was closed during loop)
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if scan:
            scan.status = "completed"
            scan.completed_at = datetime.utcnow()
            scan.stats_json = {
                "sources_found": sources_found,
                "docs_scraped": docs_scraped,
                "leads_hot": leads_hot,
                "leads_warm": leads_warm,
                "leads_cold": leads_cold,
                "total_leads": leads_hot + leads_warm + leads_cold
            }
            db.commit()

    except Exception as e:
        import traceback
        traceback.print_exc()
        if db is None:
            db = SessionLocal()
        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if scan:
            scan.status = "failed"
            scan.progress_message = f"Error: {str(e)}"
            db.commit()

    finally:
        if db is not None:
            db.close()


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
    print(f"Status: {scan.status}")
    if scan.stats_json:
        s = scan.stats_json
        print(f"Stats:  {s.get('docs_scraped',0)} docs scraped, {s.get('total_leads',0)} leads")
        print(f"        HOT:{s.get('leads_hot',0)}  WARM:{s.get('leads_warm',0)}  COLD:{s.get('leads_cold',0)}")

    hot = [l for l in leads if l.lead_type == "hot"]
    warm = [l for l in leads if l.lead_type == "warm"]
    cold = [l for l in leads if l.lead_type == "cold"]
    print(f"\nTotal: {len(leads)} leads  (HOT:{len(hot)} WARM:{len(warm)} COLD:{len(cold)})")

    if hot:
        print(f"\n--- HOT LEADS ({len(hot)}) ---")
        for l in hot:
            sigs = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"\n  [{l.relevance_score:.0f}] {l.municipality}, {l.state} (pop {l.population:,})")
            print(f"  Title:   {l.title[:80]}")
            print(f"  URL:     {l.url[:80]}")
            print(f"  Date:    {l.date}")
            print(f"  Signals: {sigs}")
            print(f"  Action:  {(l.recommended_action or '')[:100]}")

    if warm:
        print(f"\n--- WARM LEADS (top 10 of {len(warm)}) ---")
        for l in warm[:10]:
            sigs = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"\n  [{l.relevance_score:.0f}] {l.municipality}, {l.state} (pop {l.population:,})")
            print(f"  Title:   {l.title[:80]}")
            print(f"  Signals: {sigs}")

    if cold:
        print(f"\n--- COLD LEADS (top 5 of {len(cold)}) ---")
        for l in cold[:5]:
            sigs = list(l.signal_matches_json.keys()) if l.signal_matches_json else []
            print(f"  [{l.relevance_score:.0f}] {l.municipality}, {l.state} — {sigs}")

    print(f"\n--- BY STATE ---")
    by_state = {}
    for l in leads:
        by_state.setdefault(l.state, {"hot": 0, "warm": 0, "cold": 0})
        by_state[l.state][l.lead_type] += 1
    for state in sorted(by_state):
        d = by_state[state]
        print(f"  {state}: HOT={d['hot']} WARM={d['warm']} COLD={d['cold']}")

    db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", nargs="+", default=["CO", "ID"])
    parser.add_argument("--tier", choices=["small", "small-mid", "both"], default="both")
    args = parser.parse_args()

    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        print("ERROR: No users in DB")
        sys.exit(1)
    user_id = user.id
    print(f"Running as: {user.email}")
    print(f"States: {', '.join(args.states)}")

    # Print source summary
    print(f"\nSources in DB:")
    for state in args.states:
        total = db.query(MunicipalSource).join(Municipality).filter(Municipality.state == state).count()
        mm = db.query(MunicipalSource).join(Municipality).filter(
            Municipality.state == state, MunicipalSource.source_type == "meeting_minutes"
        ).count()
        print(f"  {state}: {total} total ({mm} meeting_minutes)")

    db.close()

    tiers = ["small", "small-mid"] if args.tier == "both" else [args.tier]

    for tier in tiers:
        print(f"\n{'=' * 70}")
        print(f"STARTING {tier.upper()} TIER — {', '.join(args.states)}")
        print(f"{'=' * 70}\n", flush=True)

        db = SessionLocal()
        scan = Scan(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="pending",
            config_json={
                "states": args.states,
                "population_tier": tier,
                "source_types": ["meeting_minutes", "procurement", "state_portal"],
            },
            progress_phase="discovery",
            progress_pct=0,
            progress_message="Starting...",
        )
        db.add(scan)
        db.commit()
        scan_id = scan.id
        print(f"Scan ID: {scan_id}", flush=True)
        db.close()

        t0 = time.time()
        run_scan(scan_id, {
            "states": args.states,
            "population_tier": tier,
            "source_types": ["meeting_minutes", "procurement", "state_portal"],
        })
        elapsed = time.time() - t0
        print(f"\nScan time: {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)

        print_results(scan_id, tier)


if __name__ == "__main__":
    main()
