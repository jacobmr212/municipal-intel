# Municipal Intel — Claude Code Context

## Project Overview

Sales intelligence platform for Caselle Inc. Scrapes municipal meeting minutes,
procurement postings, and budget documents across 7 western states (UT, CO, ID,
WY, MT, NV, NM) to surface government ERP buying signals.

## Architecture

- **Backend**: FastAPI on Railway (`web-production-a13f5.up.railway.app`)
- **Database**: Postgres on Neon (shared by FastAPI app and scan scripts)
- **Frontend**: Server-rendered Jinja2 templates (no separate frontend build)
- **Email**: Resend for magic link auth
- **Scraping**: aiohttp + BeautifulSoup + pdfplumber, runs locally or in background

## Current State (Feb 18, 2026)

### What Works
- FastAPI backend on Railway (web-production-a13f5.up.railway.app)
- Auth: magic link login via Resend, role-based routing (client/consultant/admin)
- Landing page at / with waitlist form writing to database
- Dashboard at /dashboard (client view: assessment, reports, consultation cards)
- Scanner at /scanner (consultant/admin view: state selector, tier filter, scan preview card)
- Admin at /admin (waitlist management, user role assignment)
- Background scan processing with progress polling
- Database: Postgres on Neon (shared by FastAPI app)
- **306 municipal sources across 7 states** (UT, CO, ID, WY, MT, NV, NM)
- Utah: 177 sources (133 portal + 44 direct)
- **Colorado: 111 sources** (49 meeting_minutes, 35 procurement, 27 budget)
- **Idaho: 42 sources** (22 meeting_minutes, 14 procurement, 6 budget)
- WY, MT, NV, NM: 18 sources via CivicPlus/pattern discovery

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

### Known Issues
1. ~~Source coverage thin outside Utah~~ → ✅ Fixed: CO now has 111 sources, ID has 42 sources (Feb 18)
2. ~~Neon SSL idle timeout during scans~~ → ✅ Fixed: Session-cycling pattern in verify_scan.py (scripts/verify_scan.py:98-106)
3. ND, SD, OR, WA not yet enriched (0 sources)
4. Landing page hero may need breakpoint check on some viewports

### Priority Next Steps
1. Add lead categorization: "EXISTING CUSTOMER" vs "NEW OPPORTUNITY"
2. ~~Build state portal scrapers for Colorado and Idaho~~ → Completed via direct discovery (Feb 18)
3. Enrich ND, SD, OR, WA (state portals or direct discovery)
4. Point govtechdiagnostic.com domain to Railway
5. Wire landing page email form to Resend for notifications

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
| `intel_scans` | id, user_id, status, config_json, progress_phase, progress_pct, stats_json |
| `intel_leads` | id, scan_id, municipality, state, lead_type, relevance_score, signal_matches_json |

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
