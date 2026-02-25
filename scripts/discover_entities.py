#!/usr/bin/env python3
"""
Discover Government Entities for a Municipality

Tests the entity discovery system to find additional government organizations
that buy ERP systems separately (school districts, fire districts, libraries, etc.)

Usage:
    python3 scripts/discover_entities.py "Salt Lake City" UT slc.gov
    python3 scripts/discover_entities.py "Provo" UT provo.org --county "Utah"
"""

import sys
import os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.entity_discovery import EntityDiscovery
import argparse


def main():
    parser = argparse.ArgumentParser(description="Discover government entities for a municipality")
    parser.add_argument("city", help="City name (e.g., 'Salt Lake City')")
    parser.add_argument("state", help="State code (e.g., 'UT')")
    parser.add_argument("domain", help="Main city domain (e.g., 'slc.gov')")
    parser.add_argument("--county", help="County name (e.g., 'Salt Lake')")

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"ENTITY DISCOVERY: {args.city}, {args.state}")
    print(f"{'='*70}\n")

    discovery = EntityDiscovery(request_delay=0.5)  # Faster for testing

    entities = discovery.discover_entities(
        municipality_name=args.city,
        state=args.state,
        main_domain=args.domain,
        county_name=args.county
    )

    print(f"\n{'='*70}")
    print(f"RESULTS: Found {len(entities)} entities")
    print(f"{'='*70}\n")

    if entities:
        for entity in entities:
            print(f"✓ {entity.name}")
            print(f"  Type: {entity.entity_type}")
            print(f"  Domain: {entity.domain}")
            print(f"  URL: {entity.url}")
            print(f"  Confidence: {entity.confidence:.0%}")
            print(f"  Notes: {entity.notes}")
            print()
    else:
        print("No additional entities discovered.")
        print("\nThis could mean:")
        print("  • Entities use different domain patterns not yet in our database")
        print("  • Municipality doesn't have separate entities")
        print("  • Entities are listed on main site but not linked")
        print()

    print(f"{'='*70}")
    print(f"SALES INSIGHT: Each entity = separate ERP opportunity!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
