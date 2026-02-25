# UI Enhancements for Enterprise Features

The backend APIs for all 13 enterprise features are complete and working. This document outlines the UI enhancements needed to expose these features to users.

## Current UI State

✅ **Existing Pages**:
- Landing page (`/`)
- Login/magic link (`/login`)
- Scanner page with Feed, Scanner, Watchlist, Territories tabs (`/scanner`)
- Dashboard (`/dashboard`)
- Admin panel (`/admin`)

**Current Feed** has basic filters:
- Lead type (hot/warm/cold)
- Days filter (7/30/90)
- Simple list view with municipality, score, source type

---

## Required UI Enhancements

### Priority 1: Essential (Launch Blockers)

#### 1.1 Enhanced Feed Filters
**Location**: `/scanner` → Feed tab

**Add Filter UI**:
```html
<!-- Urgency Filter -->
<label>Urgency</label>
<input type="range" min="0" max="100" id="urgency-slider">
<span id="urgency-value">60+</span>

<!-- Deadline Filter -->
<select id="deadline-filter">
  <option value="">All Deadlines</option>
  <option value="7">Within 7 days</option>
  <option value="14">Within 14 days</option>
  <option value="30">Within 30 days</option>
</select>

<!-- Competitor Filter -->
<select id="competitor-filter">
  <option value="">All Leads</option>
  <option value="has_competitors">Has Competitors</option>
  <option value="tyler">Tyler Technologies</option>
  <option value="centralsquare">CentralSquare</option>
</select>

<!-- Customer Status Filter -->
<select id="customer-status-filter">
  <option value="">All</option>
  <option value="existing_customer">Existing Customers</option>
  <option value="new_opportunity">New Opportunities</option>
</select>

<!-- ROI Status Filter -->
<select id="status-filter">
  <option value="">All Status</option>
  <option value="new">New</option>
  <option value="contacted">Contacted</option>
  <option value="qualified">Qualified</option>
  <option value="proposal">Proposal Sent</option>
</select>
```

**JavaScript**:
```javascript
function loadFeed() {
    const params = new URLSearchParams({
        lead_type: document.getElementById('feed-type-filter').value,
        min_urgency: document.getElementById('urgency-slider').value,
        deadline_within_days: document.getElementById('deadline-filter').value,
        competitor: document.getElementById('competitor-filter').value,
        customer_status: document.getElementById('customer-status-filter').value,
        status: document.getElementById('status-filter').value,
        limit: 50
    });

    fetch(`/api/feed?${params}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    })
    .then(res => res.json())
    .then(data => renderFeed(data.leads));
}
```

#### 1.2 Enhanced Lead Cards
**Location**: Feed list items

**Add to Lead Card**:
```html
<div class="lead-card">
    <div class="lead-header">
        <span class="lead-badge">{{ lead.lead_type.upper() }}</span>

        <!-- NEW: Urgency Badge -->
        {% if lead.urgency_score >= 80 %}
        <span class="urgency-critical">🔴 CRITICAL</span>
        {% elif lead.urgency_score >= 60 %}
        <span class="urgency-high">🟠 HIGH URGENCY</span>
        {% endif %}

        <!-- NEW: Deadline -->
        {% if lead.deadline_date %}
        <span class="deadline">📅 Deadline: {{ lead.deadline_date }}</span>
        {% endif %}

        <!-- NEW: Existing Customer Flag -->
        {% if lead.customer_status == 'existing_customer' %}
        <span class="existing-customer">⭐ EXISTING CUSTOMER</span>
        {% endif %}
    </div>

    <div class="lead-body">
        <h3>{{ lead.municipality }}, {{ lead.state }}</h3>
        <p class="text-sm">{{ lead.title[:100] }}...</p>

        <!-- NEW: Competitor Badge -->
        {% if lead.competitors_mentioned %}
        <div class="competitors">
            <span class="text-xs">Competitors: {{ ', '.join(lead.competitors_mentioned[:3]) }}</span>
        </div>
        {% endif %}

        <!-- NEW: Decision Stage -->
        {% if lead.decision_stage %}
        <span class="decision-stage">Stage: {{ lead.decision_stage }}</span>
        {% endif %}
    </div>

    <div class="lead-actions">
        <button onclick="viewLeadDetails('{{ lead.id }}')">View Details</button>

        <!-- NEW: CRM Sync Button -->
        {% if not lead.crm_synced %}
        <button onclick="syncToCRM('{{ lead.id }}')">Sync to CRM</button>
        {% else %}
        <a href="{{ lead.crm_url }}" target="_blank">View in CRM</a>
        {% endif %}

        <!-- NEW: Update Status -->
        <select onchange="updateLeadStatus('{{ lead.id }}', this.value)">
            <option value="new" {% if lead.status == 'new' %}selected{% endif %}>New</option>
            <option value="contacted" {% if lead.status == 'contacted' %}selected{% endif %}>Contacted</option>
            <option value="qualified" {% if lead.status == 'qualified' %}selected{% endif %}>Qualified</option>
            <option value="proposal" {% if lead.status == 'proposal' %}selected{% endif %}>Proposal</option>
            <option value="won" {% if lead.status == 'won' %}selected{% endif %}>Won</option>
            <option value="lost" {% if lead.status == 'lost' %}selected{% endif %}>Lost</option>
        </select>
    </div>
</div>
```

#### 1.3 Lead Detail Modal
**Location**: Modal popup when clicking "View Details"

**Create Modal**:
```html
<div id="lead-detail-modal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <h2 id="lead-title"></h2>
            <button onclick="closeModal()">&times;</button>
        </div>

        <div class="modal-body">
            <!-- Tabs -->
            <div class="tabs">
                <button class="tab active" data-tab="overview">Overview</button>
                <button class="tab" data-tab="signals">Signals</button>
                <button class="tab" data-tab="temporal">Urgency & Deadlines</button>
                <button class="tab" data-tab="competitive">Competitive Intel</button>
                <button class="tab" data-tab="timeline">Timeline</button>
            </div>

            <!-- Tab Content -->
            <div id="tab-overview" class="tab-content active">
                <div class="lead-info-grid">
                    <div>
                        <label>Municipality</label>
                        <p id="detail-municipality"></p>
                    </div>
                    <div>
                        <label>Population</label>
                        <p id="detail-population"></p>
                    </div>
                    <div>
                        <label>Relevance Score</label>
                        <p id="detail-score"></p>
                    </div>
                    <div>
                        <label>Lead Type</label>
                        <p id="detail-type"></p>
                    </div>
                    <div>
                        <label>Customer Status</label>
                        <p id="detail-customer-status"></p>
                    </div>
                    <div>
                        <label>Current Status</label>
                        <p id="detail-status"></p>
                    </div>
                </div>
            </div>

            <div id="tab-signals" class="tab-content">
                <h3>Signal Matches</h3>
                <div id="signals-list"></div>
            </div>

            <div id="tab-temporal" class="tab-content">
                <div class="urgency-meter">
                    <label>Urgency Score</label>
                    <div class="progress-bar">
                        <div id="urgency-fill" class="progress-fill"></div>
                    </div>
                    <p id="urgency-label"></p>
                </div>

                <div class="deadline-info">
                    <label>Deadline</label>
                    <p id="deadline-info"></p>
                </div>

                <div class="decision-stage">
                    <label>Decision Stage</label>
                    <p id="decision-stage-info"></p>
                </div>
            </div>

            <div id="tab-competitive" class="tab-content">
                <h3>Competitors Mentioned</h3>
                <div id="competitors-list"></div>

                <h3>Existing Vendor</h3>
                <p id="existing-vendor"></p>

                <h3>Competitive Context</h3>
                <p id="competitive-context"></p>
            </div>

            <div id="tab-timeline" class="tab-content">
                <div class="timeline">
                    <div class="timeline-item">
                        <span class="timeline-date" id="first-seen"></span>
                        <span class="timeline-event">Lead Discovered</span>
                    </div>
                    <div class="timeline-item" id="contacted-event">
                        <span class="timeline-date"></span>
                        <span class="timeline-event">Contacted</span>
                    </div>
                    <div class="timeline-item" id="won-event">
                        <span class="timeline-date"></span>
                        <span class="timeline-event">Deal Won</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="modal-footer">
            <button onclick="syncToCRM(currentLeadId)">Sync to CRM</button>
            <button onclick="closeModal()">Close</button>
        </div>
    </div>
</div>

<script>
async function viewLeadDetails(leadId) {
    const response = await fetch(`/api/leads/${leadId}/details`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });

    const data = await response.json();

    // Populate modal with data
    document.getElementById('lead-title').textContent = data.lead.title;
    document.getElementById('detail-municipality').textContent =
        `${data.lead.municipality}, ${data.lead.state}`;
    document.getElementById('detail-population').textContent =
        data.lead.population.toLocaleString();
    // ... etc

    // Show modal
    document.getElementById('lead-detail-modal').style.display = 'block';
}
</script>
```

---

### Priority 2: High Value

#### 2.1 Analytics Dashboard Tab
**Location**: New tab in `/scanner`

**Add Tab**:
```html
<button onclick="switchTab('analytics')" id="tab-analytics" class="tab-button">
    <svg><!-- Chart icon --></svg>
    Analytics
</button>
```

**Tab Content**:
```html
<div id="content-analytics" class="tab-content">
    <h2>Analytics Dashboard</h2>

    <!-- Overview Cards -->
    <div class="stats-grid">
        <div class="stat-card">
            <label>Total Leads</label>
            <p id="stat-total-leads">0</p>
        </div>
        <div class="stat-card hot">
            <label>Hot Leads</label>
            <p id="stat-hot-leads">0</p>
        </div>
        <div class="stat-card">
            <label>Avg Urgency</label>
            <p id="stat-avg-urgency">0</p>
        </div>
        <div class="stat-card">
            <label>Synced to CRM</label>
            <p id="stat-crm-synced">0</p>
        </div>
    </div>

    <!-- Charts -->
    <div class="charts-grid">
        <div class="chart-card">
            <h3>Lead Types Distribution</h3>
            <canvas id="lead-types-chart"></canvas>
        </div>

        <div class="chart-card">
            <h3>Leads Over Time</h3>
            <canvas id="leads-timeline-chart"></canvas>
        </div>

        <div class="chart-card">
            <h3>Top Competitors</h3>
            <canvas id="competitors-chart"></canvas>
        </div>

        <div class="chart-card">
            <h3>Pipeline Status</h3>
            <canvas id="pipeline-chart"></canvas>
        </div>
    </div>

    <!-- ROI Metrics -->
    <div class="roi-section">
        <h3>ROI Metrics</h3>
        <div class="roi-grid">
            <div class="roi-card">
                <label>Total Revenue (Won Deals)</label>
                <p id="roi-revenue">$0</p>
            </div>
            <div class="roi-card">
                <label>Avg Deal Size</label>
                <p id="roi-avg-deal">$0</p>
            </div>
            <div class="roi-card">
                <label>Conversion Rate</label>
                <p id="roi-conversion">0%</p>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
async function loadAnalytics() {
    const response = await fetch('/api/analytics/dashboard?days=30', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });

    const data = await response.json();

    // Update stats cards
    document.getElementById('stat-total-leads').textContent = data.overview.total_leads;
    document.getElementById('stat-hot-leads').textContent = data.overview.hot_leads;

    // Render charts
    renderLeadTypesChart(data.distributions.lead_types);
    renderTimelineChart(data.time_series);
    renderCompetitorsChart(data.competitors.top_competitors);
    renderPipelineChart(data.pipeline.distribution);
}

function renderLeadTypesChart(data) {
    const ctx = document.getElementById('lead-types-chart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Hot', 'Warm', 'Cold'],
            datasets: [{
                data: [data.hot, data.warm, data.cold],
                backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6']
            }]
        }
    });
}
</script>
```

#### 2.2 CRM Configuration Page
**Location**: New Settings tab

**Add Settings Tab**:
```html
<button onclick="switchTab('settings')" id="tab-settings" class="tab-button">
    <svg><!-- Settings icon --></svg>
    Settings
</button>
```

**Settings Content**:
```html
<div id="content-settings" class="tab-content">
    <h2>CRM Integration</h2>

    <!-- Salesforce Config -->
    <div class="crm-config-card">
        <h3>Salesforce</h3>
        <form id="salesforce-form">
            <label>Username</label>
            <input type="email" name="username" placeholder="user@company.com">

            <label>Password</label>
            <input type="password" name="password">

            <label>Security Token</label>
            <input type="text" name="security_token" placeholder="Salesforce security token">

            <label>Auto-sync Hot Leads</label>
            <input type="checkbox" name="auto_sync_hot_leads" checked>

            <button type="submit">Save Salesforce Config</button>
        </form>
    </div>

    <!-- HubSpot Config -->
    <div class="crm-config-card">
        <h3>HubSpot</h3>
        <form id="hubspot-form">
            <label>Access Token</label>
            <input type="text" name="access_token" placeholder="Private app access token">

            <label>Portal ID</label>
            <input type="text" name="portal_id" placeholder="12345678">

            <label>Auto-sync Hot Leads</label>
            <input type="checkbox" name="auto_sync_hot_leads" checked>

            <button type="submit">Save HubSpot Config</button>
        </form>
    </div>

    <!-- Email Preferences -->
    <div class="email-prefs-card">
        <h3>Email Notifications</h3>
        <form id="email-prefs-form">
            <label>
                <input type="checkbox" name="alert_on_hot_leads" checked>
                Alert me for Hot Leads
            </label>

            <label>
                <input type="checkbox" name="alert_on_urgent_leads" checked>
                Alert me for Urgent Leads (urgency >= 60)
            </label>

            <label>
                <input type="checkbox" name="daily_digest_enabled">
                Send Daily Digest
            </label>

            <label>Minimum Urgency for Alerts</label>
            <input type="range" name="min_urgency_for_alert" min="0" max="100" value="60">

            <button type="submit">Save Email Preferences</button>
        </form>
    </div>
</div>

<script>
document.getElementById('salesforce-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const response = await fetch('/api/crm/config', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            provider: 'salesforce',
            credentials: {
                username: formData.get('username'),
                password: formData.get('password'),
                security_token: formData.get('security_token')
            },
            auto_sync_hot_leads: formData.get('auto_sync_hot_leads') === 'on'
        })
    });

    if (response.ok) {
        alert('✅ Salesforce configured successfully!');
    } else {
        alert('❌ Failed to configure Salesforce');
    }
});
</script>
```

---

### Priority 3: Nice to Have

#### 3.1 Bulk CRM Sync
**Location**: Feed tab header

**Add Bulk Actions**:
```html
<div class="bulk-actions">
    <input type="checkbox" id="select-all" onchange="toggleSelectAll()">
    <label>Select All</label>

    <button onclick="bulkSyncToCRM()" id="bulk-sync-btn" style="display:none;">
        Sync Selected to CRM (<span id="selected-count">0</span>)
    </button>

    <button onclick="bulkUpdateStatus()" id="bulk-status-btn" style="display:none;">
        Update Status
    </button>
</div>

<script>
const selectedLeads = new Set();

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all').checked;
    document.querySelectorAll('.lead-checkbox').forEach(cb => {
        cb.checked = selectAll;
        if (selectAll) {
            selectedLeads.add(cb.dataset.leadId);
        } else {
            selectedLeads.clear();
        }
    });
    updateBulkActionsVisibility();
}

async function bulkSyncToCRM() {
    const provider = prompt('Enter CRM provider (salesforce or hubspot):');

    const response = await fetch('/api/crm/sync', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            lead_ids: Array.from(selectedLeads),
            provider: provider,
            update_existing: true
        })
    });

    const result = await response.json();
    alert(`✅ Synced ${result.summary.successful} of ${result.summary.total} leads`);
    selectedLeads.clear();
    loadFeed();
}
</script>
```

#### 3.2 Export to CSV
**Location**: Feed tab header

**Add Export Button**:
```html
<button onclick="exportFeedToCSV()">
    <svg><!-- Download icon --></svg>
    Export to CSV
</button>

<script>
async function exportFeedToCSV() {
    const params = new URLSearchParams({
        // ... all current filters
        limit: 1000  // Export up to 1000 leads
    });

    const response = await fetch(`/api/feed?${params}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });

    const data = await response.json();

    // Convert to CSV
    const csv = convertToCSV(data.leads);

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `municipal-intel-leads-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
}

function convertToCSV(leads) {
    const headers = ['Municipality', 'State', 'Population', 'Lead Type', 'Relevance Score',
                     'Urgency Score', 'Deadline', 'Existing Vendor', 'Status', 'URL'];

    const rows = leads.map(lead => [
        lead.municipality,
        lead.state,
        lead.population,
        lead.lead_type,
        lead.relevance_score,
        lead.urgency_score || 0,
        lead.deadline_date || '',
        lead.existing_vendor || '',
        lead.status,
        lead.url
    ]);

    return [headers, ...rows].map(row => row.join(',')).join('\n');
}
</script>
```

---

## Implementation Priority

**Week 1: Critical Path**
1. Enhanced Feed Filters (1.1)
2. Enhanced Lead Cards (1.2)
3. Lead Detail Modal (1.3)
4. Update requirements.txt and deploy

**Week 2: High Value Features**
5. Analytics Dashboard Tab (2.1)
6. CRM Configuration Page (2.2)
7. Test everything end-to-end

**Week 3: Polish**
8. Bulk CRM Sync (3.1)
9. Export to CSV (3.2)
10. UI polish and mobile responsiveness

---

## Testing Checklist

- [ ] Feed filters work correctly (urgency, deadline, competitor, etc.)
- [ ] Lead cards display new fields (urgency badges, competitors, deadlines)
- [ ] Lead detail modal loads all sections from API
- [ ] CRM sync button syncs leads to Salesforce/HubSpot
- [ ] Status updates persist to database
- [ ] Analytics dashboard loads charts correctly
- [ ] CRM configuration saves and encrypts credentials
- [ ] Email preferences update successfully
- [ ] Bulk actions work for multiple leads
- [ ] CSV export includes all fields
- [ ] Mobile responsive design

---

## Quick Start

To test the backend APIs without UI:

```bash
python3 test_enterprise_features.py --url https://your-app.railway.app --email your@email.com
```

This will verify all 13 phases are working correctly before building UI.

---

*UI enhancements can be built incrementally while the backend is already production-ready.*
