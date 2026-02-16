# Municipal Intel - Architecture Documentation

## Overview

Municipal Intel is a Government ERP Lead Intelligence Platform that scans municipal meeting minutes for procurement signals. The system uses a **database-driven architecture** that separates offline enrichment from live scanning, enabling fast, scalable operations.

## Core Architecture: Enrich Once, Scan Fast

### The Problem (Old Architecture)
- **Domain validation** + **source discovery** happened during every scan
- Probing domains: 3-10 seconds per city
- Testing URL patterns: 30-50 seconds per city
- **Result**: 50 minutes to scan 57 cities (53 sec/city)

### The Solution (New Architecture)
Two distinct phases:

1. **ENRICHMENT** (Offline, Slow, Runs Once)
   - Validates domains
   - Discovers meeting minutes/procurement sources
   - Stores everything in database
   - Runs as background task

2. **SCANNING** (Live, Fast, User-Triggered)
   - Reads pre-discovered sources from database
   - No probing, no guessing
   - **Result**: <5 seconds per city

---

## Database Schema

### Municipality Table
Tracks core city data and domain enrichment status.

```python
class Municipality(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String(200))                    # "Provo"
    state = Column(String(2), index=True)         # "UT"
    population = Column(Integer, index=True)      # 115162

    # Domain tracking
    domain = Column(String(200))                  # "provo.org" (from original data)
    domain_status = Column(String(20), index=True) # "unverified" | "verified" | "dead"
    domain_verified_at = Column(DateTime)
    resolved_url = Column(String(500))             # "https://www.provo.gov" (after redirects)

    # Relationships
    sources = relationship("MunicipalSource")
```

**Domain Status Flow:**
- `unverified` → Initial state for all cities
- `verified` → Domain works, enrichment complete
- `dead` → Domain doesn't exist or is inaccessible

### MunicipalSource Table
Stores discovered meeting minutes and procurement sources.

```python
class MunicipalSource(Base):
    id = Column(Integer, primary_key=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id"))

    # Source details
    url = Column(String(500), unique=True)         # "https://www.provo.gov/AgendaCenter"
    source_type = Column(String(50), index=True)   # "meeting_minutes" | "procurement"
    platform = Column(String(50))                  # "civicplus" | "granicus" | "html"
    confidence = Column(Float)                     # 0.7 - 1.0

    # Discovery metadata
    discovered_at = Column(DateTime)
    discovered_by_pattern = Column(String(200))    # "/AgendaCenter"

    # Scraping metadata (populated during scans)
    last_scraped_at = Column(DateTime)
    last_scrape_success = Column(Integer)          # 1=success, 0=fail, null=never
    scrape_error = Column(Text)
```

**Benefits:**
- Pre-discovered sources = fast scanning
- Track which URL patterns work per city
- Monitor scraping success/failure rates
- No redundant probing

---

## Enrichment Pipeline

**File**: `src/enrichment.py`

### Step 1: Domain Validation

For each unverified city:

1. Try original domain from database
   ```python
   test_domain("provo.org")  # May redirect to provo.gov
   ```

2. If fails, try alternatives:
   ```python
   alternatives = [
       "cityofprovo.com",
       "cityofprovo.org",
       "proovou.gov",
       "provo.ut.us",
       "ci.provo.ut.us",
       # ... 8 patterns total
   ]
   ```

3. Update municipality:
   ```python
   municipality.domain_status = "verified"  # or "dead"
   municipality.resolved_url = "https://www.provo.gov"
   ```

### Step 2: Source Discovery

For verified cities:

1. Test priority URL patterns (most common first):
   ```python
   priority_patterns = [
       "/AgendaCenter",       # CivicPlus (60%+ of cities)
       "/Archive.aspx",        # CivicPlus archive
       "/DocumentCenter",      # CivicPlus docs
       "/Meetings.aspx",       # Granicus
       "/meetings",
       # ... limited to 8 patterns for speed
   ]
   ```

2. Early stopping:
   - Stop after finding high-confidence source (>= 0.85)
   - Stop after finding any source + 5 pattern checks
   - Saves time, no redundant checks

3. Also check procurement patterns:
   ```python
   procurement_patterns = [
       "/bids",
       "/rfp",
       "/purchasing",
       "/procurement",
       # ... first 5 only
   ]
   ```

4. Store sources in database:
   ```python
   source = MunicipalSource(
       municipality_id=municipality.id,
       url="https://www.provo.gov/AgendaCenter",
       source_type="meeting_minutes",
       platform="civicplus",
       confidence=0.9,
       discovered_by_pattern="/AgendaCenter"
   )
   ```

### Enrichment Scripts

**Run enrichment for specific state:**
```bash
python -c "
from src.enrichment import EnrichmentEngine
engine = EnrichmentEngine()
engine.enrich_state('UT')
"
```

**Run enrichment for Caselle territory (11 states):**
```bash
python scripts/enrich_caselle_territory.py
```

**Stats after enrichment:**
- Utah: 60-70% discovery rate
- CivicPlus AgendaCenter: Dominant platform (~60% of sources)
- Typical: 1-2 sources per city (meeting minutes + procurement)

---

## Scan Pipeline

**File**: `app.py` → `run_scan()`

### Phase 1: Load Sources from Database (NEW)

**Before** (Old Architecture):
```python
for city in cities:
    sources = discovery.discover_municipality(city.name, city.domain)
    # 30-50 seconds per city
```

**After** (New Architecture):
```python
for city in cities:
    municipality = db.query(Municipality).filter_by(id=city.id).first()

    if municipality.domain_status != "verified":
        unenriched_cities.append(city.name)
        continue

    sources = db.query(MunicipalSource).filter_by(
        municipality_id=municipality.id
    ).all()
    # <1 second per city (database query only)
```

**Performance:**
- **Before**: 50 minutes for 57 cities
- **After**: <1 second Phase 1, <5 sec/city total (enriched cities)

### Phase 2: Scraping (Unchanged)
Visits pre-discovered URLs, extracts documents.

### Phase 3: Analysis (Unchanged)
Analyzes documents for procurement signals.

---

## US Expansion Strategy

### Current State
- **6,753 cities** in database (original municipalities.json + sample)
- **Enrichment**: Caselle territory in progress (UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA)
- **Architecture**: Ready for national scale

### Step 1: Census Import

**Script**: `scripts/import_census.py`

```bash
# Download full US Census data
# Source: https://simplemaps.com/data/us-cities (free basic version)
# Place at: data/us_cities_census.csv

python scripts/import_census.py
```

**What it does:**
- Imports ~10,000-12,000 US incorporated places
- Filters to population > 1,000
- Preserves already-enriched cities (no overwrites)
- Sets all new cities to `domain_status='unverified'`

**Expected result:**
```
Total cities in source: 19,494
Above 1,000 population: 10,234
Already in database: 6,753
Newly imported: 3,481
```

### Step 2: Domain Guessing

**Script**: `scripts/guess_domains.py`

```bash
python scripts/guess_domains.py
# Choose: Test 100 cities (quick), 500 cities, or all unverified
```

**What it does:**
- For each unverified city, tests 8 domain patterns
- Stores first working domain
- Updates `domain_status='verified'` or leaves as `'unverified'`

**Expected success rate:** 40-60% (varies by state)

### Step 3: Batch Enrichment

**Priority order:**
1. ✅ Caselle territory (UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA) - in progress
2. Large states: TX, CA, OH, PA, MN, IL, NY, FL
3. Everything else

**Per-state enrichment:**
```bash
python -c "
from src.enrichment import EnrichmentEngine
engine = EnrichmentEngine()
engine.enrich_states(['TX', 'CA', 'OH'])
"
```

**Timeline:**
- 100 cities = ~30 minutes
- 500 cities = ~2.5 hours
- Full US = ~20-30 hours (can run overnight)

### Step 4: Progressive Rollout

**Key insight**: Users can scan **any enriched city** immediately. Don't wait for full enrichment.

**Workflow:**
1. Import Census data (10 minutes)
2. Run domain guessing on 100 cities (5 minutes)
3. Run enrichment on those 100 (30 minutes)
4. **Cities are ready to scan!**
5. Continue enriching more states in background

---

## Performance Characteristics

### Enriched Cities
- **Phase 1 (Load Sources)**: <1 second total (database lookup)
- **Phase 2 (Scraping)**: 2-3 seconds per city
- **Phase 3 (Analysis)**: 1-2 seconds per city
- **Total**: ~5 seconds per city
- **200 cities**: ~15 minutes

### Unenriched Cities
- Falls back to old discovery method
- **Phase 1 (Discovery)**: 30-50 seconds per city
- Scan still works, just slower
- Warning shown: "X cities not enriched yet"

### 200-City Scan Limit
**Why:**
- With 10,000+ cities, "All Cities" could match thousands
- Prevents accidental hour-long scans
- 200 cities × 5 sec = ~15 minutes maximum

**How to scan more:**
- Scan state-by-state
- Use population tiers
- Use search filters

---

## File Structure

```
municipal-intel/
├── src/
│   ├── database.py         # SQLAlchemy models (Municipality, MunicipalSource)
│   ├── enrichment.py       # Offline enrichment pipeline
│   ├── discovery.py        # URL pattern testing (used by enrichment)
│   ├── scraper.py          # Document scraping
│   ├── analyzer.py         # Signal detection
│   ├── signals.py          # Signal definitions
│   └── reporter.py         # Report generation
├── scripts/
│   ├── migrate_municipalities.py   # Initial DB population
│   ├── import_census.py            # Import Census data
│   ├── guess_domains.py            # Algorithmic domain guessing
│   ├── enrich_caselle_territory.py # Enrich 11 Caselle states
│   ├── test_enrichment.py          # Test enrichment on sample
│   └── test_mn_discovery.py        # Diagnostic script
├── data/
│   ├── municipalities.json         # Original 6,752 cities
│   ├── municipal_intel.db          # SQLite database (NEW)
│   └── us_cities_census.csv        # Full Census data (download)
├── app.py                  # Main Streamlit UI
└── README.md              # User documentation
```

---

## Key Design Decisions

### Why SQLite?
- **Simple**: Single file, no server
- **Fast**: Local queries < 1ms
- **Portable**: Copy `municipal_intel.db` = copy everything
- **Sufficient**: Handles 10,000 cities + 20,000 sources easily

### Why Separate Enrichment from Scanning?
- **Speed**: Scanning reads from DB instead of probing
- **Scalability**: Enrich once, scan forever
- **Progressive**: Can enrich in waves while users scan ready cities
- **Reliability**: Enrichment failures don't block scanning

### Why 8 URL Patterns Max?
- **Diminishing returns**: First 8 patterns cover 90% of cities
- **Respect**: Don't hammer municipal servers
- **Speed**: 8 patterns × 1s delay = ~10 seconds
- **Early stopping**: Often finds source in 1-3 patterns

### Why CivicPlus Focus?
- **Market dominance**: 60%+ of cities use CivicPlus
- **AgendaCenter**: Standardized URL pattern (`/AgendaCenter`)
- **High confidence**: CivicPlus sources score 0.9 confidence
- **Fast discovery**: Usually found in first pattern check

---

## Common Operations

### Check Database Stats
```bash
python -c "
from src.database import SessionLocal, Municipality, MunicipalSource

db = SessionLocal()
total = db.query(Municipality).count()
verified = db.query(Municipality).filter_by(domain_status='verified').count()
sources = db.query(MunicipalSource).count()

print(f'Total cities: {total:,}')
print(f'Verified: {verified:,} ({verified/total*100:.1f}%)')
print(f'Sources: {sources:,}')
db.close()
"
```

### Enrich Specific Cities
```python
from src.database import SessionLocal, Municipality
from src.enrichment import EnrichmentEngine

db = SessionLocal()
engine = EnrichmentEngine()

# Get specific city
city = db.query(Municipality).filter_by(name="Provo", state="UT").first()

# Enrich it
engine.enrich_municipality(city, db)

db.close()
```

### Reset Enrichment for Testing
```python
from src.database import SessionLocal, Municipality, MunicipalSource

db = SessionLocal()

# Delete all sources
db.query(MunicipalSource).delete()

# Reset all municipalities to unverified
db.query(Municipality).update({
    "domain_status": "unverified",
    "domain_verified_at": None,
    "resolved_url": None
})

db.commit()
db.close()
```

---

## Admin Dashboard

**File**: `pages/admin.py`

A comprehensive admin UI for managing enrichment and monitoring database coverage.

### Features

**Tab 1: Overview**
- Database statistics dashboard
  - Total cities, verified/unverified/dead counts
  - Enrichment progress bar with percentage
- Source discovery breakdown
  - By type: meeting_minutes vs procurement
  - By platform: CivicPlus, Granicus, HTML, etc.
- Visual charts for quick insights

**Tab 2: States**
- State-by-state enrichment table
- Columns: Total cities, verified, unverified, dead, enrichment %, sources
- Color-coded enrichment percentage:
  - Green: >= 70% enriched
  - Yellow: 40-69% enriched
  - Red: < 40% enriched
- Filter by minimum enrichment threshold
- CSV export of state statistics

**Tab 3: Run Enrichment**
Three enrichment modes:
1. **Single State**: Select one state from dropdown
2. **Multiple States**: Checkbox grid to select multiple
3. **All Unverified**: Enrich all states at once

For each mode:
- Shows unverified count per state
- Enrichment summary: Target states, cities, estimated time
- Warning for large batches (> 500 cities)
- One-click enrichment with progress display
- Success metrics: Cities processed, domains verified, sources discovered
- Auto-refresh statistics after completion

### Access

Navigate to the **Admin** page via the Streamlit sidebar. The admin page automatically appears when the app runs (no separate deployment needed).

### Usage Example

```bash
# Start app (admin page auto-available)
streamlit run app.py

# Navigate to Admin in sidebar
# Tab 3: Select state (e.g., "ID - 20 unverified of 35")
# Click "Start Enrichment"
# Wait for completion, view stats
```

---

## Future Enhancements

### Scheduled Enrichment
- Cron job to enrich new cities nightly
- Re-verify dead domains monthly
- Update source availability

### Multi-Database Support
- PostgreSQL for larger deployments
- Redis for caching
- ElasticSearch for full-text search

### Advanced Discovery
- Google search fallback for cities with no working domain
- Third-party APIs (OpenCorporates, etc.)
- Machine learning for URL pattern prediction

---

## Troubleshooting

### "No sources found" for verified city
**Cause**: Domain works but uses non-standard URL structure

**Solution:**
1. Manually visit city website
2. Find meeting minutes page
3. Add source manually:
   ```python
   from src.database import SessionLocal, Municipality, MunicipalSource

   db = SessionLocal()
   city = db.query(Municipality).filter_by(name="CityName", state="ST").first()

   source = MunicipalSource(
       municipality_id=city.id,
       url="https://example.gov/custom/path",
       source_type="meeting_minutes",
       platform="html",
       confidence=0.8
   )
   db.add(source)
   db.commit()
   db.close()
   ```

### "X cities not enriched yet" warning
**Cause**: Cities haven't been through enrichment pipeline

**Solution**:
1. Run enrichment for those cities
2. Or filter to only scan enriched cities
3. Or accept slower scan (falls back to discovery)

### Database locked error
**Cause**: Multiple processes accessing SQLite simultaneously

**Solution**:
- Don't run enrichment + scan at same time
- Or upgrade to PostgreSQL for concurrent access

---

## Performance Benchmarks

### Enrichment
- **Utah (96 cities)**:
  - Time: ~45 minutes
  - Success: 60-70% discovery rate
  - Sources: 60+ meeting minutes, 30+ procurement

### Scanning (Enriched Cities)
- **5 Utah cities**: 25 seconds (5 sec/city)
- **57 Minnesota cities** (projected): <5 minutes
- **200 cities** (max): ~15 minutes

### Scanning (Unenriched Cities)
- **57 Minnesota cities**: 50 minutes (old architecture)
- **Reason**: Domain discovery + URL probing per city

**Recommendation**: Always enrich before scanning for best performance.

---

## Summary

The new database-driven architecture transforms Municipal Intel from a slow, probing-based system into a fast, scalable platform. By separating enrichment (offline, slow, once) from scanning (live, fast, always), we achieve:

- **10x faster scanning** for enriched cities
- **Scalability** to cover all 10,000+ US cities
- **Progressive rollout** - enrich in waves, scan immediately
- **Reliability** - pre-discovered sources, no guessing

The system is **production-ready** for national scale.
