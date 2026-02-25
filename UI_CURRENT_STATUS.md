# UI Current Status & Priority 1 Roadmap

**Assessment Date**: February 25, 2026

---

## ✅ What Exists Now (scanner.html)

### Current UI Structure
```
├── Top Navigation
│   ├── Logo
│   ├── "Scanner" badge
│   ├── User email
│   ├── User role badge
│   └── Logout link
│
├── Tab Navigation
│   ├── Feed (active by default)
│   ├── Scanner
│   ├── Watchlist
│   └── Territories
│
├── Feed Tab ✅ (Basic, needs enhancement)
│   ├── Type filter (all/hot/warm)
│   ├── Days filter (7/30/90 days)
│   ├── Refresh button
│   └── Lead cards showing:
│       ├── Lead type badge (HOT/WARM/COOL)
│       ├── Customer status (existing/new)
│       ├── Municipality, State
│       ├── Title
│       ├── Signals (first 3)
│       ├── Relevance score
│       └── "View" button (opens doc URL)
│
├── Scanner Tab ✅ (Functional)
│   ├── State selector (dynamic, all 52 jurisdictions)
│   ├── Population tier selector
│   ├── Scan preview card
│   └── "Start Scan" button
│
├── Watchlist Tab ✅ (Functional)
│   └── Add/remove municipalities
│
└── Territories Tab ✅ (Functional)
    └── Assign states to user
```

---

## ⚠️ What's MISSING (Enterprise Features)

### 1. Lead Cards - Missing Enterprise Data

**Current lead card shows:**
- Lead type, customer status, date
- Municipality, title
- First 3 signals
- Relevance score
- View button

**MISSING (all APIs ready!):**
- ❌ **Urgency score** & urgency badge (e.g., "CRITICAL - 15 days")
- ❌ **Deadline date** (e.g., "Due: Mar 15, 2026")
- ❌ **Decision stage** (exploration/evaluation/procurement/implementation)
- ❌ **Competitors mentioned** (e.g., "Tyler, Oracle detected")
- ❌ **Existing vendor** (e.g., "Currently using: Tyler")
- ❌ **Entity info** (e.g., "School District" badge if from entity)
- ❌ **Lead status** (new/contacted/qualified/won/lost)
- ❌ **Deal value** (if assigned)

### 2. Advanced Filters - Missing UI

**Current filters:**
- ✅ Lead type (all/hot/warm)
- ✅ Days (7/30/90)

**MISSING (25+ filter APIs ready!):**
- ❌ **Urgency range** (slider: 0-100)
- ❌ **Deadline range** (date picker: within X days)
- ❌ **Decision stage** (dropdown)
- ❌ **Competitor filter** (multi-select: Tyler, Oracle, SAP, etc.)
- ❌ **Existing vendor filter**
- ❌ **Population range** (for targeting small towns!)
- ❌ **State filter** (multi-select)
- ❌ **Source type** (meeting_minutes, procurement, budget)
- ❌ **Customer status** (existing/new)
- ❌ **Lead status** (pipeline stage)
- ❌ **Has competitors** (yes/no toggle)
- ❌ **Entity type** (school_district, fire_district, etc.)

### 3. Lead Detail Modal - Completely Missing

**When user clicks on a lead, should show 8-section modal:**

❌ **Not built yet** - But API endpoint exists! (`GET /api/leads/{id}/details`)

**8 Sections the API returns:**
1. **Overview** - Basic lead info, status, scores
2. **Signal Analysis** - All detected signals with context
3. **Temporal Intelligence** - Urgency, deadline, decision stage, fiscal year
4. **Competitive Analysis** - Competitors, existing vendor, displacement opportunities
5. **ROI Tracking** - Pipeline status, deal value, dates
6. **Timeline** - Chronological activity
7. **Municipality Context** - Population, domain, verified date
8. **Related Leads** - Other leads from same municipality

### 4. Analytics Dashboard - Completely Missing

❌ **Not built yet** - But API endpoint exists! (`GET /api/analytics/dashboard`)

**Should show (with Chart.js):**
- Overview stats (total leads, hot/warm/cool, avg score)
- Lead type distribution (pie chart)
- Source type distribution (pie chart)
- Urgency levels (bar chart)
- Competitors breakdown (bar chart)
- Time series (line chart - leads per day)
- Pipeline funnel (if ROI tracking enabled)
- Revenue metrics (if deal values tracked)

### 5. CRM Configuration Page - Completely Missing

❌ **Not built yet** - But API endpoints exist!

**Needs:**
- Form to configure Salesforce (username, password, token, domain)
- Form to configure HubSpot (access token, portal ID)
- List of configured CRMs with enable/disable toggle
- Field mapping interface (optional)
- Auto-sync preferences (hot leads, warm leads)
- Sync status dashboard

### 6. Entity View - Completely Missing

❌ **Not built yet** - Database has entities, but no UI to show them

**Should show:**
- Entity badges on lead cards (e.g., "School District" icon)
- Entity count per municipality
- Filter leads by entity type
- Entity discovery status

---

## 🎯 Priority 1: Critical UI Enhancements

**Goal**: Make enterprise features visible and usable
**Timeline**: 1-2 weeks
**Impact**: 10x better user experience, justify $300-500/mo pricing

### Week 1: Enhanced Feed & Filters

**Day 1-2: Enhanced Lead Cards**
```javascript
// Add to createLeadCard() function:

// 1. Urgency badge
if (lead.urgency_score >= 80) {
    urgencyHTML = '<span class="px-2 py-1 text-xs font-bold text-red-800 bg-red-100 rounded-full animate-pulse">
        CRITICAL - ' + lead.days_until_deadline + ' days
    </span>';
} else if (lead.urgency_score >= 60) {
    urgencyHTML = '<span class="px-2 py-1 text-xs font-semibold text-orange-800 bg-orange-100 rounded-full">
        URGENT - ' + lead.days_until_deadline + ' days
    </span>';
}

// 2. Deadline date
if (lead.deadline_date) {
    deadlineHTML = '<div class="text-xs text-gray-600">
        ⏰ Due: ' + new Date(lead.deadline_date).toLocaleDateString() + '
    </div>';
}

// 3. Competitors
if (lead.competitors_mentioned && lead.competitors_mentioned.length > 0) {
    competitorsHTML = '<div class="text-xs text-gray-600">
        ⚔️ Competing: ' + lead.competitors_mentioned.slice(0, 2).join(', ') + '
    </div>';
}

// 4. Decision stage
if (lead.decision_stage) {
    stageHTML = '<span class="text-xs text-gray-500">
        📊 ' + lead.decision_stage.replace('_', ' ') + '
    </span>';
}

// 5. Click handler for detail modal
card.onclick = () => openLeadDetailModal(lead.id);
card.style.cursor = 'pointer';
```

**Day 3-4: Advanced Filters UI**
```html
<!-- Add to feed section -->
<div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
    <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-gray-700">Advanced Filters</h3>
        <button onclick="toggleFilters()" class="text-sm text-blue-600">
            <span id="filter-toggle-text">Show</span>
        </button>
    </div>

    <div id="advanced-filters" class="hidden grid grid-cols-3 gap-4">
        <!-- Urgency slider -->
        <div>
            <label class="text-xs text-gray-600">Min Urgency</label>
            <input type="range" id="min-urgency" min="0" max="100" value="0"
                   class="w-full" onchange="loadFeed()">
            <span id="min-urgency-value" class="text-xs text-gray-500">0</span>
        </div>

        <!-- Deadline filter -->
        <div>
            <label class="text-xs text-gray-600">Deadline Within</label>
            <select id="deadline-filter" class="text-sm w-full" onchange="loadFeed()">
                <option value="">Any time</option>
                <option value="7">7 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
            </select>
        </div>

        <!-- Decision stage -->
        <div>
            <label class="text-xs text-gray-600">Decision Stage</label>
            <select id="decision-stage-filter" class="text-sm w-full" onchange="loadFeed()">
                <option value="">All stages</option>
                <option value="exploration">Exploration</option>
                <option value="evaluation">Evaluation</option>
                <option value="procurement">Procurement</option>
                <option value="implementation">Implementation</option>
            </select>
        </div>

        <!-- Competitor filter -->
        <div>
            <label class="text-xs text-gray-600">Competitor</label>
            <select id="competitor-filter" class="text-sm w-full" onchange="loadFeed()">
                <option value="">Any</option>
                <option value="tyler">Tyler</option>
                <option value="oracle">Oracle</option>
                <option value="sap">SAP</option>
                <!-- ... more competitors -->
            </select>
        </div>

        <!-- Population range -->
        <div>
            <label class="text-xs text-gray-600">Population</label>
            <select id="population-filter" class="text-sm w-full" onchange="loadFeed()">
                <option value="">All sizes</option>
                <option value="2500-10000">Small towns (2.5K-10K)</option>
                <option value="10000-25000">Small-mid (10K-25K)</option>
                <option value="25000-50000">Mid-market (25K-50K)</option>
                <option value="50000-100000">Upper-mid (50K-100K)</option>
                <option value="100000+">Large (100K+)</option>
            </select>
        </div>

        <!-- Entity type -->
        <div>
            <label class="text-xs text-gray-600">Entity Type</label>
            <select id="entity-type-filter" class="text-sm w-full" onchange="loadFeed()">
                <option value="">All entities</option>
                <option value="municipality">City/Town</option>
                <option value="school_district">School District</option>
                <option value="fire_district">Fire District</option>
                <option value="library">Library</option>
                <option value="water_district">Water District</option>
            </select>
        </div>
    </div>
</div>
```

**Day 5: Update loadFeed() to use all filters**
```javascript
async function loadFeed() {
    // Existing filters
    const typeFilter = document.getElementById('feed-type-filter').value;
    const daysFilter = document.getElementById('feed-days-filter').value;

    // NEW: Advanced filters
    const minUrgency = document.getElementById('min-urgency')?.value || 0;
    const deadlineFilter = document.getElementById('deadline-filter')?.value || '';
    const decisionStage = document.getElementById('decision-stage-filter')?.value || '';
    const competitor = document.getElementById('competitor-filter')?.value || '';
    const populationRange = document.getElementById('population-filter')?.value || '';
    const entityType = document.getElementById('entity-type-filter')?.value || '';

    // Build query params
    let url = `/api/feed?days=${daysFilter}&lead_type=${typeFilter}`;
    if (minUrgency > 0) url += `&min_urgency=${minUrgency}`;
    if (deadlineFilter) url += `&deadline_within_days=${deadlineFilter}`;
    if (decisionStage) url += `&decision_stage=${decisionStage}`;
    if (competitor) url += `&competitor=${competitor}`;
    if (entityType) url += `&entity_type=${entityType}`;

    // Parse population range
    if (populationRange) {
        if (populationRange.includes('-')) {
            const [min, max] = populationRange.split('-');
            url += `&min_population=${min}&max_population=${max}`;
        } else if (populationRange.includes('+')) {
            url += `&min_population=${populationRange.replace('+', '')}`;
        }
    }

    // Fetch and render
    const response = await fetch(url);
    const data = await response.json();
    renderFeed(data.leads);
}
```

### Week 2: Lead Detail Modal

**Day 1-3: Build Lead Detail Modal**

Create new file: `static/lead-detail-modal.js`

```javascript
async function openLeadDetailModal(leadId) {
    // Fetch full lead details
    const response = await fetch(`/api/leads/${leadId}/details`);
    const data = await response.json();

    // Create modal HTML
    const modal = document.createElement('div');
    modal.id = 'lead-detail-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    modal.onclick = (e) => {
        if (e.target === modal) closeLeadDetailModal();
    };

    modal.innerHTML = `
        <div class="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
            <!-- Header -->
            <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                <div>
                    <h2 class="text-xl font-bold text-gray-900">${data.lead.municipality}, ${data.lead.state}</h2>
                    <p class="text-sm text-gray-600">${data.lead.title}</p>
                </div>
                <button onclick="closeLeadDetailModal()" class="text-gray-400 hover:text-gray-600">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>

            <!-- Content: 8 Sections -->
            <div class="px-6 py-4">
                ${renderOverviewSection(data.lead)}
                ${renderSignalAnalysisSection(data.signal_analysis)}
                ${renderTemporalSection(data.temporal_intelligence)}
                ${renderCompetitiveSection(data.competitive_analysis)}
                ${renderROISection(data.roi_tracking)}
                ${renderTimelineSection(data.timeline)}
                ${renderMunicipalitySection(data.municipality)}
                ${renderRelatedLeadsSection(data.related_leads)}
            </div>

            <!-- Footer Actions -->
            <div class="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex items-center justify-between">
                <div class="flex space-x-2">
                    <button onclick="syncToCRM('${data.lead.id}')" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        Sync to CRM
                    </button>
                    <button onclick="updateLeadStatus('${data.lead.id}')" class="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700">
                        Update Status
                    </button>
                </div>
                <a href="${data.lead.url}" target="_blank" class="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50">
                    Open Document →
                </a>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

function renderOverviewSection(lead) {
    return `
        <div class="mb-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-3">Overview</h3>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <p class="text-sm text-gray-600">Lead Type</p>
                    <span class="px-3 py-1 text-sm font-bold rounded-full ${lead.lead_type === 'hot' ? 'bg-red-100 text-red-800' : 'bg-orange-100 text-orange-800'}">
                        ${lead.lead_type.toUpperCase()}
                    </span>
                </div>
                <div>
                    <p class="text-sm text-gray-600">Relevance Score</p>
                    <p class="text-2xl font-bold text-gray-900">${Math.round(lead.relevance_score)}/100</p>
                </div>
                <div>
                    <p class="text-sm text-gray-600">Customer Status</p>
                    <span class="px-3 py-1 text-sm font-semibold rounded-full ${lead.customer_status === 'existing_customer' ? 'bg-green-100 text-green-800' : 'bg-purple-100 text-purple-800'}">
                        ${lead.customer_status === 'existing_customer' ? 'EXISTING CUSTOMER' : 'NEW OPPORTUNITY'}
                    </span>
                </div>
                <div>
                    <p class="text-sm text-gray-600">Source Type</p>
                    <p class="text-sm font-medium text-gray-900">${lead.source_type}</p>
                </div>
            </div>
        </div>
    `;
}

// ... other section render functions
```

**Day 4-5: Style and polish modal, add keyboard shortcuts (ESC to close)**

---

## 📊 Effort Estimate

| Task | Time | Complexity |
|------|------|------------|
| Enhanced lead cards | 2 days | Low |
| Advanced filters UI | 2 days | Medium |
| Update loadFeed() | 1 day | Low |
| Lead detail modal | 3 days | Medium |
| Keyboard shortcuts | 0.5 days | Low |
| Testing & polish | 1.5 days | Low |
| **TOTAL** | **10 days** | **Medium** |

---

## 🎯 Success Criteria

After Priority 1 UI:
- ✅ Users can see urgency, deadlines, competitors on feed
- ✅ Users can filter by 10+ parameters
- ✅ Users can click lead for full 8-section detail view
- ✅ Lead cards show 80% of enterprise intelligence
- ✅ UI feels "enterprise-grade" and justifies $300-500/mo pricing

---

## 🚀 Quick Wins (Do First)

**1-2 Hour Tasks:**
1. Add urgency badge to lead cards (30 min)
2. Add deadline to lead cards (30 min)
3. Add competitors to lead cards (30 min)
4. Add click handler to open detail modal (30 min)
5. Add min-urgency slider filter (30 min)

**Before building modal, these 5 quick wins make feed 5x better!**

---

*Current UI: Functional but basic (10/100 features visible)*
*After Priority 1: Enterprise-ready (80/100 features visible)*
