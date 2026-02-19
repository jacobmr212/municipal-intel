#!/usr/bin/env python3
"""
Nevada Public Notice Portal Directory Scraper
Extracts municipal links from notice.nv.gov homepage and adds to database.

Unlike Utah's centralized portal, Nevada's portal is a DIRECTORY that links
to individual municipality pages hosted on third-party platforms.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

BASE_URL = "https://notice.nv.gov"

def scrape_municipal_links():
    """Extract all municipal/county links from Nevada portal homepage."""
    print("=" * 80)
    print("SCRAPING NEVADA PORTAL MUNICIPAL DIRECTORY")
    print("=" * 80)

    try:
        response = requests.get(BASE_URL, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all links
        all_links = soup.find_all('a', href=True)

        # Filter for municipal/county links (external URLs only, ignore '#' anchors)
        municipal_links = []

        # Keywords indicating municipal government
        gov_keywords = [
            'city', 'town', 'county', 'municipal', 'council', 'board',
            'commissioners', 'government', 'clerk', 'meeting', 'agenda'
        ]

        for link in all_links:
            href = link.get('href', '')
            text = link.text.strip().lower()

            # Skip anchors and internal links
            if href.startswith('#') or not href.startswith('http'):
                continue

            # Skip back to notice.nv.gov itself
            if href == BASE_URL or href == f"{BASE_URL}/":
                continue

            # Check if text contains government keywords
            if any(keyword in text for keyword in gov_keywords):
                municipal_links.append({
                    'text': link.text.strip(),
                    'url': href
                })

        print(f"\nFound {len(municipal_links)} potential municipal links")

        # Parse entity names from link text
        entities = []
        for link in municipal_links:
            text = link['text']
            url = link['url']

            # Try to extract city/county name
            # Common patterns: "City Name Council", "County Name Board of Commissioners", etc.
            entity_name = None

            # Remove common suffixes to get entity name
            patterns_to_remove = [
                r'\s+board\s+of\s+commissioners.*$',
                r'\s+city\s+council.*$',
                r'\s+town\s+council.*$',
                r'\s+board\s+of\s+supervisors.*$',
                r'\s+commission.*$',
                r'\s+committee.*$',
                r'\s+board.*$',
                r'\s+-\s+.*$',  # Everything after a dash
            ]

            cleaned = text
            for pattern in patterns_to_remove:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()

            if cleaned:
                entity_name = cleaned
            else:
                entity_name = text

            # Classify as city or county
            entity_type = 'county' if 'county' in text.lower() else 'city'

            entities.append({
                'name': entity_name,
                'type': entity_type,
                'full_text': text,
                'url': url
            })

        return entities

    except Exception as e:
        print(f"Error scraping portal: {e}")
        return []


def match_and_add_to_database(entities):
    """Match entities to database municipalities and add as sources."""

    from src.database import SessionLocal, Municipality, MunicipalSource
    from difflib import SequenceMatcher

    db = SessionLocal()

    try:
        # Get all Nevada municipalities
        nv_munis = db.query(Municipality).filter_by(state="NV").all()

        print("\n" + "=" * 80)
        print("MATCHING ENTITIES TO DATABASE MUNICIPALITIES")
        print("=" * 80)

        matches = []
        added = 0
        existing = 0

        for entity in entities:
            entity_name = entity['name'].lower()
            entity_url = entity['url']

            # Try fuzzy matching against NV municipalities
            best_match = None
            best_score = 0.0

            for muni in nv_munis:
                muni_name = muni.name.lower()

                # Calculate similarity
                similarity = SequenceMatcher(None, muni_name, entity_name).ratio()

                # Also check if one contains the other
                if muni_name in entity_name or entity_name in muni_name:
                    similarity = max(similarity, 0.85)

                if similarity > best_score:
                    best_score = similarity
                    best_match = muni

            # If similarity > 70%, consider it a match
            if best_match and best_score >= 0.7:
                # Check if source already exists
                source = db.query(MunicipalSource).filter_by(
                    municipality_id=best_match.id,
                    url=entity_url
                ).first()

                if source:
                    existing += 1
                else:
                    # Determine platform from URL
                    platform = 'unknown'
                    if 'granicus' in entity_url:
                        platform = 'granicus'
                    elif 'civicclerk' in entity_url or 'civicplus' in entity_url:
                        platform = 'civicplus'
                    elif 'agendacenter' in entity_url.lower():
                        platform = 'civicplus'
                    elif 'legistar' in entity_url:
                        platform = 'granicus'
                    elif 'municode' in entity_url:
                        platform = 'municode'

                    # Add new source
                    source = MunicipalSource(
                        municipality_id=best_match.id,
                        url=entity_url,
                        source_type='state_portal',  # Directory reference from state portal
                        platform=platform,
                        confidence=0.80,  # Directory link = good confidence
                        discovered_by_pattern='nevada_portal_directory',
                        discovered_at=datetime.now()
                    )
                    db.add(source)
                    db.commit()
                    added += 1

                    print(f"  ✓ {best_match.name} ({best_score:.0%} match) → {entity_url[:70]}")

                matches.append({
                    'municipality': best_match.name,
                    'entity': entity['name'],
                    'score': best_score,
                    'url': entity_url
                })
            else:
                print(f"  ~ No match for: {entity['name']} (best: {best_score:.0%})")

        print(f"\n" + "=" * 80)
        print("MATCHING SUMMARY")
        print("=" * 80)
        print(f"  Entities from portal: {len(entities)}")
        print(f"  Matched to database: {len(matches)}")
        print(f"  New sources added: {added}")
        print(f"  Already existed: {existing}")

        # Coverage stats
        nv_total = db.query(Municipality).filter_by(state='NV').count()
        with_sources = db.query(Municipality).join(MunicipalSource).filter(
            Municipality.state == 'NV'
        ).distinct().count()

        coverage = (with_sources / nv_total * 100) if nv_total > 0 else 0

        print(f"\nNevada Coverage: {with_sources}/{nv_total} municipalities ({coverage:.1f}%)")
        print("=" * 80)

        return matches

    finally:
        db.close()


if __name__ == "__main__":
    print("\nNevada Public Notice Portal Scraper")
    print("Note: Nevada's portal is a DIRECTORY of links to individual municipality")
    print("      pages, not a centralized data repository like Utah's PMN portal.\n")

    # Step 1: Scrape directory links
    entities = scrape_municipal_links()

    if not entities:
        print("\n⚠️  No entities found. Portal may have changed structure.")
        sys.exit(1)

    # Show sample
    print(f"\nSample entities found:")
    for entity in entities[:10]:
        print(f"  - {entity['name']} ({entity['type']})")
        print(f"    {entity['url'][:70]}...")

    if len(entities) > 10:
        print(f"  ... and {len(entities) - 10} more")

    # Step 2: Match to database and add sources
    matches = match_and_add_to_database(entities)

    print(f"\n✅ Nevada portal directory extraction complete!")
    print(f"   Extracted {len(entities)} entity links")
    print(f"   Matched {len(matches)} to database municipalities")
