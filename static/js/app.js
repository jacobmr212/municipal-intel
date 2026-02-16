// Municipal Intel - Frontend Application

// Global state
let currentScanId = null;
let pollInterval = null;
let allLeads = [];
let filteredLeads = [];
let currentFilter = 'all';
let currentSort = 'score';
let currentView = 'table';

// Caselle Territory states
const CASELLE_STATES = ['UT', 'ID', 'WY', 'MT', 'CO', 'NV', 'NM', 'ND', 'SD', 'OR', 'WA'];

// All states with municipalities
const ALL_STATES = ['UT', 'ID', 'WY', 'MT', 'CO', 'NV', 'NM', 'ND', 'SD', 'OR', 'WA', 'MN', 'AZ', 'CA', 'WI', 'IA', 'NE', 'KS', 'OK', 'TX', 'AK', 'HI', 'ME', 'VT', 'NH', 'MA', 'RI', 'CT'];

// Population tier display names
const TIER_NAMES = {
    'micro': 'Micro (<2,500)',
    'small': 'Small (2,500-10,000)',
    'small-mid': 'Small-Mid (10,000-25,000)',
    'mid-market': 'Mid-Market (25,000-75,000)',
    'upper-mid': 'Upper-Mid (75,000-150,000)',
    'large': 'Large (150,000+)'
};

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    initializeStateSelector();
    initializeTierSelector();
    loadScanHistory();
    updateConfigSummary();
});

// Initialize state selector
function initializeStateSelector() {
    const container = document.getElementById('stateSelector');

    ALL_STATES.forEach(state => {
        const label = document.createElement('label');
        label.className = 'state-checkbox';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = state;
        checkbox.id = `state-${state}`;
        checkbox.addEventListener('change', updateConfigSummary);

        const span = document.createElement('span');
        span.textContent = state;

        label.appendChild(checkbox);
        label.appendChild(span);
        container.appendChild(label);
    });
}

// Initialize tier selector
function initializeTierSelector() {
    const radios = document.querySelectorAll('input[name="tier"]');
    radios.forEach(radio => {
        radio.addEventListener('change', updateConfigSummary);
    });
}

// Caselle Territory quick select
document.getElementById('caselleTerritory').addEventListener('click', (e) => {
    e.preventDefault();

    // Uncheck all states first
    ALL_STATES.forEach(state => {
        document.getElementById(`state-${state}`).checked = false;
    });

    // Check Caselle Territory states
    CASELLE_STATES.forEach(state => {
        const checkbox = document.getElementById(`state-${state}`);
        if (checkbox) {
            checkbox.checked = true;
        }
    });

    updateConfigSummary();
});

// ============================================================
// CONFIG SUMMARY
// ============================================================

async function updateConfigSummary() {
    const selectedStates = getSelectedStates();
    const selectedTier = getSelectedTier();

    // Update states display
    document.getElementById('selectedStates').textContent =
        selectedStates.length > 0 ? selectedStates.join(', ') : 'None selected';

    // Update tier display
    document.getElementById('selectedTier').textContent = TIER_NAMES[selectedTier];

    // Query API for actual city count
    let citiesMatched = 0;
    if (selectedStates.length > 0) {
        try {
            // For now, estimate based on known data
            // Utah Small-Mid (10K-25K) = ~8-10 cities
            // We can add a real API endpoint later if needed
            const tierEstimates = {
                'micro': 5,
                'small': 8,
                'small-mid': 6,
                'mid-market': 4,
                'upper-mid': 2,
                'large': 1
            };
            citiesMatched = selectedStates.length * (tierEstimates[selectedTier] || 5);
        } catch (error) {
            citiesMatched = 0;
        }
    }

    document.getElementById('citiesMatched').textContent = citiesMatched;

    // Update estimated time
    const estimatedMinutes = citiesMatched > 0 ? Math.ceil(citiesMatched * 0.5) : 0;
    document.getElementById('estimatedTime').textContent = estimatedMinutes > 0 ? `~${estimatedMinutes} min` : '--';

    // Update scan summary text
    if (selectedStates.length === 0) {
        document.getElementById('scanSummaryText').textContent = 'Select states to scan';
    } else {
        document.getElementById('scanSummaryText').textContent =
            `Scanning ${citiesMatched} cities across ${selectedStates.length} state${selectedStates.length !== 1 ? 's' : ''}`;
    }

    // Enable/disable Run Scan button
    document.getElementById('runScanBtn').disabled = selectedStates.length === 0;
}

function getSelectedStates() {
    return ALL_STATES.filter(state =>
        document.getElementById(`state-${state}`).checked
    );
}

function getSelectedTier() {
    const selectedRadio = document.querySelector('input[name="tier"]:checked');
    return selectedRadio ? selectedRadio.value : 'small';
}

function getSelectedSourceTypes() {
    const types = [];
    if (document.getElementById('sourceTypeMeetings').checked) types.push('meeting_minutes');
    if (document.getElementById('sourceTypeProcurement').checked) types.push('procurement');
    if (document.getElementById('sourceTypeBudget').checked) types.push('budget');
    if (document.getElementById('sourceTypeJobs').checked) types.push('job_posting');
    return types;
}

// ============================================================
// SCAN CONTROL
// ============================================================

async function startScan() {
    const states = getSelectedStates();
    const tier = getSelectedTier();
    const sourceTypes = getSelectedSourceTypes();

    if (states.length === 0) {
        alert('Please select at least one state');
        return;
    }

    const config = {
        states: states,
        population_tier: tier,
        source_types: sourceTypes
    };

    try {
        // Start scan
        const response = await fetch('/api/scans', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();
        currentScanId = data.scan_id;

        // Switch to progress view
        showView('progressView');

        // Start polling for progress
        startProgressPolling();

    } catch (error) {
        console.error('Error starting scan:', error);
        alert('Error starting scan. Please try again.');
    }
}

function startProgressPolling() {
    // Poll every 2 seconds
    pollInterval = setInterval(async () => {
        await updateProgress();
    }, 2000);

    // Initial update
    updateProgress();
}

async function updateProgress() {
    if (!currentScanId) return;

    try {
        const response = await fetch(`/api/scans/${currentScanId}`);
        const scan = await response.json();

        // Update phase indicators
        updatePhaseIndicators(scan.progress_phase);

        // Update progress bar
        document.getElementById('progressBar').style.width = `${scan.progress_pct}%`;
        document.getElementById('progressPct').textContent = `${scan.progress_pct}%`;
        document.getElementById('progressMessage').textContent = scan.progress_message || '';

        // Update stats
        if (scan.stats) {
            document.getElementById('statSources').textContent = scan.stats.sources_found || 0;
            document.getElementById('statDocs').textContent = scan.stats.docs_scraped || 0;
            document.getElementById('statLeads').textContent = scan.stats.total_leads || 0;
        }

        // Check if scan is complete
        if (scan.status === 'completed') {
            stopProgressPolling();
            await loadResults(currentScanId);
            showView('resultsView');
            loadScanHistory();
        } else if (scan.status === 'failed') {
            stopProgressPolling();
            alert('Scan failed: ' + (scan.progress_message || 'Unknown error'));
            showView('configView');
        }

    } catch (error) {
        console.error('Error polling progress:', error);
    }
}

function updatePhaseIndicators(currentPhase) {
    const phases = ['discovery', 'scraping', 'analysis', 'complete'];
    const currentIndex = phases.indexOf(currentPhase);

    phases.forEach((phase, index) => {
        const indicator = document.querySelector(`.phase-indicator[data-phase="${phase}"]`);
        if (indicator) {
            if (index < currentIndex) {
                indicator.classList.add('completed');
                indicator.classList.remove('active');
            } else if (index === currentIndex) {
                indicator.classList.add('active');
                indicator.classList.remove('completed');
            } else {
                indicator.classList.remove('active', 'completed');
            }
        }
    });
}

function stopProgressPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// ============================================================
// RESULTS
// ============================================================

async function loadResults(scanId) {
    try {
        const response = await fetch(`/api/scans/${scanId}/leads`);
        const data = await response.json();

        allLeads = data.leads || [];
        filteredLeads = [...allLeads];

        // Update results summary
        const stats = {
            total: allLeads.length,
            hot: allLeads.filter(l => l.lead_type === 'hot').length,
            warm: allLeads.filter(l => l.lead_type === 'warm').length,
            cold: allLeads.filter(l => l.lead_type === 'cold').length
        };

        const cities = new Set(allLeads.map(l => l.municipality)).size;

        document.getElementById('resultsSummary').textContent =
            `Found ${stats.total} leads across ${cities} cities — ${stats.hot} hot, ${stats.warm} warm, ${stats.cold} cold`;

        // Render leads
        renderLeads();

    } catch (error) {
        console.error('Error loading results:', error);
    }
}

function renderLeads() {
    if (currentView === 'table') {
        renderTableView();
    } else {
        renderCardView();
    }
}

function renderTableView() {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    filteredLeads.forEach(lead => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${lead.municipality}</td>
            <td>${lead.state}</td>
            <td>${lead.population.toLocaleString()}</td>
            <td>${lead.relevance_score.toFixed(1)}</td>
            <td><span class="lead-type-badge ${lead.lead_type}">${lead.lead_type}</span></td>
            <td>${formatSourceType(lead.source_type)}</td>
            <td>${lead.date || '—'}</td>
            <td>${truncate(lead.recommended_action || '', 50)}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderCardView() {
    const container = document.getElementById('cardView');
    container.innerHTML = '';

    filteredLeads.forEach(lead => {
        const card = document.createElement('div');
        card.className = 'lead-card';

        const signals = lead.signal_matches ? Object.keys(lead.signal_matches) : [];

        card.innerHTML = `
            <div class="lead-card-header">
                <div>
                    <div class="lead-card-title">${lead.municipality}</div>
                    <div class="lead-card-location">${lead.state} • ${lead.population.toLocaleString()}</div>
                </div>
                <div class="lead-card-score">${lead.relevance_score.toFixed(0)}</div>
            </div>
            <div class="lead-card-action">${truncate(lead.recommended_action || '', 100)}</div>
            <div class="lead-card-signals">
                ${signals.slice(0, 5).map(s => `<span class="signal-pill">${s}</span>`).join('')}
            </div>
            <div class="lead-card-footer">
                <span class="lead-card-source">${formatSourceType(lead.source_type)}</span>
                <a href="${lead.url}" target="_blank" class="lead-card-link">View Source →</a>
            </div>
        `;

        container.appendChild(card);
    });
}

// ============================================================
// FILTERS & SORTING
// ============================================================

function filterLeads(type) {
    currentFilter = type;

    // Update filter tab active state
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`.filter-tab[data-type="${type}"]`).classList.add('active');

    // Filter leads
    if (type === 'all') {
        filteredLeads = [...allLeads];
    } else {
        filteredLeads = allLeads.filter(lead => lead.lead_type === type);
    }

    // Re-sort and render
    sortLeads(currentSort);
}

function sortLeads(field) {
    currentSort = field;

    filteredLeads.sort((a, b) => {
        switch (field) {
            case 'municipality':
                return a.municipality.localeCompare(b.municipality);
            case 'state':
                return a.state.localeCompare(b.state);
            case 'population':
                return b.population - a.population;
            case 'score':
                return b.relevance_score - a.relevance_score;
            case 'type':
                const typeOrder = { hot: 0, warm: 1, cold: 2 };
                return typeOrder[a.lead_type] - typeOrder[b.lead_type];
            case 'source':
                return a.source_type.localeCompare(b.source_type);
            case 'date':
                return (b.date || '').localeCompare(a.date || '');
            default:
                return 0;
        }
    });

    renderLeads();
}

function switchView(view) {
    currentView = view;

    // Update view toggle buttons
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Show/hide views
    document.getElementById('tableView').classList.toggle('active', view === 'table');
    document.getElementById('cardView').classList.toggle('active', view === 'card');

    renderLeads();
}

// ============================================================
// EXPORT
// ============================================================

async function exportResults(format) {
    if (!currentScanId) return;

    try {
        const url = `/api/export/${currentScanId}?format=${format}`;

        if (format === 'html') {
            // Open in new tab
            window.open(url, '_blank');
        } else {
            // Download JSON
            const response = await fetch(url);
            const data = await response.json();

            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const downloadUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `municipal-intel-${currentScanId}.json`;
            a.click();
            URL.revokeObjectURL(downloadUrl);
        }

    } catch (error) {
        console.error('Error exporting results:', error);
        alert('Error exporting results');
    }
}

// ============================================================
// SCAN HISTORY
// ============================================================

async function loadScanHistory() {
    try {
        const response = await fetch('/api/scans');
        const data = await response.json();

        const container = document.getElementById('scanHistory');
        container.innerHTML = '';

        if (data.scans && data.scans.length > 0) {
            data.scans.slice(0, 5).forEach(scan => {
                const item = document.createElement('div');
                item.className = 'scan-history-item';
                item.onclick = () => loadPastScan(scan.id);

                const date = new Date(scan.created_at).toLocaleDateString();
                const states = scan.config?.states?.join(', ') || 'N/A';
                const leadCount = scan.stats?.total_leads || 0;

                item.innerHTML = `
                    <div class="scan-history-date">${date}</div>
                    <div class="scan-history-stats">${states} • ${leadCount} leads</div>
                `;

                container.appendChild(item);
            });
        } else {
            container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.875rem;">No scans yet</div>';
        }

    } catch (error) {
        console.error('Error loading scan history:', error);
    }
}

async function loadPastScan(scanId) {
    currentScanId = scanId;
    await loadResults(scanId);
    showView('resultsView');
}

// ============================================================
// UI HELPERS
// ============================================================

function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(viewId).classList.add('active');
}

function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    const icon = document.getElementById(`${sectionId}Icon`);

    section.classList.toggle('collapsed');
    icon.style.transform = section.classList.contains('collapsed') ? 'rotate(-90deg)' : 'rotate(0deg)';
}

function formatSourceType(type) {
    const map = {
        'meeting_minutes': 'Meeting Minutes',
        'procurement': 'Procurement',
        'budget': 'Budget',
        'job_posting': 'Job Posting',
        'agenda_packet': 'Agenda Packet',
        'audit': 'Audit'
    };
    return map[type] || type;
}

function truncate(str, length) {
    if (!str) return '';
    return str.length > length ? str.substring(0, length) + '...' : str;
}
