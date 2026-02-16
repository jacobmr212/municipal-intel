# City Database Population Scripts

Tools to expand the municipality database with comprehensive US city data.

## Quick Start

### Option 1: US Census Bureau API (Recommended)

Gets official population data from the 2020 Census:

```bash
cd ~/Desktop/municipal-intel
source venv/bin/activate
python scripts/populate_cities.py
```

**What it does:**
- Fetches all US cities with population ≥ 5,000
- Gets official 2020 Census population counts
- Auto-generates likely domain names
- Preserves manually-verified domains from existing database
- Outputs to `data/municipalities.json`

**Result:** ~3,000-4,000 cities across all 50 states

---

### Option 2: Download Pre-Built Database

If the Census API is down, download a pre-built database:

1. Go to: https://www.census.gov/data/tables/time-series/demo/popest/2020s-total-cities-and-towns.html
2. Download city population data
3. Or use SimpleMaps: https://simplemaps.com/data/us-cities (free basic version)

---

## Configuration

Edit `populate_cities.py` to adjust:

```python
# Line 11: Minimum population threshold
MIN_POPULATION = 5000  # Change to 1000 for smaller cities

# Line 117-124: Domain generation patterns
# Customize for your target region's naming conventions
```

---

## Manual Domain Verification

The script auto-generates domain guesses, but for best results, manually verify domains for your target markets:

### Common Municipal Domain Patterns:

```
cityname.gov
cityofcityname.org
cityname-state.gov
cityname.org
cityname.us
cityofcityname.com
```

### How to Verify:

1. Google: `"city name" official website`
2. Check city Wikipedia page
3. Verify domain loads and has meeting minutes section

### Update Domains:

Edit `data/municipalities.json` directly:

```json
{
  "name": "Smallville",
  "population": 8500,
  "domain": "smallville-ut.gov"  ← Change this
}
```

---

## Adding Individual Cities

To manually add a city without running the full script:

```bash
cd data
# Edit municipalities.json
# Add to the appropriate state:

{
  "name": "Your City",
  "population": 12000,
  "domain": "yourcity.gov"
}
```

---

## Database Structure

```json
{
  "metadata": {
    "description": "...",
    "last_updated": "2026-02-15",
    "sources": "US Census Bureau 2020",
    "min_population": 5000
  },
  "states": {
    "UT": {
      "name": "Utah",
      "municipalities": [
        {
          "name": "Salt Lake City",
          "population": 200133,
          "domain": "slc.gov"
        }
      ]
    }
  }
}
```

---

## Troubleshooting

### Census API Not Working?

The Census API can be rate-limited or temporarily down. Alternatives:

1. **Use cached data:** Some states already have full coverage
2. **Download CSV:** Get data from census.gov and parse manually
3. **Use SimpleMaps:** Free basic dataset with 30K+ cities

### Domain Guesses Wrong?

This is expected! The script makes educated guesses. For production use:

1. Focus on your target states/markets
2. Manually verify domains for cities you'll actually scan
3. Use the discovery engine to auto-detect - it will find alternate URLs

### Too Many Cities?

Increase `MIN_POPULATION` to reduce the dataset:

```python
MIN_POPULATION = 10000  # Only cities over 10K
```

Or filter by state:

```python
# Only include specific states
STATES_TO_INCLUDE = ["UT", "ID", "WY", "MT", "CO"]
```

---

## Next Steps After Population

1. Run the populate script
2. Manually verify domains for your top 50 target cities
3. Test the app with different population filters
4. Deploy to Streamlit Cloud with expanded database
5. Share with your team!

