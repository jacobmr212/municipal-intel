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

**IMPORTANT**: Small towns (2.5K-25K population) are often the **most valuable** targets:
- Less competition (big vendors ignore them)
- Easier to win (simpler RFP processes)
- Higher close rates (personal relationships)
- Better margins (less price pressure)
- Longer retention (fewer alternatives)

**Don't skip small towns!** They're gold mines that competitors overlook.

---

### Strategy 1: State-by-State (Recommended)

Focus on your target states, **all municipalities regardless of size**:

```bash
# Export all dead domains in target state
python3 scripts/manage_dead_domains.py --export utah_dead.csv --state UT

# Research correct domains for ALL cities (small towns matter!)
# Fill in "Corrected Domain" column
# Save as utah_dead_corrected.csv

# Batch update
python3 scripts/manage_dead_domains.py --batch-update utah_dead_corrected.csv --reenrich
```

**Why this works**:
- You know the local domain patterns (e.g., Utah uses `.ut.us`)
- Small towns in your territory = warm leads
- Complete coverage in your sales region

---

### Strategy 2: Tier-Based (Match Your Sales Focus)

Focus on the tier that matches your current sales pipeline:

```bash
# Small towns (2.5K-10K) - Often MOST valuable!
python3 scripts/manage_dead_domains.py --export small_towns.csv --min-pop 2500 --max-pop 10000

# Small-Mid tier (10K-25K)
python3 scripts/manage_dead_domains.py --export small_mid.csv --min-pop 10000 --max-pop 25000

# Mid-market (25K-50K)
python3 scripts/manage_dead_domains.py --export mid_market.csv --min-pop 25000 --max-pop 50000
```

**Pro tip**: Start with small towns in states where you already have customers. They're more likely to trust a vendor their neighbors use.

---

### Strategy 3: Quick Wins (CDPs can be skipped)

CDPs (Census Designated Places) are unincorporated areas without official governments. Skip these to focus on actual municipalities:

```bash
# Export all non-CDP dead domains
python3 scripts/manage_dead_domains.py --export real_cities.csv --exclude-cdp

# Much smaller list, all actual municipalities
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

**Recommended priority** (Focus on small towns!):
1. 🎯 **Pop 2.5K-10K** (~600 cities) - **HIGHEST VALUE** (less competition, easier wins)
2. 🎯 **Pop 10K-25K** (~400 cities) - **HIGH VALUE** (still overlooked by big vendors)
3. ✅ Pop 25K-50K (~500 cities) - Good lead potential
4. ✅ Pop 50K-100K (~150 cities) - Good lead potential
5. ⚠️ Pop > 100K (50-100 cities) - Competitive but high profile
6. ❌ CDPs (~500 cities) - Unincorporated areas, often no official government website

**Tools available**:
- ✅ CLI tool for viewing, updating, exporting
- ✅ API endpoints for programmatic access
- ✅ CSV export for batch research
- ✅ Batch update from corrected CSV

**Estimated time** (State-by-State Approach):
- Small state (UT, ID): 1-2 hours per state
- Medium state (CO, WA): 3-4 hours per state
- Large state (CA, TX, FL): 6-8 hours per state

**Workflow**:
```bash
# Focus on YOUR sales territories first!
# Example: Utah (all municipalities, prioritize small towns)
python3 scripts/manage_dead_domains.py --export utah_all.csv --state UT
# Fix domains, then:
python3 scripts/manage_dead_domains.py --batch-update utah_all_corrected.csv --reenrich
```

This will significantly improve coverage quality for the **small towns competitors miss**! 🎯
