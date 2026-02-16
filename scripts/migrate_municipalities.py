#!/usr/bin/env python3
"""
Migration script: Import municipalities from municipalities.json into database.

This seeds the database with all 6,752 cities from the JSON file, setting
all domain_status to "unverified" so they can be enriched later.
"""

import json
import sys
import os

# Add parent directory to path so we can import src modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db, SessionLocal, Municipality

def load_municipalities_json():
    """Load municipalities from JSON file."""
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "municipalities.json")
    with open(json_path, 'r') as f:
        data = json.load(f)
    return data

def migrate():
    """Import all municipalities from JSON into database."""
    print("="*70)
    print("MIGRATION: Import municipalities from JSON to database")
    print("="*70)

    # Initialize database (create tables if needed)
    init_db()

    # Load JSON data
    print("\n1. Loading municipalities.json...")
    data = load_municipalities_json()
    states_data = data.get("states", {})
    print(f"   Found {len(states_data)} states in JSON")

    # Count total municipalities
    total_count = sum(len(state_data.get("municipalities", [])) for state_data in states_data.values())
    print(f"   Total municipalities: {total_count:,}")

    # Create database session
    db = SessionLocal()

    try:
        # Check if database already has data
        existing_count = db.query(Municipality).count()
        if existing_count > 0:
            print(f"\n⚠️  WARNING: Database already contains {existing_count} municipalities")
            response = input("   Delete existing data and re-import? (yes/no): ")
            if response.lower() != 'yes':
                print("   Migration cancelled.")
                return

            print("   Deleting existing data...")
            db.query(Municipality).delete()
            db.commit()

        # Import municipalities
        print("\n2. Importing municipalities...")
        imported_count = 0

        for state_code, state_data in states_data.items():
            municipalities = state_data.get("municipalities", [])

            for muni in municipalities:
                municipality = Municipality(
                    name=muni["name"],
                    state=state_code,
                    population=muni.get("population", 0),
                    domain=muni.get("domain"),
                    domain_status="unverified"  # All start as unverified
                )
                db.add(municipality)
                imported_count += 1

            # Commit in batches (per state) for performance
            db.commit()
            print(f"   Imported {state_code}: {len(municipalities)} cities")

        print(f"\n✓ Successfully imported {imported_count:,} municipalities")

        # Show summary stats
        print("\n3. Database summary:")
        print(f"   Total cities: {db.query(Municipality).count():,}")
        print(f"   Unverified: {db.query(Municipality).filter_by(domain_status='unverified').count():,}")
        print(f"   States: {db.query(Municipality.state).distinct().count()}")

        # Show sample data
        print("\n4. Sample data:")
        samples = db.query(Municipality).limit(5).all()
        for city in samples:
            print(f"   - {city.name}, {city.state} (pop: {city.population:,}, domain: {city.domain})")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    print("\n" + "="*70)
    print("MIGRATION COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("1. Run enrichment to verify domains and discover sources")
    print("2. Start with Caselle territory states (UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA)")
    print()

if __name__ == "__main__":
    migrate()
