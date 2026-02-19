#!/usr/bin/env python3
"""
Explore Nevada notice.nv.gov portal to understand data access patterns.
Based on web research: portal has City/County/State/K-12/Special District filters.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

BASE_URL = "https://notice.nv.gov"

def explore_homepage():
    """Examine the homepage structure and navigation."""
    print("=" * 80)
    print("EXPLORING NEVADA PORTAL HOMEPAGE")
    print("=" * 80)

    try:
        response = requests.get(BASE_URL, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        print(f"\nStatus: {response.status_code}")
        print(f"Title: {soup.title.text if soup.title else 'No title'}")

        # Look for navigation/filter options
        links = soup.find_all('a', href=True)
        print(f"\nTotal links: {len(links)}")

        # Filter for city/county/municipal links
        municipal_links = []
        for link in links:
            href = link.get('href', '')
            text = link.text.strip().lower()

            if any(term in text for term in ['city', 'county', 'municipal', 'local', 'government']):
                municipal_links.append({
                    'text': link.text.strip(),
                    'href': href
                })

        if municipal_links:
            print(f"\nMunicipal-related links ({len(municipal_links)}):")
            for link in municipal_links[:15]:
                print(f"  - {link['text']}: {link['href']}")

        # Look for forms (search/filter)
        forms = soup.find_all('form')
        print(f"\n\nForms found: {len(forms)}")
        for i, form in enumerate(forms):
            print(f"\nForm {i+1}:")
            print(f"  Action: {form.get('action', 'None')}")
            print(f"  Method: {form.get('method', 'GET')}")

            inputs = form.find_all(['input', 'select', 'textarea'])
            if inputs:
                print(f"  Inputs ({len(inputs)}):")
                for inp in inputs[:10]:
                    name = inp.get('name', 'unnamed')
                    inp_type = inp.get('type', inp.name)
                    print(f"    - {name} ({inp_type})")

                    # If it's a select with options, show them
                    if inp.name == 'select':
                        options = inp.find_all('option')
                        if options:
                            print(f"      Options: {[opt.text.strip() for opt in options[:5]]}")

        # Look for JavaScript files that might handle data
        scripts = soup.find_all('script', src=True)
        print(f"\n\nJavaScript files:")
        for script in scripts[:10]:
            src = script.get('src')
            print(f"  - {src}")

        # Check for API endpoints in page source
        page_text = response.text
        api_patterns = [
            r'/api/[^"\']+',
            r'/search[^"\']*',
            r'/notices[^"\']*',
            r'/public[^"\']*'
        ]

        print(f"\n\nPotential API endpoints:")
        for pattern in api_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            if matches:
                unique = list(set(matches))[:5]
                print(f"  Pattern '{pattern}': {unique}")

    except Exception as e:
        print(f"Error: {e}")


def try_search_patterns():
    """Try common search/filter URL patterns."""
    print("\n" + "=" * 80)
    print("TRYING COMMON SEARCH PATTERNS")
    print("=" * 80)

    # Common government notice portal patterns
    test_urls = [
        f"{BASE_URL}/search",
        f"{BASE_URL}/notices",
        f"{BASE_URL}/public-notices",
        f"{BASE_URL}/meetings",
        f"{BASE_URL}/agendas",
        f"{BASE_URL}/city",
        f"{BASE_URL}/cities",
        f"{BASE_URL}/county",
        f"{BASE_URL}/local",
        f"{BASE_URL}/browse",
        f"{BASE_URL}/list",
    ]

    for url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {url} (HTTP 200)")

                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'json' in content_type:
                    print(f"    → JSON response")
                    try:
                        data = response.json()
                        print(f"    → Keys: {list(data.keys())[:5]}")
                    except:
                        pass
                elif 'html' in content_type:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    title = soup.title.text if soup.title else 'No title'
                    print(f"    → HTML: {title[:60]}")
            else:
                print(f"  ✗ {url} (HTTP {response.status_code})")
        except Exception as e:
            print(f"  ✗ {url} ({str(e)[:40]})")


def try_city_filters():
    """Try to access city-specific notices."""
    print("\n" + "=" * 80)
    print("TRYING CITY FILTER PATTERNS")
    print("=" * 80)

    # Test cities in Nevada
    test_cities = [
        'Las Vegas',
        'Henderson',
        'Reno',
        'Carson City',
        'Sparks',
    ]

    # Try different parameter patterns
    param_patterns = [
        {'city': '{city}'},
        {'entity_type': 'city', 'entity_name': '{city}'},
        {'jurisdiction': '{city}'},
        {'agency': '{city}'},
        {'q': '{city}'},
        {'search': '{city}'},
    ]

    for city in test_cities[:2]:  # Test just 2 to be quick
        print(f"\n{city}:")
        for pattern in param_patterns:
            params = {k: v.format(city=city) for k, v in pattern.items()}

            try:
                response = requests.get(BASE_URL, params=params, timeout=5)

                # Check if URL changed (might indicate search worked)
                if '?' in response.url:
                    print(f"  Pattern {pattern}: {response.url[-60:]}")

                    # Check for results indicators
                    soup = BeautifulSoup(response.text, 'html.parser')
                    results = soup.find_all(['table', 'div'], class_=re.compile('result|notice|meeting'))
                    if results:
                        print(f"    → Found {len(results)} potential result containers")

            except Exception as e:
                pass


def check_robots_sitemap():
    """Check robots.txt and sitemap for clues."""
    print("\n" + "=" * 80)
    print("CHECKING ROBOTS.TXT AND SITEMAP")
    print("=" * 80)

    # Check robots.txt
    try:
        response = requests.get(f"{BASE_URL}/robots.txt", timeout=5)
        if response.status_code == 200:
            print("\nrobots.txt:")
            lines = response.text.split('\n')[:20]
            for line in lines:
                if line.strip():
                    print(f"  {line}")
    except:
        print("\nNo robots.txt found")

    # Check for sitemap
    sitemap_urls = [
        f"{BASE_URL}/sitemap.xml",
        f"{BASE_URL}/sitemap_index.xml",
        f"{BASE_URL}/sitemap/index.xml",
    ]

    for url in sitemap_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"\n✓ Found sitemap: {url}")
                # Parse first few URLs
                soup = BeautifulSoup(response.text, 'xml')
                locs = soup.find_all('loc')[:10]
                if locs:
                    print("  Sample URLs:")
                    for loc in locs[:5]:
                        print(f"    - {loc.text}")
                break
        except:
            pass


if __name__ == "__main__":
    explore_homepage()
    try_search_patterns()
    try_city_filters()
    check_robots_sitemap()

    print("\n" + "=" * 80)
    print("EXPLORATION COMPLETE")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review output to identify data access pattern")
    print("2. Build scraper based on discovered endpoints")
    print("3. Test with sample Nevada cities")
