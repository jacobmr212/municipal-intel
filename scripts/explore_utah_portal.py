#!/usr/bin/env python3
"""
Explore Utah PMN portal to reverse-engineer the data access method.
"""

import requests
from bs4 import BeautifulSoup
import json
import re

BASE_URL = "https://www.utah.gov/pmn"

def explore_search_form():
    """Try to submit a search and see what happens."""
    print("=" * 80)
    print("EXPLORING SEARCH FORM")
    print("=" * 80)

    # Try searching for "Provo" to see the request
    session = requests.Session()

    # First, get the search page to see if there are any hidden fields
    response = session.get(f"{BASE_URL}/search.html")
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all forms
    forms = soup.find_all('form')
    print(f"\nFound {len(forms)} form(s)")

    for i, form in enumerate(forms):
        print(f"\nForm {i+1}:")
        print(f"  Action: {form.get('action', 'None')}")
        print(f"  Method: {form.get('method', 'GET')}")

        inputs = form.find_all(['input', 'select', 'textarea'])
        print(f"  Inputs: {len(inputs)}")
        for inp in inputs[:5]:  # Show first 5
            print(f"    - {inp.get('name')}: {inp.get('type', 'select')}")

    # Look for JavaScript files
    scripts = soup.find_all('script', src=True)
    print(f"\n\nJavaScript files:")
    for script in scripts:
        src = script.get('src')
        if 'pmn' in src or 'search' in src or 'entity' in src:
            print(f"  - {src}")


def try_direct_ids():
    """Try accessing public body pages directly with sequential IDs."""
    print("\n" + "=" * 80)
    print("TRYING DIRECT PUBLIC BODY IDs")
    print("=" * 80)

    # We know 6239 is Herriman. Try a few around it.
    test_ids = [6237, 6238, 6239, 6240, 6241, 6250, 6260]

    for pb_id in test_ids:
        url = f"{BASE_URL}/sitemap/publicbody/{pb_id}.html"
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Try to find the entity name
                h1 = soup.find('h1')
                title = h1.text.strip() if h1 else "Unknown"

                # Count notices
                table = soup.find('table')
                rows = table.find_all('tr') if table else []

                print(f"  ✓ {pb_id}: {title} ({len(rows)-1} notices)")
            else:
                print(f"  ✗ {pb_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  ✗ {pb_id}: {str(e)[:50]}")


def search_for_municipality():
    """Try to search for a specific municipality and capture the request."""
    print("\n" + "=" * 80)
    print("ATTEMPTING SEARCH FOR 'PROVO'")
    print("=" * 80)

    session = requests.Session()

    # Try a simple search with keywords
    params = {
        'entity_name': 'Provo',
        'keywords': '',
    }

    try:
        response = session.get(f"{BASE_URL}/search.html", params=params)
        print(f"Status: {response.status_code}")
        print(f"URL: {response.url}")

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for results
        results = soup.find_all(['table', 'div'], class_=re.compile('result|notice|meeting'))
        print(f"Potential result containers: {len(results)}")

        # Look for links to public bodies
        links = soup.find_all('a', href=re.compile(r'/publicbody/\d+'))
        if links:
            print(f"\nFound {len(links)} public body links:")
            for link in links[:10]:
                print(f"  - {link.text.strip()}: {link.get('href')}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    explore_search_form()
    try_direct_ids()
    search_for_municipality()
