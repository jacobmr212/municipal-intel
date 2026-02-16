#!/usr/bin/env python3
"""
Full scan of Utah PMN portal to discover all city council public bodies.
Writes results to JSON file for fast, reliable discovery.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime

BASE_URL = "https://www.utah.gov/pmn/sitemap/publicbody"
OUTPUT_FILE = "data/utah_portal_entities.json"

def scan_portal_ids(start_id=6000, end_id=7000):
    """Scan portal ID range and save all entities to JSON."""

    print(f"Scanning Utah PMN portal IDs {start_id}-{end_id}...")
    print(f"Writing results to: {OUTPUT_FILE}")
    print("=" * 80)

    entities = []
    checked = 0
    found = 0

    for pb_id in range(start_id, end_id + 1):
        url = f"{BASE_URL}/{pb_id}.html"

        try:
            response = requests.get(url, timeout=3)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract entity name
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
                        notice_count = len(rows) - 1

                    entity = {
                        'id': pb_id,
                        'name': entity_name,
                        'url': url,
                        'notices': notice_count,
                        'discovered_at': datetime.now().isoformat()
                    }

                    entities.append(entity)
                    found += 1

                    # Progress update every 10 finds
                    if found % 10 == 0:
                        print(f"  Found {found} entities (checked {checked} IDs)...")

            checked += 1

            # Progress update every 100 checks
            if checked % 100 == 0:
                print(f"  Progress: {checked}/{end_id - start_id + 1} IDs checked, {found} entities found")

            # Rate limit: 3 requests per second
            if checked % 3 == 0:
                time.sleep(1)

        except Exception as e:
            # Skip errors silently
            pass

    print(f"\nScan complete: {found} entities found out of {checked} IDs checked")
    print("=" * 80)

    # Write to JSON file
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            'scan_date': datetime.now().isoformat(),
            'id_range': f'{start_id}-{end_id}',
            'entities_found': len(entities),
            'entities': entities
        }, f, indent=2)

    print(f"Results saved to: {OUTPUT_FILE}")

    return entities


def match_and_add_to_database(entities):
    """Match entities to database cities and add portal sources."""

    from src.database import SessionLocal, Municipality, MunicipalSource

    db = SessionLocal()

    try:
        # Get all Utah cities
        ut_cities = db.query(Municipality).filter_by(state="UT").all()

        print("\nMatching entities to database cities...")
        print("=" * 80)

        matches = []
        added = 0
        existing = 0

        for entity in entities:
            entity_name_lower = entity['name'].lower()

            # Try to match to a city
            for city in ut_cities:
                city_name_lower = city.name.lower()

                # Fuzzy matching
                if (city_name_lower == entity_name_lower or
                    city_name_lower in entity_name_lower or
                    entity_name_lower in city_name_lower or
                    city_name_lower.replace(' ', '') == entity_name_lower.replace(' ', '')):

                    # Check if source already exists
                    source = db.query(MunicipalSource).filter_by(
                        municipality_id=city.id,
                        url=entity['url']
                    ).first()

                    if source:
                        existing += 1
                    else:
                        # Add new source
                        source = MunicipalSource(
                            municipality_id=city.id,
                            url=entity['url'],
                            source_type='state_portal',
                            platform='utah_pmn',
                            confidence=0.95,
                            discovered_by_pattern='portal_id_scan',
                            discovered_at=datetime.now()
                        )
                        db.add(source)
                        db.commit()
                        added += 1

                        print(f"  ✓ {city.name} → {entity['url']}")

                    matches.append({
                        'city': city.name,
                        'entity': entity['name'],
                        'url': entity['url']
                    })

                    break

        print(f"\nMatching complete:")
        print(f"  Entities matched: {len(matches)}")
        print(f"  New sources added: {added}")
        print(f"  Already existed: {existing}")
        print("=" * 80)

        # Final coverage stats
        ut_total = db.query(Municipality).filter_by(state='UT').count()
        with_sources = db.query(Municipality).join(MunicipalSource).filter(
            Municipality.state == 'UT'
        ).distinct().count()

        coverage = (with_sources / ut_total * 100) if ut_total > 0 else 0

        print(f"\nUtah Coverage: {with_sources}/{ut_total} cities ({coverage:.1f}%)")
        print("=" * 80)

        return matches

    finally:
        db.close()


if __name__ == "__main__":
    # Step 1: Scan portal
    entities = scan_portal_ids(start_id=6000, end_id=7000)

    # Step 2: Match and add to database
    matches = match_and_add_to_database(entities)

    print(f"\n✅ Portal discovery complete!")
    print(f"   Discovered {len(entities)} entities")
    print(f"   Matched {len(matches)} to database cities")
