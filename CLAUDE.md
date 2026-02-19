# Municipal Intel — Claude Code Context

## Project Overview

Sales intelligence platform for Caselle Inc. Scrapes municipal meeting minutes,
procurement postings, and budget documents across **all 50 US states + DC + Puerto Rico**
to surface government ERP buying signals.

## Architecture

- **Backend**: FastAPI on Railway (`web-production-a13f5.up.railway.app`)
- **Database**: Postgres on Neon (shared by FastAPI app and scan scripts)
- **Frontend**: Server-rendered Jinja2 templates (no separate frontend build)
- **Email**: Resend for magic link auth
- **Scraping**: aiohttp + BeautifulSoup + pdfplumber, runs locally or in background

## Current State (Feb 19, 2026)

### What Works
- FastAPI backend on Railway (web-production-a13f5.up.railway.app)
- Auth: magic link login via Resend, role-based routing (client/consultant/admin)
- Landing page at / with waitlist form writing to database
- Dashboard at /dashboard (client view: assessment, reports, consultation cards)
- Scanner at /scanner (consultant/admin view: **dynamic state selector showing all covered states, auto-refreshing**, tier filter, scan preview card)
- Admin at /admin (waitlist management, user role assignment)
- Background scan processing with progress polling
- Database: Postgres on Neon (shared by FastAPI app)
- **1,376+ municipal sources across 49 states + DC + Puerto Rico**
- Top 10 states by coverage: UT (177), TX (111), CO (111), IL (58), MN (57), CA (52), FL (50), OH (49), WA (46), MI (44)
- Scanner UI features live state counter and 30-second auto-refresh for real-time coverage tracking

### First Production Scan Results (Feb 18, 2026)
- Small tier (2.5K–10K): 24 min, 61 sources, 241 docs, 2 HOT + 1 WARM
- Small-Mid tier (10K–25K): 33 min, 69 sources, 290 docs, 1 HOT + 1 WARM
- Real finds: Torrington WY ($2,652 Caselle maintenance), Evanston WY ($4,450 Caselle support)
- False positives fixed: Rawlins WY (agenda deadline), Douglas WY (street sweeper procurement)
- Hit rate: ~0.6% — coverage is the bottleneck, not the analysis engine

### CO + ID Verification Scan (Feb 18, 2026)
After discovering 111 CO sources and 42 ID sources, ran verification scan to confirm sources work:
- **Small tier (2.5K–10K)**: 59 cities, 30 min, 65 docs scraped, 0 leads
- **Small-Mid tier (10K–25K)**: 43 cities, 63 min, 73 docs scraped, 0 leads
- **Total**: 102 cities, 93 min, 138 docs scraped, 0 leads
- ✅ **Result**: Sources operational, session-cycling fix prevents SSL timeouts
- The 0 leads is expected (rare signal hit rate ~0.6%), verification goal was to confirm sources scrape docs

### Signal Precision (commit 66814bc)
- `budget_signals` now requires `requires_context: True` — validated against tech terms within ±50 words
- Removed bare `rfp`/`rfi`/`rfq` keywords (too broad, fired on equipment/vehicle RFPs)
- Removed `capital improvement` (fired on property/infrastructure fund transfers)
- Added `PHYSICAL_PROCUREMENT_TERMS` negative filter in analyzer.py (street sweeper, mower, etc.)
- Added `TECH_CONTEXT_TERMS` positive requirement in analyzer.py (software, erp, system, etc.)
- `active_rfp_signals` no longer uses circular self-validation via "rfp" as a supporting term

### Nationwide Expansion (Feb 18-19, 2026)
- ✅ **Scope**: Expanded from 7 Caselle states to nationwide coverage (50 states + DC + Puerto Rico)
- ✅ **Scale**: Grew from 367 sources to 1,376+ sources (3.75x increase)
- ✅ **Coverage**: 49 jurisdictions with active sources (Hawaii still enriching)
- ✅ **Implementation**:
  - Created 45 state-specific enrichment scripts using EnrichmentEngine
  - Parallelized enrichment across all states (I/O-bound, 1sec request delays)
  - Fixed KeyError bug in results reporting (verified vs domains_verified)
- ✅ **UI Enhancements**:
  - Dynamic state selector populates automatically via /api/states endpoint
  - 30-second auto-refresh preserves user selections while showing new states
  - Live state/source counter: "(49 states, 1,376 sources)"
- ✅ **Top Coverage**: UT (177), TX (111), CO (111), IL (58), MN (57), CA (52), FL (50), OH (49), WA (46), MI (44)

### Known Issues
1. ~~Source coverage thin outside Utah~~ → ✅ Fixed: Nationwide coverage with 1,376+ sources across 49 jurisdictions
2. ~~Neon SSL idle timeout during scans~~ → ✅ Fixed: Session-cycling pattern (scripts/verify_scan.py:98-106)
3. Smaller/rural states rely primarily on meeting_minutes sources (limited procurement/budget page standardization)
4. Hawaii enrichment still in progress (will auto-appear when complete via 30sec UI refresh)
5. Landing page hero may need breakpoint check on some viewports

### Customer Status Categorization (Feb 18, 2026)
✅ **Implemented automatic customer status detection for leads:**
- Leads are categorized as "existing_customer" or "new_opportunity" based on signal analysis
- Detection logic: If "direct_mentions" signal is present (Caselle/Clarity mentioned) → "existing_customer"
- Otherwise → "new_opportunity" (municipality shopping for ERP, no current Caselle affiliation)
- Field added to Lead model (src/database.py:214) with index for efficient filtering
- Detection implemented in DocumentAnalyzer (src/analyzer.py:264-265)
- Tests confirm 100% accuracy: Caselle mentions → existing_customer, all others → new_opportunity
- **Sales Impact**: Enables prioritization of existing customer retention/upsell vs new acquisition

### Priority Next Steps
1. ~~Add lead categorization: "EXISTING CUSTOMER" vs "NEW OPPORTUNITY"~~ → ✅ Completed (Feb 18)
2. ~~Build state portal scrapers for Colorado and Idaho~~ → ✅ Completed via direct discovery (Feb 18)
3. ~~Enrich CO, ID with procurement/budget sources~~ → ✅ Completed (Feb 19: 80 new sources)
4. ~~Expand to nationwide coverage~~ → ✅ Completed (Feb 19: 49 states, 1,376+ sources, 3.75x growth)
5. Point govtechdiagnostic.com domain to Railway
6. Wire landing page email form to Resend for notifications
7. Run verification scans on newly enriched states to confirm sources operational

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app entry point, all routes |
| `src/signals.py` | 138+ keywords, weights, lead classification rules |
| `src/enrichment.py` | Domain validation, source discovery |
| `src/scraper.py` | HTML/PDF scraping, Utah portal support |
| `src/analyzer.py` | Keyword matching, scoring, lead classification |
| `src/discovery.py` | URL pattern probing |
| `src/database.py` | SQLAlchemy models |
| `scripts/discover_sources.py` | Targeted source discovery for Caselle states |
| `scripts/run_caselle_scan.py` | Production scan runner |
| `templates/landing.html` | Public landing page |
| `data/utah_portal_entities.json` | Utah state portal entity data |

## Database Tables

| Table | Key columns |
|-------|-------------|
| `users` | id, email, role, created_at |
| `waitlist` | id, email, created_at |
| `municipalities` | id, name, state, population, domain, domain_status, resolved_url |
| `municipal_sources` | id, municipality_id, url, source_type, platform, confidence |
| `scans` | id, user_id, status, config_json, progress_phase, progress_pct, stats_json |
| `leads` | id, scan_id, municipality, state, lead_type, customer_status, relevance_score, signal_matches_json |

## Environment Variables (Railway)

```
DATABASE_URL        postgresql://neondb_owner:...@neon.tech/neondb
JWT_SECRET_KEY      ...
RESEND_API_KEY      re_...
RESEND_FROM_EMAIL   Municipal Intel <noreply@govtechdiagnostic.com>
APP_URL             https://govtechdiagnostic.com
ANTHROPIC_API_KEY   sk-ant-...  (optional, for LLM-enhanced analysis)
```

## Git

Main branch. Push before closing session:
```bash
git push origin main
```
