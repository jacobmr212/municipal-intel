#!/usr/bin/env python3
"""
Discover all Utah cities in the PMN portal and match them to our database.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
import time
from src.database import SessionLocal, Municipality, MunicipalSource
from datetime import datetime

BASE_URL = "https://www.utah.gov/pmn/sitemap/publicbody"

def discover_portal_entities(start_id=6000, end_id=7000):
    """Scan portal ID range and extract all entities."""

    print("=" * 80)
    print("DISCOVERING UTAH PMN PORTAL ENTITIES")
    print("=" * 80)
    print(f"Scanning IDs {start_id} to {end_id}...")
    print()

    entities = []
    checked = 0

    for pb_id in range(start_id, end_id + 1):
        url = f"{BASE_URL}/{pb_id}.html"

        try:
            response = requests.get(url, timeout=3)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract entity name from definition list
                entity_name = None
                dt_tags = soup.find_all('dt')
                for dt in dt_tags:
                    if 'Entity Name' in dt.text:
                        dd = dt.find_next_sibling('dd')
                        if dd:
                            entity_name = dd.text.strip()
                            break

                if entity_name and entity_name != 'Unknown':
                    # Count notices
                    table = soup.find('table')
                    notice_count = 0
                    if table:
                        rows = table.find_all('tr')
                        notice_count = len(rows) - 1  # Subtract header

                    entities.append({
                        'id': pb_id,
                        'name': entity_name,
                        'url': url,
                        'notices': notice_count
                    })

                    print(f"  Found: {pb_id} - {entity_name} ({notice_count} notices)")

            checked += 1

            # Rate limit (3 requests/second = respectful)
            if checked % 3 == 0:
                time.sleep(1)

        except Exception as e:
            # Skip errors silently (timeouts, connection errors, etc.)
            pass

    print()
    print(f"Scanned {checked} IDs, found {len(entities)} entities")
    print("=" * 80)
    print()

    return entities


def match_to_database(entities):
    """Match discovered entities to Utah cities in our database."""

    db = SessionLocal()

    try:
        # Get all Utah cities from database
        ut_cities = db.query(Municipality).filter_by(state="UT").all()

        print("=" * 80)
        print("MATCHING PORTAL ENTITIES TO DATABASE")
        print("=" * 80)
        print(f"Database has {len(ut_cities)} Utah cities")
        print(f"Portal has {len(entities)} entities")
        print()

        matches = []

        for entity in entities:
            entity_name_lower = entity['name'].lower()

            # Try to match to a city in our database
            for city in ut_cities:
                city_name_lower = city.name.lower()

                # Match variations:
                # - Exact: "Provo" == "Provo"
                # - Entity contains city: "Provo City" contains "Provo"
                # - City contains entity: "Salt Lake City" contains "Salt Lake"

                if (city_name_lower == entity_name_lower or
                    city_name_lower in entity_name_lower or
                    entity_name_lower in city_name_lower):

                    matches.append({
                        'entity': entity,
                        'city': city
                    })

                    print(f"  ✓ Match: {entity['name']} (ID {entity['id']}) → {city.name}")
                    break

        print()
        print(f"Matched {len(matches)} portal entities to database cities")
        print(f"Unmatched: {len(entities) - len(matches)} portal entities")
        print(f"Missing: {len(ut_cities) - len(matches)} database cities")
        print("=" * 80)
        print()

        return matches

    finally:
        db.close()


def add_portal_sources(matches):
    """Add portal URLs as sources in the database."""

    db = SessionLocal()

    try:
        print("=" * 80)
        print("ADDING PORTAL SOURCES TO DATABASE")
        print("=" * 80)
        print()

        added = 0
        existing = 0

        for match in matches:
            entity = match['entity']
            city = match['city']

            # Check if source already exists
            source = db.query(MunicipalSource).filter_by(
                municipality_id=city.id,
                url=entity['url']
            ).first()

            if source:
                existing += 1
                continue

            # Create new source
            source = MunicipalSource(
                municipality_id=city.id,
                url=entity['url'],
                source_type="state_portal",
                platform="utah_pmn",
                confidence=0.95,  # High confidence - official state portal
                discovered_by_pattern="utah_portal_scan",
                discovered_at=datetime.utcnow()
            )

            db.add(source)
            added += 1

            print(f"  + Added: {city.name} → {entity['url']}")

        db.commit()

        print()
        print(f"Added {added} new portal sources")
        print(f"Skipped {existing} existing sources")
        print("=" * 80)
        print()

        return added

    finally:
        db.close()


def main():
    # Step 1: Discover all entities in portal
    entities = discover_portal_entities(start_id=6000, end_id=7000)

    # Step 2: Match to database cities
    matches = match_to_database(entities)

    # Step 3: Add portal URLs as sources
    added = add_portal_sources(matches)

    # Final summary
    print()
    print("=" * 80)
    print("UTAH PORTAL DISCOVERY COMPLETE")
    print("=" * 80)
    print(f"Portal entities found: {len(entities)}")
    print(f"Matched to database: {len(matches)}")
    print(f"New sources added: {added}")
    print()

    # Show coverage improvement
    db = SessionLocal()
    try:
        ut_cities = db.query(Municipality).filter_by(state="UT").count()
        cities_with_sources = db.query(Municipality).join(MunicipalSource).filter(
            Municipality.state == "UT"
        ).distinct().count()

        coverage = (cities_with_sources / ut_cities * 100) if ut_cities > 0 else 0

        print(f"Utah coverage: {cities_with_sources}/{ut_cities} cities ({coverage:.1f}%)")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
