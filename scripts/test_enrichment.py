#!/usr/bin/env python3
"""
Test script for enrichment module.
Tests domain validation and source discovery on a small sample.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality, MunicipalSource
from src.enrichment import EnrichmentEngine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

def test_enrichment():
    """Test enrichment on a few Utah cities."""
    print("=" * 70)
    print("ENRICHMENT TEST: Sample Utah Cities")
    print("=" * 70)

    db = SessionLocal()

    try:
        # Get 5 Utah cities to test (mix of sizes)
        test_cities = db.query(Municipality).filter_by(
            state="UT",
            domain_status="unverified"
        ).order_by(Municipality.population.desc()).limit(5).all()

        if not test_cities:
            print("No unverified Utah cities found in database.")
            print("Run migration script first: python scripts/migrate_municipalities.py")
            return

        print(f"\nTesting enrichment on {len(test_cities)} Utah cities:")
        for city in test_cities:
            print(f"  - {city.name} (pop: {city.population:,}, domain: {city.domain})")

        print("\n" + "=" * 70)
        print("Starting enrichment...")
        print("=" * 70 + "\n")

        engine = EnrichmentEngine(request_delay=1.0, timeout=8)

        for i, city in enumerate(test_cities):
            print(f"\n[{i + 1}/{len(test_cities)}] Enriching {city.name}, UT...")
            stats = engine.enrich_municipality(city, db)

            # Show result
            if city.domain_status == "verified":
                print(f"  ✓ Domain verified: {city.resolved_url}")

                # Check sources found
                sources = db.query(MunicipalSource).filter_by(municipality_id=city.id).all()
                if sources:
                    print(f"  ✓ Found {len(sources)} source(s):")
                    for source in sources:
                        print(f"    - {source.source_type}: {source.url} ({source.platform})")
                else:
                    print(f"  ⚠ Domain verified but no sources found")
            elif city.domain_status == "dead":
                print(f"  ✗ Domain dead: {city.domain}")
            else:
                print(f"  ? Status: {city.domain_status}")

        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        verified = db.query(Municipality).filter_by(state="UT", domain_status="verified").count()
        dead = db.query(Municipality).filter_by(state="UT", domain_status="dead").count()
        sources_found = db.query(MunicipalSource).join(Municipality).filter(Municipality.state == "UT").count()

        print(f"Utah cities verified: {verified}")
        print(f"Utah cities dead: {dead}")
        print(f"Utah sources discovered: {sources_found}")

        if sources_found > 0:
            print("\n✅ Enrichment module working correctly!")
        else:
            print("\n⚠️  No sources found — may need to investigate")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_enrichment()
