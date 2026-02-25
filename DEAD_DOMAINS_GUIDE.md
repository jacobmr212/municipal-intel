# Dead Domain Management Guide

After nationwide enrichment, you'll have ~2,195 municipalities with dead domains. This guide helps you fix them efficiently.

---

## Quick Stats

Run this to see the scope:
```bash
python3 scripts/manage_dead_domains.py --list | tail -1
```

---

## CLI Tool Usage

### 1. List Dead Domains

**All dead domains:**
```bash
python3 scripts/manage_dead_domains.py --list
```

**Filter by state:**
```bash
python3 scripts/manage_dead_domains.py --list --state CA
python3 scripts/manage_dead_domains.py --list --state TX
```

**High-priority only (pop > 50K):**
```bash
python3 scripts/manage_dead_domains.py --list --min-pop 50000
```

**Top 20 by population:**
```bash
python3 scripts/manage_dead_domains.py --list --limit 20
```

**Combine filters:**
```bash
python3 scripts/manage_dead_domains.py --list --state CA --min-pop 100000 --limit 10
```

### 2. Update a Single Domain

When you manually find the correct domain:

```bash
python3 scripts/manage_dead_domains.py \
  --update "Oceanside" \
  --state CA \
  --domain ci.oceanside.ca.us
```

**Update and re-enrich immediately:**
```bash
python3 scripts/manage_dead_domains.py \
  --update "Oceanside" \
  --state CA \
  --domain ci.oceanside.ca.us \
  --reenrich
```

This will:
1. Update the domain in the database
2. Clear existing sources
3. Re-run enrichment to discover sources

### 3. Export to CSV for Batch Research

**Export all dead domains:**
```bash
python3 scripts/manage_dead_domains.py --export dead_domains.csv
```

**Export high-priority only:**
```bash
python3 scripts/manage_dead_domains.py --export priority_dead.csv --min-pop 50000
```

**Export by state:**
```bash
python3 scripts/manage_dead_domains.py --export ca_dead_domains.csv --state CA
```

The CSV includes:
- Municipality ID (for updates)
- Municipality name
- State
- Population
- Dead Domain
- **Corrected Domain** (empty - fill this in)
- **Notes** (empty - for your research notes)

### 4. Batch Update from CSV

After filling in the "Corrected Domain" column:

```bash
python3 scripts/manage_dead_domains.py --batch-update dead_domains_corrected.csv
```

**Batch update and re-enrich:**
```bash
python3 scripts/manage_dead_domains.py --batch-update dead_domains_corrected.csv --reenrich
```

---

## API Endpoints

All endpoints require authentication (JWT token).

### GET /api/dead-domains

List dead domains via API.

**Query params:**
- `state` - Filter by state (e.g., `CA`, `TX`)
- `min_population` - Minimum population
- `limit` - Max results

**Example:**
```bash
curl "https://your-app.railway.app/api/dead-domains?state=CA&min_population=50000&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "total": 10,
  "municipalities": [
    {
      "id": "uuid",
      "name": "Oceanside",
      "state": "CA",
      "population": 174068,
      "dead_domain": "oceansidecity.org",
      "resolved_url": null
    }
  ]
}
```

### PATCH /api/municipalities/{municipality_id}/domain

Update domain for a municipality.

**Body:**
```json
{
  "new_domain": "ci.oceanside.ca.us",
  "reenrich": true
}
```

**Example:**
```bash
curl -X PATCH "https://your-app.railway.app/api/municipalities/{id}/domain" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_domain": "ci.oceanside.ca.us",
    "reenrich": true
  }'
```

**Response:**
```json
{
  "success": true,
  "municipality": {
    "id": "uuid",
    "name": "Oceanside",
    "state": "CA",
    "old_domain": "oceansidecity.org",
    "new_domain": "ci.oceanside.ca.us",
    "old_status": "dead",
    "new_status": "unverified"
  },
  "reenrichment": "started"
}
```

### GET /api/dead-domains/export

Download CSV of dead domains.

**Query params:**
- `state` - Filter by state
- `min_population` - Minimum population

**Example:**
```bash
curl "https://your-app.railway.app/api/dead-domains/export?min_population=50000" \
  -H "Authorization: Bearer $TOKEN" \
  -O -J
```

Downloads: `dead_domains_20260225.csv`

### GET /api/dead-domains/stats

Get statistics about dead domains.

**Example:**
```bash
curl "https://your-app.railway.app/api/dead-domains/stats" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "total_dead": 2195,
  "high_priority": 156,
  "by_state": [
    {"state": "FL", "count": 310},
    {"state": "NJ", "count": 243},
    {"state": "MD", "count": 169}
  ]
}
```

---

## Recommended Workflow

### Phase 1: High-Priority Cities (Pop > 100K)

These have the highest lead potential:

```bash
# Export to CSV
python3 scripts/manage_dead_domains.py --export priority_100k.csv --min-pop 100000

# Opens ~50-100 cities
# Research correct domains manually
# Fill in "Corrected Domain" column
# Save as priority_100k_corrected.csv

# Batch update
python3 scripts/manage_dead_domains.py --batch-update priority_100k_corrected.csv --reenrich
```

### Phase 2: Mid-Size Cities (Pop 50K-100K)

```bash
python3 scripts/manage_dead_domains.py --export priority_50k.csv --min-pop 50000
# ... research and correct ...
python3 scripts/manage_dead_domains.py --batch-update priority_50k_corrected.csv --reenrich
```

### Phase 3: State-by-State (Focus on high-count states)

From stats, focus on states with most dead domains:

```bash
# Florida has 310 dead domains
python3 scripts/manage_dead_domains.py --export fl_dead.csv --state FL
# ... research and correct ...
python3 scripts/manage_dead_domains.py --batch-update fl_dead_corrected.csv --reenrich
```

---

## Common Patterns

Many dead domains follow predictable patterns:

| Dead Domain | Likely Correct Domain |
|-------------|----------------------|
| `cityname.org` | `ci.cityname.state.us` |
| `cityname.gov` | `www.cityname.gov` |
| `citynamecity.org` | `cityname-city.org` |
| `citynamecity.org` | `cityofcityname.org` |
| `cdpcity.org` | (CDPs often don't have official sites) |

### CDPs (Census Designated Places)

Many "dead" domains are CDPs (Census Designated Places) which don't have official government websites. These can often be skipped unless they're very large.

**Identify CDPs:**
```bash
python3 scripts/manage_dead_domains.py --list | grep "CDP"
```

---

## Tips for Finding Correct Domains

1. **Google Search**: `"[City Name] [State] official website"`

2. **Wikipedia**: Often lists official website in infobox

3. **State Municipal Associations**:
   - California: `www.cacities.org`
   - Texas: `www.tml.org`
   - Florida: `www.flcities.com`

4. **Domain Patterns**:
   - `.gov` domains (federal standard)
   - `ci.[city].[state].us` (common format)
   - `cityof[city].org` (common format)

5. **Social Media**: Check Facebook/Twitter official pages for website links

---

## Example: Fixing Oceanside, CA

**Step 1: Find dead domain**
```bash
python3 scripts/manage_dead_domains.py --list --state CA --min-pop 100000 --limit 5
```

Output shows: `Oceanside - oceansidecity.org`

**Step 2: Research**
- Google: "Oceanside California official website"
- Result: `www.ci.oceanside.ca.us`

**Step 3: Update**
```bash
python3 scripts/manage_dead_domains.py \
  --update "Oceanside" \
  --state CA \
  --domain ci.oceanside.ca.us \
  --reenrich
```

**Step 4: Verify**
Check enrichment log or database:
```bash
# Check sources found
psql $DATABASE_URL -c "SELECT COUNT(*) FROM municipal_sources WHERE municipality_id IN (SELECT id FROM municipalities WHERE name='Oceanside' AND state='CA');"
```

---

## Automation Ideas

### Script to Auto-Test Domains

Create a script to test common patterns:

```python
# scripts/auto_fix_domains.py
patterns = [
    "www.ci.{city}.{state}.us",
    "www.cityof{city}.org",
    "{city}-city.org",
    "www.{city}.gov"
]

for dead_domain in dead_domains:
    for pattern in patterns:
        test_domain = pattern.format(city=city_name.lower().replace(' ', ''), state=state.lower())
        if test_domain_alive(test_domain):
            update_domain(city_name, state, test_domain)
            break
```

### Bulk Correction via API

Use the API to update multiple domains programmatically:

```python
import requests

token = "your-jwt-token"
corrections = {
    "uuid-1": "ci.oceanside.ca.us",
    "uuid-2": "www.ventura.org",
    # ... more corrections
}

for muni_id, new_domain in corrections.items():
    response = requests.patch(
        f"https://your-app.railway.app/api/municipalities/{muni_id}/domain",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_domain": new_domain, "reenrich": True}
    )
    print(f"Updated {muni_id}: {response.json()}")
```

---

## Summary

**Total dead domains**: ~2,195 (expected from enrichment)

**Recommended priority**:
1. ✅ Pop > 100K (50-100 cities) - Highest lead potential
2. ✅ Pop 50K-100K (~150 cities) - High lead potential
3. ⚠️ Pop 25K-50K (~500 cities) - Medium lead potential
4. ❌ CDPs and pop < 25K (~1,500 cities) - Low priority

**Tools available**:
- ✅ CLI tool for viewing, updating, exporting
- ✅ API endpoints for programmatic access
- ✅ CSV export for batch research
- ✅ Batch update from corrected CSV

**Estimated time**:
- Phase 1 (100K+): 2-4 hours research + instant update
- Phase 2 (50K-100K): 4-6 hours research + instant update
- Phase 3 (State focus): Ongoing as needed

This will significantly improve coverage quality for high-value municipalities! 🎯
