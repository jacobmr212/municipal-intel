#!/usr/bin/env python3
"""
Test JavaScript-enabled discovery on tech-forward cities.
Compares static vs JS-rendered scraping results.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality
from src.discovery import SourceDiscovery
from src.discovery_js import check_url_with_js, JSSourceDiscovery
import asyncio

# Tech-forward cities with likely JS-heavy sites
TEST_CITIES = [
    {"name": "San Francisco", "state": "CA", "domain": "sf.gov"},
    {"name": "San Jose", "state": "CA", "domain": "sanjoseca.gov"},
    {"name": "Oakland", "state": "CA", "domain": "oaklandca.gov"},
    {"name": "Austin", "state": "TX", "domain": "austintexas.gov"},
    {"name": "Seattle", "state": "WA", "domain": "seattle.gov"},
]

# Common URL patterns to test
TEST_PATTERNS = [
    "/meetings",
    "/city-council/meetings",
    "/council/agendas",
    "/government/meetings",
    "/AgendaCenter",
    "/Meetings.aspx",
]


def test_static_vs_js():
    """Compare static requests vs JS rendering for known cities."""

    print("=" * 80)
    print("JAVASCRIPT DISCOVERY TEST — Static vs JS Rendering")
    print("=" * 80)

    static_discovery = SourceDiscovery(request_delay=1.0, timeout=8)

    for city_info in TEST_CITIES:
        name = city_info["name"]
        state = city_info["state"]
        domain = city_info["domain"]

        print(f"\n{'=' * 80}")
        print(f"{name}, {state} — {domain}")
        print("=" * 80)

        # Test with static discovery first
        print("\n[1] STATIC DISCOVERY (requests + BeautifulSoup)")
        base_urls = [f"https://www.{domain}", f"https://{domain}"]

        static_found = []
        for base_url in base_urls[:1]:  # Just try primary URL
            for pattern in TEST_PATTERNS[:4]:  # Try first 4 patterns
                url = f"{base_url}{pattern}"
                result = static_discovery._check_url(url)
                if result:
                    static_found.append((url, result))
                    print(f"  ✓ Found: {url}")
                    print(f"    Platform: {result[1]}")

        if not static_found:
            print("  ✗ No sources found with static scraping")

        # Test with JS discovery
        print("\n[2] JAVASCRIPT DISCOVERY (Playwright + Chromium)")
        js_found = []

        async def test_js():
            async with JSSourceDiscovery(timeout=10000) as js_discovery:
                for base_url in base_urls[:1]:
                    for pattern in TEST_PATTERNS[:4]:
                        url = f"{base_url}{pattern}"
                        result = await js_discovery.check_url(url)
                        if result:
                            js_found.append((url, result))
                            print(f"  ✓ Found: {url}")
                            print(f"    Platform: {result[1]}")

        asyncio.run(test_js())

        if not js_found:
            print("  ✗ No sources found with JS rendering")

        # Compare results
        print(f"\n[COMPARISON]")
        print(f"  Static discovery: {len(static_found)} sources")
        print(f"  JS discovery: {len(js_found)} sources")

        if len(js_found) > len(static_found):
            improvement = len(js_found) - len(static_found)
            print(f"  🎯 JS discovery found {improvement} additional source(s)")
        elif len(static_found) == len(js_found) == 0:
            print(f"  ⚠️  Both methods failed - site may not have standard patterns")
        else:
            print(f"  ✓ Both methods found similar results")

    print(f"\n{'=' * 80}")
    print("TEST COMPLETE")
    print("=" * 80)


def test_from_database():
    """Test JS discovery on actual database municipalities with no sources."""

    print("\n" + "=" * 80)
    print("DATABASE TEST — Finding sources for municipalities without coverage")
    print("=" * 80)

    db = SessionLocal()

    # Get high-population CA cities without sources
    ca_cities = db.query(Municipality).filter(
        Municipality.state == "CA",
        Municipality.population > 50000,
        Municipality.domain_status == "verified"
    ).outerjoin(Municipality.sources).group_by(Municipality.id).having(
        db.func.count(Municipality.sources) == 0
    ).limit(5).all()

    print(f"\nTesting {len(ca_cities)} high-population CA cities without sources:")
    for muni in ca_cities:
        print(f"  - {muni.name} (pop {muni.population:,}) — {muni.domain}")

    db.close()

    if not ca_cities:
        print("\nNo cities found without sources - test skipped")
        return

    async def test_batch():
        async with JSSourceDiscovery(timeout=15000) as js_discovery:
            for muni in ca_cities:
                print(f"\n{'-' * 60}")
                print(f"{muni.name}, CA (pop {muni.population:,})")
                print(f"Domain: {muni.domain}")

                # Build test URLs
                base_urls = [f"https://www.{muni.domain}", f"https://{muni.domain}"]
                test_urls = []
                for base in base_urls[:1]:
                    for pattern in TEST_PATTERNS[:6]:
                        test_urls.append(f"{base}{pattern}")

                print(f"Testing {len(test_urls)} URL patterns with JS rendering...")

                found_count = 0
                for url in test_urls:
                    result = await js_discovery.check_url(url)
                    if result:
                        final_url, platform = result
                        print(f"  ✓ FOUND: {final_url[:70]}")
                        print(f"    Platform: {platform}")
                        found_count += 1
                        break  # Stop after first find

                if found_count == 0:
                    print(f"  ✗ No sources found")

    asyncio.run(test_batch())

    print(f"\n{'=' * 80}")
    print("DATABASE TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    print("\nJavaScript Discovery Validation")
    print("Testing Playwright-based rendering on tech-forward municipal sites\n")

    # Run comparison test
    test_static_vs_js()

    # Run database test
    # test_from_database()  # Uncomment to test with actual DB data

    print("\n✅ Testing complete!")
    print("\nNext step: Integrate JS discovery into src/discovery.py as fallback")
