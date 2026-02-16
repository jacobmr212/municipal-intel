#!/usr/bin/env python3
"""
Analyze Utah enrichment gaps to identify pattern improvements.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality, MunicipalSource

# Domain patterns that were tested (from enrichment.py)
DOMAIN_PATTERNS = [
    "{domain}",  # Original
    "cityof{city}.com",
    "cityof{city}.org",
    "{city}ut.gov",
    "{city}{state}.gov",
    "ci.{city}.ut.us",
    "{city}-ut.gov",
    "{city}utah.gov",
]

def normalize_city(name):
    """Normalize city name for domain generation."""
    return name.lower().replace(' ', '').replace('.', '').replace('-', '')


def main():
    db = SessionLocal()

    try:
        print("=" * 80)
        print("UTAH ENRICHMENT GAP ANALYSIS")
        print("=" * 80)
        print()

        # Get all Utah municipalities
        all_ut = db.query(Municipality).filter_by(state="UT").order_by(Municipality.population.desc()).all()

        verified = [m for m in all_ut if m.domain_status == "verified"]
        dead = [m for m in all_ut if m.domain_status == "dead"]
        unverified = [m for m in all_ut if m.domain_status == "unverified"]

        print(f"Total Utah cities: {len(all_ut)}")
        print(f"  Verified: {len(verified)}")
        print(f"  Dead: {len(dead)}")
        print(f"  Unverified: {len(unverified)}")
        print()

        # 1. DEAD DOMAINS
        print("=" * 80)
        print("1. DEAD DOMAINS (30 cities)")
        print("=" * 80)
        print()
        print(f"{'City':<30} {'Population':>10}  Original Domain")
        print("-" * 80)

        for m in dead:
            print(f"{m.name:<30} {m.population:>10,}  {m.domain or '(none)'}")

        print()
        print("Domain patterns tested for each city:")
        for i, pattern in enumerate(DOMAIN_PATTERNS, 1):
            print(f"  {i}. {pattern}")
        print()

        # 2. VERIFIED BUT NO SOURCES
        print("=" * 80)
        print("2. VERIFIED BUT NO SOURCES")
        print("=" * 80)
        print()

        verified_no_sources = []
        for m in verified:
            source_count = db.query(MunicipalSource).filter_by(municipality_id=m.id).count()
            if source_count == 0:
                verified_no_sources.append(m)

        print(f"Found {len(verified_no_sources)} verified cities with zero sources")
        print()
        print(f"{'City':<30} {'Population':>10}  {'Verified Domain':<40}")
        print("-" * 80)

        for m in verified_no_sources:
            print(f"{m.name:<30} {m.population:>10,}  {m.resolved_url or m.domain or '(unknown)'}")

        print()
        print("URL patterns tested for each verified city (first 8 only):")
        print("  1. /AgendaCenter")
        print("  2. /Archive.aspx")
        print("  3. /DocumentCenter")
        print("  4. /Meetings.aspx")
        print("  5. /meetings")
        print("  6. /bids")
        print("  7. /rfp")
        print("  8. /purchasing")
        print("(Early stopping: Stops after high-confidence source found or 8 patterns tested)")
        print()

        # 3. THE 5 MISSING CITIES
        print("=" * 80)
        print("3. STATUS BREAKDOWN")
        print("=" * 80)
        print()

        if unverified:
            print(f"Unverified cities ({len(unverified)}):")
            for m in unverified:
                print(f"  - {m.name} (pop: {m.population:,}) - domain: {m.domain or '(none)'}")
        else:
            print("No unverified cities.")

        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total cities: {len(all_ut)}")
        print(f"Verified: {len(verified)} ({len(verified)/len(all_ut)*100:.1f}%)")
        print(f"  - With sources: {len(verified) - len(verified_no_sources)}")
        print(f"  - Without sources: {len(verified_no_sources)}")
        print(f"Dead: {len(dead)} ({len(dead)/len(all_ut)*100:.1f}%)")
        print(f"Unverified: {len(unverified)} ({len(unverified)/len(all_ut)*100:.1f}%)")
        print()
        print("NEXT STEPS:")
        print("1. Research dead domains - find correct domains manually")
        print("2. Research verified-no-sources - find meeting minutes URLs manually")
        print("3. Identify missing URL patterns from successful discoveries")
        print("4. Re-run enrichment with improved patterns")

    finally:
        db.close()


if __name__ == "__main__":
    main()
