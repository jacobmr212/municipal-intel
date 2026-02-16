#!/usr/bin/env python3
"""
Reset all "dead" Utah cities back to unverified for re-testing with fixed validator.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality

def main():
    db = SessionLocal()

    try:
        # Reset all dead Utah cities to unverified
        dead_cities = db.query(Municipality).filter_by(
            state="UT",
            domain_status="dead"
        ).all()

        print(f"Found {len(dead_cities)} dead Utah cities")
        print("Resetting to unverified status...\n")

        for city in dead_cities:
            print(f"  - {city.name}")
            city.domain_status = "unverified"
            city.domain_verified_at = None
            city.resolved_url = None

        db.commit()

        print(f"\nReset {len(dead_cities)} cities to unverified")
        print("Ready for re-enrichment with fixed validator!")

    finally:
        db.close()


if __name__ == "__main__":
    main()
