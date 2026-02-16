#!/usr/bin/env python3
"""
Test script to manually discover meeting minutes pages for failed Minnesota cities.
"""

import requests
import time
from bs4 import BeautifulSoup

# Test cities (mid-sized MN cities likely to have failed)
TEST_CITIES = [
    ("Blaine", "blainecity.org"),
    ("Lakeville", "lakevillecity.org"),
    ("Eagan", "eagancity.org"),
    ("Burnsville", "burnsvillecity.org"),
    ("Eden Prairie", "edenprairiecity.org"),
]

# Top 12 URL patterns to test
PATTERNS_TO_TEST = [
    "/AgendaCenter",
    "/agendacenter",
    "/Archive.aspx",
    "/DocumentCenter",
    "/Meetings.aspx",
    "/meetings",
    "/city-council/meetings",
    "/council/meetings",
    "/government/city-council",
    "/city-clerk/agendas-minutes",
    "/agendas-minutes",
    "/minutes",
]

def check_url(url, timeout=5):
    """Check if URL exists and contains meeting content."""
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code != 200:
            return None

        if "html" not in response.headers.get("content-type", ""):
            return None

        html_lower = response.text.lower()

        # Check for meeting indicators
        indicators = ["meeting", "agenda", "minutes", "council"]
        count = sum(1 for ind in indicators if ind in html_lower)

        if count >= 2:
            # Check platform
            platform = "html"
            if "agendacenter" in url.lower() or "civicplus" in html_lower:
                platform = "civicplus"
            elif "granicus" in html_lower or "legistar" in html_lower:
                platform = "granicus"

            return (response.url, platform, count)
    except:
        pass

    return None

def test_city(name, domain):
    """Test all patterns for a city."""
    print(f"\n{'='*70}")
    print(f"Testing: {name} ({domain})")
    print(f"{'='*70}")

    base_urls = [f"https://www.{domain}", f"https://{domain}"]
    found = []

    for base_url in base_urls:
        for pattern in PATTERNS_TO_TEST:
            url = f"{base_url}{pattern}"
            result = check_url(url)

            if result:
                found_url, platform, score = result
                print(f"✓ FOUND: {pattern}")
                print(f"  URL: {found_url}")
                print(f"  Platform: {platform}")
                print(f"  Score: {score}/4 indicators")
                found.append((pattern, found_url, platform))
                break  # Stop after first match

        if found:
            break

    if not found:
        print("✗ NO SOURCES FOUND with standard patterns")
        print("\nTrying homepage to see what's there...")
        for base_url in base_urls:
            result = check_url(base_url)
            if result:
                print(f"  Homepage exists: {base_url}")
                # Try to find meeting links on homepage
                try:
                    resp = requests.get(base_url, timeout=5)
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    links = soup.find_all('a', href=True)

                    meeting_links = []
                    for link in links[:100]:  # Check first 100 links
                        text = link.get_text().lower()
                        href = link['href'].lower()
                        if any(word in text or word in href for word in ['agenda', 'meeting', 'minutes', 'council']):
                            meeting_links.append(f"    - {link.get_text().strip()}: {link['href']}")

                    if meeting_links:
                        print("\n  Potential meeting links found on homepage:")
                        for ml in meeting_links[:5]:
                            print(ml)
                except:
                    pass
                break

    return found

if __name__ == "__main__":
    print("DISCOVERY DIAGNOSTIC: Testing Failed Minnesota Cities")
    print("="*70)

    all_results = {}
    for name, domain in TEST_CITIES:
        results = test_city(name, domain)
        all_results[name] = results
        time.sleep(1)  # Be respectful

    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    successful = [city for city, results in all_results.items() if results]
    print(f"\nSuccess Rate: {len(successful)}/{len(TEST_CITIES)} ({len(successful)/len(TEST_CITIES)*100:.0f}%)")

    if successful:
        print("\nSuccessful patterns:")
        for city in successful:
            if all_results[city]:
                pattern, url, platform = all_results[city][0]
                print(f"  {city}: {pattern} → {platform}")

    failed = [city for city, results in all_results.items() if not results]
    if failed:
        print(f"\nFailed cities ({len(failed)}): {', '.join(failed)}")
        print("  These cities likely use non-standard paths or platforms")
