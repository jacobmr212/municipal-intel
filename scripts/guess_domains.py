#!/usr/bin/env python3
"""
Algorithmic Domain Guessing

For cities without verified domains, generate and test candidate domains.

Patterns tested (in order of likelihood):
1. {city}.gov
2. {city}{state}.gov
3. cityof{city}.com
4. cityof{city}.org
5. ci.{city}.{state}.us
6. {city}-{state}.gov
7. {city}{state_full}.gov
8. {city}.{state}.us

Special handling:
- Cities with spaces: "Salt Lake City" → "saltlakecity"
- Cities with "Saint"/"St.": try both variations
- Well-known abbreviations: "Salt Lake City" → also try "slc"
"""

import sys
import os
import time
import logging
import re
from typing import Optional, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality
import requests

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# State abbreviation to full name mapping
STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "newhampshire", "NJ": "newjersey", "NM": "newmexico", "NY": "newyork",
    "NC": "northcarolina", "ND": "northdakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhodeisland", "SC": "southcarolina",
    "SD": "southdakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "westvirginia",
    "WI": "wisconsin", "WY": "wyoming",
}


def normalize_city_name(name: str) -> str:
    """Normalize city name for domain generation."""
    # Convert to lowercase
    name = name.lower()

    # Handle Saint/St. variations
    name = re.sub(r'\bsaint\b', 'st', name)
    name = re.sub(r'\bst\.\s*', 'st', name)

    # Remove special characters
    name = re.sub(r'[^a-z0-9\s]', '', name)

    # Remove spaces
    name = name.replace(' ', '')

    return name


def generate_domain_candidates(city_name: str, state_code: str, max_candidates: int = 8) -> List[str]:
    """
    Generate candidate domains for a city.

    Returns list of domains to test (without http/https).
    """
    city_slug = normalize_city_name(city_name)
    state_lower = state_code.lower()
    state_name = STATE_NAMES.get(state_code, state_lower)

    candidates = []

    # Pattern 1: {city}.gov (most common for larger cities)
    candidates.append(f"{city_slug}.gov")

    # Pattern 2: {city}{state}.gov
    candidates.append(f"{city_slug}{state_lower}.gov")

    # Pattern 3: cityof{city}.com (very common)
    candidates.append(f"cityof{city_slug}.com")

    # Pattern 4: cityof{city}.org
    candidates.append(f"cityof{city_slug}.org")

    # Pattern 5: ci.{city}.{state}.us (older format, still used)
    candidates.append(f"ci.{city_slug}.{state_lower}.us")

    # Pattern 6: {city}-{state}.gov
    candidates.append(f"{city_slug}-{state_lower}.gov")

    # Pattern 7: {city}{state_full}.gov
    candidates.append(f"{city_slug}{state_name}.gov")

    # Pattern 8: {city}.{state}.us
    candidates.append(f"{city_slug}.{state_lower}.us")

    # Limit to max candidates
    return candidates[:max_candidates]


def test_domain(domain: str, timeout: int = 2) -> Optional[str]:
    """
    Test if a domain exists and is accessible.

    Returns final URL after redirects, or None if domain doesn't work.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "MunicipalIntel/1.0 (Government Meeting Research Tool)",
    })

    for protocol in ['https', 'http']:
        url = f"{protocol}://{domain}"
        try:
            response = session.head(url, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                return response.url  # Return final URL after redirects
        except requests.exceptions.RequestException:
            continue

        # Also try with www.
        url_www = f"{protocol}://www.{domain}"
        try:
            response = session.head(url_www, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                return response.url
        except requests.exceptions.RequestException:
            continue

    return None


def guess_domains(batch_size: int = 100, max_cities: Optional[int] = None):
    """
    Test domain candidates for unverified cities.

    Args:
        batch_size: Number of cities to process before committing
        max_cities: Maximum number of cities to process (None = all)
    """
    db = SessionLocal()

    try:
        # Get all unverified cities
        query = db.query(Municipality).filter_by(domain_status="unverified")

        if max_cities:
            query = query.limit(max_cities)

        cities = query.all()
        total = len(cities)

        if total == 0:
            logger.info("No unverified cities found.")
            return

        logger.info(f"Found {total:,} unverified cities")
        logger.info(f"Testing up to 8 domain candidates per city\n")

        stats = {
            "tested": 0,
            "verified": 0,
            "failed": 0,
        }

        for i, city in enumerate(cities):
            logger.info(f"[{i+1}/{total}] {city.name}, {city.state}")

            # Generate candidates
            candidates = generate_domain_candidates(city.name, city.state)

            # Test each candidate
            found_domain = None
            for candidate in candidates:
                resolved_url = test_domain(candidate)

                if resolved_url:
                    logger.info(f"  ✓ Found: {candidate} → {resolved_url}")
                    found_domain = candidate
                    city.domain = candidate
                    city.resolved_url = resolved_url
                    city.domain_status = "verified"
                    stats["verified"] += 1
                    break

                # Small delay to be respectful
                time.sleep(0.5)

            if not found_domain:
                logger.info(f"  ✗ No working domain found")
                stats["failed"] += 1

            stats["tested"] += 1

            # Commit in batches
            if stats["tested"] % batch_size == 0:
                db.commit()
                logger.info(f"\n  Progress: {stats['verified']} verified, {stats['failed']} failed\n")

        # Final commit
        db.commit()

        return stats

    finally:
        db.close()


def main():
    """Main domain guessing process."""
    logger.info("=" * 70)
    logger.info("ALGORITHMIC DOMAIN GUESSING")
    logger.info("=" * 70)
    logger.info("Testing domain candidates for unverified cities\n")

    # Ask for batch size
    print("How many cities to process?")
    print("  1. Test 100 cities (quick test)")
    print("  2. Test 500 cities (moderate)")
    print("  3. Test all unverified cities")
    choice = input("Choice (1-3): ").strip()

    max_cities = None
    if choice == "1":
        max_cities = 100
    elif choice == "2":
        max_cities = 500
    elif choice == "3":
        max_cities = None
    else:
        logger.info("Invalid choice. Exiting.")
        return

    logger.info("\n" + "=" * 70)
    logger.info("STARTING DOMAIN GUESSING")
    logger.info("=" * 70 + "\n")

    start_time = time.time()
    stats = guess_domains(batch_size=100, max_cities=max_cities)
    elapsed = time.time() - start_time

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("DOMAIN GUESSING SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Cities tested: {stats['tested']:,}")
    logger.info(f"Domains found: {stats['verified']:,} ({stats['verified']/stats['tested']*100:.1f}%)")
    logger.info(f"No domain found: {stats['failed']:,} ({stats['failed']/stats['tested']*100:.1f}%)")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")

    # Check total verified in database
    db = SessionLocal()
    try:
        total_verified = db.query(Municipality).filter_by(domain_status="verified").count()
        total_unverified = db.query(Municipality).filter_by(domain_status="unverified").count()
        total_cities = total_verified + total_unverified

        logger.info(f"\nDatabase status:")
        logger.info(f"  Total cities: {total_cities:,}")
        logger.info(f"  Verified: {total_verified:,} ({total_verified/total_cities*100:.1f}%)")
        logger.info(f"  Unverified: {total_unverified:,} ({total_unverified/total_cities*100:.1f}%)")

    finally:
        db.close()

    logger.info("\n" + "=" * 70)
    logger.info("GUESSING COMPLETE")
    logger.info("=" * 70)
    logger.info("\nNext steps:")
    logger.info("1. Run enrichment to discover sources for verified cities")
    logger.info("2. Start scanning verified cities!\n")


if __name__ == "__main__":
    main()
