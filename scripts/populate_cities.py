"""
Populate municipalities database with comprehensive US city data.
Uses Census Bureau data + web research for domains.
"""

import json
import requests
import time
from pathlib import Path

# Minimum population threshold
MIN_POPULATION = 5000

def fetch_census_cities():
    """
    Fetch cities from US Census Bureau API.
    This gets incorporated places (cities, towns, villages) with population data.
    """
    print("Fetching cities from US Census Bureau API...")

    # Try 2023 Population Estimates first (most recent)
    print("Attempting to fetch 2023 Population Estimates...")
    url_2023 = "https://api.census.gov/data/2023/pep/population"

    params_2023 = {
        "get": "NAME,POP_2023",  # Name and 2023 population estimate
        "for": "place:*",         # All places
        "in": "state:*",          # All states
    }

    try:
        response = requests.get(url_2023, params=params_2023, timeout=30)
        response.raise_for_status()
        data = response.json()
        headers = data[0]
        rows = data[1:]
        print(f"✓ Fetched {len(rows)} places from 2023 Population Estimates")
        return headers, rows, "2023"
    except Exception as e:
        print(f"✗ 2023 estimates failed: {e}")
        print("Falling back to 2020 Census data...")

    # Fallback to 2020 Census data
    url_2020 = "https://api.census.gov/data/2020/dec/pl"

    params_2020 = {
        "get": "NAME,P1_001N",  # Name and total population
        "for": "place:*",        # All places
        "in": "state:*",         # All states
    }

    try:
        response = requests.get(url_2020, params=params_2020, timeout=30)
        response.raise_for_status()
        data = response.json()

        # First row is headers
        headers = data[0]
        rows = data[1:]

        print(f"✓ Fetched {len(rows)} places from 2020 Census")
        return headers, rows, "2020"

    except Exception as e:
        print(f"✗ Census API failed: {e}")
        return None, None, None


def parse_census_data(headers, rows):
    """Parse Census data into structured format."""
    cities_by_state = {}

    name_idx = headers.index("NAME")

   # Try different population field names (depends on data source)
    pop_field = None
    for field in ["POP_2023", "POP_2022", "P1_001N"]:
        if field in headers:
            pop_field = field
            break

    if not pop_field:
        print("ERROR: Could not find population field in data")
        return cities_by_state

    pop_idx = headers.index(pop_field)
    state_idx = headers.index("state")

    state_fips = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
        "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
        "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
        "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
        "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
        "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
        "56": "WY", "72": "PR"
    }

    for row in rows:
        state_fips_code = row[state_idx]
        state_abbr = state_fips.get(state_fips_code)

        if not state_abbr:
            continue

        name = row[name_idx]
        population = int(row[pop_idx])

        # Clean up name (remove state suffix and type)
        name = name.split(",")[0]  # Remove ", State" part
        name = name.replace(" city", "").replace(" town", "").replace(" village", "")

        # Filter by minimum population
        if population < MIN_POPULATION:
            continue

        if state_abbr not in cities_by_state:
            cities_by_state[state_abbr] = []

        cities_by_state[state_abbr].append({
            "name": name,
            "population": population,
            "domain": ""  # Will be filled in later
        })

    # Sort by population (descending) within each state
    for state in cities_by_state:
        cities_by_state[state].sort(key=lambda x: x["population"], reverse=True)

    return cities_by_state


def generate_domain_guess(city_name, state_abbr):
    """
    Generate likely domain name for a municipality.
    This is a best guess - manual verification recommended.
    """
    # Common patterns for municipal websites
    city_clean = city_name.lower()
    city_clean = city_clean.replace(" ", "")
    city_clean = city_clean.replace(".", "")
    city_clean = city_clean.replace("'", "")

    state_lower = state_abbr.lower()

    # Common domain patterns (in order of likelihood)
    patterns = [
        f"{city_clean}city.org",
        f"{city_clean}{state_lower}.gov",
        f"cityof{city_clean}.org",
        f"cityof{city_clean}.com",
        f"{city_clean}.gov",
        f"{city_clean}city.com",
        f"{city_clean}-{state_lower}.gov",
        f"{city_clean}.org",
    ]

    return patterns[0]  # Return most likely


def main():
    """Main script to populate cities."""

    print("="*60)
    print("Municipal Intel - City Database Population Script")
    print("="*60)
    print()

    # Fetch Census data
    headers, rows, data_year = fetch_census_cities()

    if not headers or not rows:
        print("Failed to fetch Census data")
        return

    # Parse data
    print(f"\nParsing {data_year} Census data...")
    cities_by_state = parse_census_data(headers, rows)

    total_cities = sum(len(cities) for cities in cities_by_state.values())
    print(f"✓ Parsed {total_cities} cities across {len(cities_by_state)} states")
    print(f"  (Minimum population: {MIN_POPULATION:,})")

    # Show sample
    print("\nSample cities by state:")
    for state in sorted(list(cities_by_state.keys())[:5]):
        cities = cities_by_state[state]
        print(f"  {state}: {len(cities)} cities (largest: {cities[0]['name']} - {cities[0]['population']:,})")

    # Load existing database to preserve domains
    db_path = Path(__file__).parent.parent / "data" / "municipalities.json"
    existing_db = {}

    if db_path.exists():
        print(f"\n✓ Found existing database at {db_path}")
        with open(db_path) as f:
            existing_db = json.load(f)

    # Merge with existing data (preserve manually-verified domains)
    print("\nMerging with existing database...")

    state_names = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
        "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
        "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
        "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
        "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
        "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
        "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
        "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming"
    }

    new_db = {
        "metadata": {
            "description": "Comprehensive municipality database for Municipal Intel",
            "last_updated": "2026-02-15",
            "sources": f"US Census Bureau {data_year}, municipal website surveys",
            "data_year": data_year,
            "min_population": MIN_POPULATION
        },
        "states": {}
    }

    for state_abbr, cities in cities_by_state.items():
        # Get existing domains if available
        existing_cities = {}
        if "states" in existing_db and state_abbr in existing_db["states"]:
            for city in existing_db["states"][state_abbr].get("municipalities", []):
                existing_cities[city["name"]] = city.get("domain", "")

        # Build new city list
        new_cities = []
        for city in cities:
            # Use existing domain if available, otherwise generate guess
            domain = existing_cities.get(city["name"], "")
            if not domain:
                domain = generate_domain_guess(city["name"], state_abbr)

            new_cities.append({
                "name": city["name"],
                "population": city["population"],
                "domain": domain
            })

        new_db["states"][state_abbr] = {
            "name": state_names.get(state_abbr, state_abbr),
            "municipalities": new_cities
        }

    # Save new database
    print(f"\nSaving to {db_path}...")
    db_path.parent.mkdir(exist_ok=True)

    with open(db_path, "w") as f:
        json.dump(new_db, f, indent=2)

    print("\n" + "="*60)
    print("✓ DATABASE UPDATED SUCCESSFULLY")
    print("="*60)
    print(f"Total states: {len(new_db['states'])}")
    print(f"Total cities: {sum(len(s['municipalities']) for s in new_db['states'].values())}")
    print()
    print("Note: Domain names are auto-generated guesses.")
    print("For best results, manually verify domains for target cities.")
    print("="*60)


if __name__ == "__main__":
    main()
