#!/usr/bin/env python3
"""
Enrich Caselle Territory States

Runs offline enrichment for all 11 Caselle territory states:
UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA

This validates domains and discovers meeting minutes/procurement sources,
storing everything in the database for fast scanning.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.enrichment import enrich_caselle_territory

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("CASELLE TERRITORY ENRICHMENT")
    print("="*70)
    print("\nThis will enrich all municipalities in 11 states:")
    print("UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA")
    print("\nThis may take 10-30 minutes depending on the number of cities.")
    print("="*70 + "\n")

    try:
        stats = enrich_caselle_territory()

        print("\n" + "="*70)
        print("ENRICHMENT COMPLETE!")
        print("="*70)
        print(f"\nYou can now scan these states with blazing-fast performance!")
        print(f"Expected scan speed: <5 seconds per city")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Enrichment interrupted by user")
        print("Partial enrichment data has been saved to database.")
        print("You can resume enrichment later by running this script again.")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise
