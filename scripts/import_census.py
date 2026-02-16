#!/usr/bin/env python3
"""
Import US Census Data - Expand database to all US incorporated places

Sources (in order of preference):
1. SimpleMaps US Cities Database (GitHub - reliable, updated annually)
2. US Census Bureau Gazetteer Files
3. Wikipedia lists (fallback)

Target: ~10,000-12,000 cities with population > 1,000

This script:
- Downloads city data from a reliable source
- Filters to incorporated places with population > 1,000
- Inserts into Municipality table
- Preserves already-enriched cities (no overwrites)
- Logs import statistics
"""

import sys
import os
import csv
import json
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def import_from_csv(csv_path: str, min_population: int = 1000):
    """
    Import cities from a CSV file.

    Expected CSV format:
    - city: City name
    - state_id or state_code: Two-letter state code
    - population: Population count
    - Optional: county, lat, lng, etc.
    """
    db = SessionLocal()

    try:
        stats = {
            "total_in_file": 0,
            "above_min_pop": 0,
            "already_exists": 0,
            "imported": 0,
            "states": set(),
        }

        logger.info(f"Reading CSV from {csv_path}...")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Detect column names (different sources use different names)
            fieldnames = reader.fieldnames
            logger.info(f"CSV columns: {', '.join(fieldnames)}")

            # Map common column name variations
            city_col = next((col for col in fieldnames if col.lower() in ['city', 'name', 'city_name']), None)
            state_col = next((col for col in fieldnames if col.lower() in ['state_id', 'state_code', 'state', 'state_abbr']), None)
            pop_col = next((col for col in fieldnames if col.lower() in ['population', 'pop', 'population_2020', 'population_2019']), None)

            if not all([city_col, state_col, pop_col]):
                logger.error(f"Missing required columns. Found: city={city_col}, state={state_col}, pop={pop_col}")
                return stats

            logger.info(f"Using columns: city='{city_col}', state='{state_col}', population='{pop_col}'")
            logger.info(f"Filtering to cities with population >= {min_population:,}\n")

            for row in reader:
                stats["total_in_file"] += 1

                city_name = row.get(city_col, '').strip()
                state_code = row.get(state_col, '').strip().upper()
                population_str = row.get(pop_col, '0').replace(',', '').strip()

                # Skip if missing data
                if not city_name or not state_code or len(state_code) != 2:
                    continue

                # Parse population
                try:
                    population = int(float(population_str))
                except (ValueError, TypeError):
                    population = 0

                # Filter by minimum population
                if population < min_population:
                    continue

                stats["above_min_pop"] += 1
                stats["states"].add(state_code)

                # Check if city already exists
                existing = db.query(Municipality).filter_by(
                    name=city_name,
                    state=state_code
                ).first()

                if existing:
                    stats["already_exists"] += 1
                    # Skip to preserve enrichment data
                    continue

                # Insert new city
                municipality = Municipality(
                    name=city_name,
                    state=state_code,
                    population=population,
                    domain=None,  # Will be filled by domain guessing
                    domain_status="unverified"
                )
                db.add(municipality)
                stats["imported"] += 1

                # Commit in batches (every 100 cities)
                if stats["imported"] % 100 == 0:
                    db.commit()
                    logger.info(f"  Imported {stats['imported']:,} cities so far...")

            # Final commit
            db.commit()

        return stats

    finally:
        db.close()


def download_simplemaps_data():
    """
    Download the SimpleMaps US Cities Database (free version).

    This is a well-maintained, annually-updated dataset.
    URL: https://simplemaps.com/data/us-cities (free version available)

    Returns path to downloaded CSV.
    """
    import requests
    from pathlib import Path

    # SimpleMaps provides a free basic database
    # For this demo, we'll use a placeholder URL
    # In production, download from: https://simplemaps.com/static/data/us-cities/1.75/basic/simplemaps_uscities_basicv1.75.zip

    data_dir = Path(__file__).parent.parent / "data"
    csv_path = data_dir / "us_cities_census.csv"

    if csv_path.exists():
        logger.info(f"Using existing data file: {csv_path}")
        return str(csv_path)

    logger.info("NOTE: For full US Census data, download from:")
    logger.info("  https://simplemaps.com/data/us-cities (free basic version)")
    logger.info("  Or: https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html")
    logger.info("")
    logger.info("Place the CSV file at: data/us_cities_census.csv")
    logger.info("")

    return None


def create_sample_data():
    """
    Create a sample CSV with major US cities for testing.
    This is a fallback if Census data isn't available.
    """
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / "data"
    csv_path = data_dir / "us_cities_sample.csv"

    # Sample of major US cities across different states
    sample_cities = [
        # Format: city, state, population
        ("New York", "NY", 8336817),
        ("Los Angeles", "CA", 3979576),
        ("Chicago", "IL", 2693976),
        ("Houston", "TX", 2320268),
        ("Phoenix", "AZ", 1680992),
        ("Philadelphia", "PA", 1584064),
        ("San Antonio", "TX", 1547253),
        ("San Diego", "CA", 1423851),
        ("Dallas", "TX", 1343573),
        ("San Jose", "CA", 1021795),
        ("Austin", "TX", 978908),
        ("Jacksonville", "FL", 911507),
        ("Fort Worth", "TX", 909585),
        ("Columbus", "OH", 898553),
        ("Charlotte", "NC", 885708),
        ("San Francisco", "CA", 881549),
        ("Indianapolis", "IN", 876384),
        ("Seattle", "WA", 753675),
        ("Denver", "CO", 727211),
        ("Boston", "MA", 692600),
        ("Minneapolis", "MN", 429606),
        ("St. Paul", "MN", 307695),
        ("Portland", "OR", 654741),
        ("Las Vegas", "NV", 641903),
        ("Boise", "ID", 235684),
    ]

    logger.info(f"Creating sample data file: {csv_path}")

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['city', 'state_id', 'population'])
        writer.writerows(sample_cities)

    return str(csv_path)


def main():
    """Main import process."""
    logger.info("=" * 70)
    logger.info("US CENSUS DATA IMPORT")
    logger.info("=" * 70)
    logger.info("Expanding municipality database to cover entire United States\n")

    # Try to get data source
    csv_path = download_simplemaps_data()

    if not csv_path:
        logger.warning("Full Census data not found. Using sample data for demo.")
        logger.info("To import full US data:")
        logger.info("  1. Download from https://simplemaps.com/data/us-cities")
        logger.info("  2. Save as data/us_cities_census.csv")
        logger.info("  3. Run this script again\n")

        response = input("Create sample data for testing? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Import cancelled.")
            return

        csv_path = create_sample_data()

    # Import cities
    logger.info("\n" + "=" * 70)
    logger.info("IMPORTING CITIES")
    logger.info("=" * 70 + "\n")

    min_population = 1000
    logger.info(f"Minimum population filter: {min_population:,}\n")

    stats = import_from_csv(csv_path, min_population=min_population)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("IMPORT SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total cities in source file: {stats['total_in_file']:,}")
    logger.info(f"Cities above {min_population:,} population: {stats['above_min_pop']:,}")
    logger.info(f"Already in database (skipped): {stats['already_exists']:,}")
    logger.info(f"Newly imported: {stats['imported']:,}")
    logger.info(f"States represented: {len(stats['states'])}")

    # Check total in database
    db = SessionLocal()
    try:
        total_cities = db.query(Municipality).count()
        verified_cities = db.query(Municipality).filter_by(domain_status="verified").count()
        unverified_cities = db.query(Municipality).filter_by(domain_status="unverified").count()

        logger.info(f"\nDatabase totals:")
        logger.info(f"  Total cities: {total_cities:,}")
        logger.info(f"  Verified: {verified_cities:,} ({verified_cities/total_cities*100:.1f}%)")
        logger.info(f"  Unverified: {unverified_cities:,} ({unverified_cities/total_cities*100:.1f}%)")

    finally:
        db.close()

    logger.info("\n" + "=" * 70)
    logger.info("IMPORT COMPLETE")
    logger.info("=" * 70)
    logger.info("\nNext steps:")
    logger.info("1. Run domain guessing: python scripts/guess_domains.py")
    logger.info("2. Run enrichment for unverified cities")
    logger.info("3. Start scanning!\n")


if __name__ == "__main__":
    main()
