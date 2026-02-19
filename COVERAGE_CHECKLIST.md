# Municipal Intel — Coverage Checklist
**Last Updated**: Feb 19, 2026
**Current Status**: 1,463 sources across 49 states

---

## ✅ What We're Covering

### 1. Meeting Minutes (833 sources, 56.9%)
**Status**: ✅ EXCELLENT

**URL Patterns Checked** (~40 patterns):
- CivicPlus: /AgendaCenter, /Archive.aspx, /DocumentCenter
- Granicus: /Meetings.aspx, /Calendar.aspx, /ViewPublishedAgendas.ashx
- BoardDocs: /boarddocs, /meetings/Board
- Generic: /meetings, /agendas, /minutes, /city-council, /council-meetings

**Platform Detection**:
- CivicPlus (54.8%)
- Granicus (0.4%)
- BoardDocs
- HTML fallback (35%)

**Alternative Domain Discovery**:
- Tries 8+ alternative domain patterns when provided domain fails
- Examples: cityof{name}.com, cityof{name}.org, {name}{state}.gov

**Third-Party Platforms Checked**:
- {city}.civicweb.net
- {city}.legistar.com
- {city}.granicus.com
- {city}-{state}.municode.com

---

### 2. Procurement Documents (425 sources, 29.0%)
**Status**: ✅ GOOD

**URL Patterns Checked** (14 patterns):
- /bids, /rfps, /rfp, /purchasing, /procurement
- /bid-opportunities, /requests-for-proposals, /open-bids, /current-bids
- /solicitations, /vendor-opportunities
- /departments/purchasing, /departments/procurement
- /finance/purchasing, /finance/bids, /government/purchasing

**Content Validation**:
- Requires 2+ indicators: "bid", "rfp", "request for proposal", "procurement", "solicitation", "vendor", "purchasing", "opportunity"

---

### 3. State Portals (133 sources, 9.5%)
**Status**: ✅ EXCELLENT (Utah-specific)

**Current Coverage**:
- Utah Public Meeting Notice (PMN) portal: 133 sources (75% of Utah coverage)
- Provides centralized meeting data for Utah municipalities

**Expansion Opportunity**:
- Colorado: dlg.colorado.gov (Department of Local Affairs)
- Idaho: notice.nv.gov, townhall.idaho.gov
- Other states may have similar centralized portals

---

## ⚠️ Coverage Gaps

### 1. Budget Documents (72 sources, 4.9%) — **IMPROVED**
**Status**: ⚠️ NEEDS EXPANSION

**Current State**:
- 72 budget sources total (+112% increase from 34)
- 27 in Colorado (24.3% of CO sources)
- 20 in California (21.5% of CA sources)
- Others: Alabama (6), Arizona (8), Arkansas (3), Alaska (1)
- ✅ Systematic budget URL patterns now defined in src/signals.py

**Budget URL Patterns Implemented** (27 patterns):
- ✅ /budget, /annual-budget, /adopted-budget, /proposed-budget
- ✅ /finance/budget, /departments/finance/budget, /finance
- ✅ /financial-reports, /financial-statements, /audited-financials
- ✅ /cafr, /comprehensive-annual-financial-report, /acfr
- ✅ /transparency, /financial-transparency, /open-books, /checkbook
- ✅ /government/budget, /government/finance, /business/budget

**Completed Actions**:
1. ✅ Added BUDGET_PATTERNS to src/signals.py (Feb 19)
2. ✅ Updated discover_procurement_sources.py to include budget discovery
3. ✅ Ran nationwide budget+procurement discovery
4. ⏳ Ongoing: State enrichments will auto-discover budget sources

**Remaining Actions**:
1. Continue nationwide budget discovery as enrichments complete
2. Target states with 0% budget coverage (TX, IL, MN, FL, OH, WA, MI)

---

### 2. Large States with Low Coverage
**Status**: ⚠️ NEEDS IMPROVEMENT

**States Under 10% Coverage**:
- **California**: 58/660 municipalities (8.8%) — 602 missing
- **Pennsylvania**: 4/270 municipalities (1.5%) — 266 missing
- **New Jersey**: 13/285 municipalities (4.6%) — 272 missing
- **Maryland**: 13/204 municipalities (6.4%) — 191 missing
- **Virginia**: 13/199 municipalities (6.5%) — 186 missing
- **Louisiana**: 8/108 municipalities (7.4%) — 100 missing

**Root Causes**:
- Domain failures (47.2% of municipalities marked "dead")
- Non-standard website platforms
- ✅ Pattern limit now adaptive: 8 (small), 12 (medium), 16 (large cities)

**Recommended Actions**:
1. ✅ Adaptive URL pattern limit implemented (8/12/16 by city size)
2. ✅ Third-party platforms expanded (10 platforms: BoardDocs, NovusAgenda, PrimeGov, OpenGov)
3. ⏳ Manual review of high-population municipalities in underperforming states
4. ⏳ Alternative data sources (state transparency portals attempted, limited success)

---

### 3. States with No Sources Yet
**Status**: ⏳ IN PROGRESS

**Current List**:
- Hawaii (57 municipalities) — enrichment running
- DC (1 municipality) — enrichment running
- Puerto Rico (51 municipalities) — enrichment running

**Action**: Wait for enrichments to complete (auto-appear via 30sec UI refresh)

---

## 📊 Coverage by Source Type (Top 10 States)

| State | Meeting Minutes | Procurement | Budget | State Portal |
|-------|----------------|-------------|--------|--------------|
| UT    | 16.4%          | 8.5%        | 0%     | **75.1%**    |
| TX    | 70.2%          | 29.8%       | 0%     | 0%           |
| CO    | 44.1%          | 31.5%       | **24.3%** | 0%        |
| IL    | 66.1%          | 33.9%       | 0%     | 0%           |
| CA    | 62.1%          | 37.9%       | 0%     | 0%           |
| MN    | 80.7%          | 19.3%       | 0%     | 0%           |
| OH    | 69.1%          | 30.9%       | 0%     | 0%           |
| FL    | 67.3%          | 32.7%       | 0%     | 0%           |
| WA    | 60.9%          | 39.1%       | 0%     | 0%           |
| MI    | 72.7%          | 27.3%       | 0%     | 0%           |

**Key Insight**: Only Colorado has systematic budget coverage. All other states 0%.

---

## 🎯 Priority Recommendations

### Immediate (Next 7 Days)
1. ✅ **Run coverage analysis** (DONE - Feb 19)
2. ✅ **Add BUDGET_PATTERNS** to src/signals.py (DONE - Feb 19)
3. ✅ **Implement adaptive pattern limits** (DONE - Feb 19)
4. ⏳ **Verify enrichment completion** for HI, DC, PR (in progress)

### Short-Term (Next 30 Days)
1. **Expand URL patterns** for underperforming states (CA, PA, NJ, MD, VA)
2. **Increase pattern check limit** from 8 to 12 for municipalities >25K population
3. **Add state transparency portals** (CO, ID already done — expand to others)
4. **Manual high-value municipality review** (100 largest cities without sources)

### Long-Term (Next 90 Days)
1. **Platform-specific scrapers** for Municode, Novus Agenda, SiteSpect
2. **FOIA automation** for municipalities with dead domains but active governments
3. **Historical data backfill** (meeting minutes archives 2020-present)
4. **Real-time monitoring** (daily checks for new documents on discovered sources)

---

## 📈 Coverage Metrics

**Overall**:
- 1,463 sources across 1,074 municipalities (15.9% coverage)
- 49 states active, 3 enriching (HI, DC, PR)
- 7 platforms detected
- 189 municipalities still "unverified" (enrichments in progress)

**Domain Status**:
- 50.0% verified (3,376 municipalities)
- 47.2% dead (3,188 municipalities)
- 2.8% unverified (189 municipalities — enrichments running)

**Quality Indicators**:
- ✅ Platform diversity: 7 distinct platforms
- ✅ Source type balance: 57% minutes, 29% procurement
- ⚠️ Budget coverage: 4.9% (improving, target 10-15%)
- ⚠️ Large state coverage: CA (14.1%), PA (1.5%), NJ (4.6%) still low

---

## 🔧 Technical Considerations

### Current Limits
- **Adaptive URL pattern checking** (Feb 19):
  - Small cities (<10K): 8 patterns
  - Medium cities (10K-50K): 12 patterns (+50%)
  - Large cities (>50K): 16 patterns (+100%)
- **1sec delay between requests** (respectful crawling)
- **10sec timeout** per request
- **Early stopping**: Stops after high-confidence match (confidence ≥0.85)

### Implemented Optimizations
1. ✅ **Adaptive pattern checking**: 8/12/16 patterns by population (Feb 19)
2. ✅ **Early stopping**: Stops after confidence ≥0.85 match
3. ⏳ **Parallel domain verification**: Considered for future
4. ⏳ **Cached negative results**: Considered for future
5. ⏳ **Smart pattern ordering**: Priority patterns identified (CivicPlus first)

---

## ✅ Bottom Line

**What We're Doing Right**:
- Excellent meeting minutes coverage (58.6%)
- Strong procurement coverage (29.5%)
- Good platform diversity (7 platforms)
- Nationwide expansion complete (49 states)

**Critical Gaps to Address**:
1. ✅ **Budget documents**: Now at 4.9% coverage (+112% improvement)
2. **Large state coverage**: PA (1.5%), NJ (4.6%), VA (6.5%), MD (6.4%) still very low
3. ✅ **Pattern limits**: Now adaptive (8/12/16 by city size)

**Immediate Next Steps**:
1. ✅ Budget URL patterns added and nationwide discovery run
2. ⏳ Monitor HI, DC, PR enrichments (189 municipalities still enriching)
3. ⏳ Focus on Pennsylvania (1.5%) and New Jersey (4.6%) - critical gaps
4. ✅ Adaptive pattern limit implemented (8/12/16 by size)
