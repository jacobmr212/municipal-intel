"""
Municipal Intel — Government ERP Lead Intelligence Platform
Main Streamlit application.
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime
from collections import namedtuple

import streamlit as st

from src.discovery import SourceDiscovery, DiscoveredSource
from src.scraper import MunicipalScraper
from src.analyzer import DocumentAnalyzer
from src.reporter import ReportGenerator
from src.database import SessionLocal, Municipality, MunicipalSource

# --- Page Config ---
st.set_page_config(
    page_title="Municipal Intel",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Data ---
DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

# --- Population Tiers (Government ERP Sales Segments) ---
POPULATION_TIERS = {
    "Micro (under 2,500)": (0, 2500),
    "Small (2,500 – 10,000)": (2500, 10000),
    "Small-Mid (10,000 – 25,000)": (10000, 25000),
    "Mid-Market (25,000 – 75,000)": (25000, 75000),
    "Upper-Mid (75,000 – 150,000)": (75000, 150000),
    "Large (150,000+)": (150000, 10000000),
    "All Cities": (0, 10000000),
    "Custom": (0, 10000000),
}

# --- Caselle Territory States ---
CASELLE_TERRITORY = ["UT", "ID", "WY", "MT", "CO", "NV", "NM", "ND", "SD", "OR", "WA"]


@st.cache_data
def load_municipalities():
    """Load municipalities from database."""
    db = SessionLocal()
    try:
        municipalities = db.query(Municipality).all()

        # Convert to JSON-like structure for compatibility with existing UI code
        # Group by state
        states = {}
        for muni in municipalities:
            if muni.state not in states:
                states[muni.state] = {
                    "name": muni.state,  # State name lookup could be added later
                    "municipalities": []
                }

            states[muni.state]["municipalities"].append({
                "id": muni.id,
                "name": muni.name,
                "state": muni.state,
                "population": muni.population,
                "domain": muni.domain,
                "domain_status": muni.domain_status,
                "resolved_url": muni.resolved_url,
            })

        return {"states": states}
    finally:
        db.close()


def get_state_options(db: dict) -> dict:
    """Build state selection options with enrichment status."""
    session = SessionLocal()
    try:
        states = db.get("states", {})
        options = {}
        for abbr, info in sorted(states.items(), key=lambda x: x[0]):
            count = len(info.get("municipalities", []))

            # Count verified cities
            verified_count = session.query(Municipality).filter_by(
                state=abbr,
                domain_status="verified"
            ).count()

            enrichment_pct = int((verified_count / count * 100)) if count > 0 else 0
            options[abbr] = f"{abbr} ({count} cities, {enrichment_pct}% enriched)"
        return options
    finally:
        session.close()


# --- Custom CSS ---
st.markdown("""
<style>
    /* === Global Reset & Base === */
    * { margin: 0; padding: 0; box-sizing: border-box; }

    .stApp {
        background-color: #09090B;
    }

    section[data-testid="stSidebar"] {
        background-color: #1A1A1F;
        border-right: 1px solid #1F1F23;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 2rem;
    }

    /* === Top Accent Bar === */
    .stApp::before {
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #4F6AFF 0%, #6B7FFF 100%);
        z-index: 999999;
    }

    /* === Typography === */
    body, .stMarkdown, .stText {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
        line-height: 1.65;
        -webkit-font-smoothing: antialiased;
    }

    h1, h2, h3, h4, h5, h6 {
        font-weight: 600;
        line-height: 1.3;
        letter-spacing: -0.02em;
    }

    /* === Header === */
    .main-header {
        font-size: 32px;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: #E5E7EB;
        margin-bottom: 6px;
        margin-top: 1rem;
    }

    .main-header .accent {
        color: #4F6AFF;
        font-weight: 800;
    }

    .sub-header {
        color: #6B7280;
        font-size: 14px;
        font-weight: 400;
        line-height: 1.5;
        margin-bottom: 32px;
    }

    /* === Sidebar === */
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #9CA3AF;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }

    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 13px;
        color: #6B7280;
        line-height: 1.6;
    }

    .help-text {
        font-size: 12px;
        color: #6B7280;
        margin-top: 4px;
        line-height: 1.4;
    }

    /* === Stat Boxes === */
    .stat-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 16px;
        margin: 24px 0 32px 0;
    }

    .stat-box {
        background: #111113;
        border: 1px solid #1F1F23;
        border-radius: 8px;
        padding: 20px;
        position: relative;
    }

    .stat-box::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 3px;
        border-radius: 8px 0 0 8px;
    }

    .stat-box.total::before { background: #4F6AFF; }
    .stat-box.hot::before { background: #DC3545; }
    .stat-box.warm::before { background: #D97706; }
    .stat-box.cold::before { background: #3B82F6; }

    .stat-box .label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6B7280;
        font-weight: 500;
        margin-bottom: 8px;
    }

    .stat-box .value {
        font-size: 32px;
        font-weight: 700;
        line-height: 1;
        color: #E5E7EB;
    }

    /* === Pre-Scan Briefing === */
    .pre-scan-briefing {
        background: #111113;
        border: 1px solid #1F1F23;
        border-radius: 8px;
        padding: 20px 24px;
        margin: 24px 0;
    }

    .scan-info-line {
        font-size: 14px;
        color: #D1D5DB;
        line-height: 1.8;
        margin-bottom: 6px;
    }

    .scan-info-line .label {
        color: #6B7280;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 0.08em;
        font-weight: 500;
        display: inline-block;
        width: 140px;
    }

    .scan-info-line .value {
        color: #E5E7EB;
        font-weight: 600;
    }

    .scan-summary {
        font-size: 14px;
        color: #9CA3AF;
        line-height: 1.5;
        padding-top: 12px;
        margin-top: 12px;
        border-top: 1px solid #1F1F23;
    }

    .scan-warning {
        font-size: 13px;
        color: #D97706;
        padding: 8px 12px;
        background: rgba(217, 119, 6, 0.08);
        border-left: 3px solid #D97706;
        border-radius: 4px;
        margin-top: 12px;
    }

    /* === Link-Style Button for Caselle Territory === */
    #caselle-link-label {
        margin-bottom: -8px;
    }

    /* Target the button that comes after the caselle-link-label */
    #caselle-link-label + div button,
    div:has(#caselle-link-label) + div button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #4F6AFF !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 0 4px !important;
        height: auto !important;
        min-height: 0 !important;
        text-decoration: none !important;
    }

    #caselle-link-label + div button:hover,
    div:has(#caselle-link-label) + div button:hover {
        background: transparent !important;
        color: #6B7FFF !important;
        text-decoration: underline !important;
        border: none !important;
        box-shadow: none !important;
    }

    #caselle-link-label + div button:focus,
    div:has(#caselle-link-label) + div button:focus {
        background: transparent !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* === Empty State === */
    .empty-state {
        text-align: center;
        padding: 80px 40px;
        color: #6B7280;
    }

    .empty-state h3 {
        font-size: 18px;
        font-weight: 600;
        color: #9CA3AF;
        margin-bottom: 8px;
    }

    .empty-state p {
        font-size: 14px;
        line-height: 1.6;
        max-width: 500px;
        margin: 0 auto;
    }

    /* === Lead Cards (CRM Style) === */
    .lead-card {
        background: #111113;
        border: 1px solid #1F1F23;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 12px;
        position: relative;
        transition: border-color 0.2s ease;
    }

    .lead-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 3px;
        border-radius: 8px 0 0 8px;
    }

    .lead-card.hot::before { background: #DC3545; }
    .lead-card.warm::before { background: #D97706; }
    .lead-card.cold::before { background: #3B82F6; }

    .lead-card:hover {
        border-color: #2F2F33;
    }

    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 14px;
    }

    .card-title {
        font-size: 17px;
        font-weight: 600;
        color: #E5E7EB;
        line-height: 1.3;
    }

    .card-meta {
        font-size: 13px;
        color: #6B7280;
        margin-top: 4px;
        line-height: 1.4;
    }

    .lead-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .lead-badge::before {
        content: "";
        width: 6px;
        height: 6px;
        border-radius: 50%;
    }

    .lead-badge.hot { color: #DC3545; background: rgba(220, 53, 69, 0.08); }
    .lead-badge.hot::before { background: #DC3545; }

    .lead-badge.warm { color: #D97706; background: rgba(217, 119, 6, 0.08); }
    .lead-badge.warm::before { background: #D97706; }

    .lead-badge.cold { color: #3B82F6; background: rgba(59, 130, 246, 0.08); }
    .lead-badge.cold::before { background: #3B82F6; }

    .card-score {
        font-size: 13px;
        color: #6B7280;
        margin-top: 6px;
        text-align: right;
    }

    .card-score .number {
        font-weight: 600;
        color: #9CA3AF;
    }

    .action-callout {
        background: #0F0F11;
        border-left: 3px solid #4F6AFF;
        border-radius: 4px;
        padding: 12px 16px;
        font-size: 14px;
        color: #D1D5DB;
        margin: 12px 0;
        line-height: 1.5;
    }

    .signal-tags {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        margin: 12px 0;
    }

    .signal-tag {
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 11px;
        background: #1A1A1F;
        color: #9CA3AF;
        border: 1px solid #1F1F23;
        font-weight: 500;
    }

    .source-link {
        display: inline-block;
        margin-top: 12px;
        color: #4F6AFF;
        text-decoration: none;
        font-size: 13px;
        font-weight: 500;
    }

    .source-link:hover {
        color: #6B7FFF;
        text-decoration: underline;
    }

    /* === Table View === */
    .results-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin: 20px 0;
    }

    .results-table thead {
        background: #111113;
        border: 1px solid #1F1F23;
    }

    .results-table th {
        padding: 12px 16px;
        text-align: left;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9CA3AF;
        border-bottom: 1px solid #1F1F23;
    }

    .results-table tbody tr {
        background: #111113;
        border: 1px solid #1F1F23;
        border-top: none;
    }

    .results-table tbody tr:hover {
        background: #1A1A1F;
    }

    .results-table td {
        padding: 14px 16px;
        font-size: 14px;
        color: #D1D5DB;
        border-bottom: 1px solid #1F1F23;
    }

    .results-table td:first-child {
        font-weight: 600;
    }

    /* === Phase Indicators === */
    .phase {
        padding: 10px 16px;
        border-radius: 6px;
        margin: 8px 0;
        font-size: 14px;
        font-weight: 500;
    }

    .phase.active {
        background: rgba(79, 106, 255, 0.08);
        color: #4F6AFF;
        border: 1px solid rgba(79, 106, 255, 0.2);
    }

    .phase.done {
        background: rgba(34, 197, 94, 0.08);
        color: #22C55E;
        border: 1px solid rgba(34, 197, 94, 0.2);
    }

    .phase.waiting {
        background: rgba(156, 163, 175, 0.05);
        color: #6B7280;
        border: 1px solid #1F1F23;
    }

    /* === Streamlit Component Overrides === */
    .stButton > button {
        background: #4F6AFF;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 10px 20px;
        font-weight: 600;
        font-size: 14px;
        letter-spacing: 0.01em;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background: #6B7FFF;
        border: none;
    }

    .stButton > button[kind="primary"] {
        background: #4F6AFF;
    }

    .stButton > button[kind="primary"]:hover {
        background: #6B7FFF;
    }

    /* Normal-sized button (not full-width by default) */
    .stButton {
        display: inline-block;
    }

    .stTextInput input {
        background: #111113;
        border: 1px solid #1F1F23;
        border-radius: 6px;
        color: #E5E7EB;
        font-size: 14px;
        padding: 8px 12px;
    }

    .stTextInput input:focus {
        border-color: #4F6AFF;
        box-shadow: 0 0 0 1px #4F6AFF;
    }

    .stSelectbox [data-baseweb="select"] {
        background: #111113;
        border-radius: 6px;
    }

    .stMultiSelect [data-baseweb="select"] {
        background: #111113;
        border-radius: 6px;
    }

    .stSlider {
        padding: 8px 0;
    }

    /* === Hide Streamlit Branding === */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
    header { visibility: hidden; }

    /* === Dividers === */
    hr {
        border: none;
        border-top: 1px solid #1F1F23;
        margin: 24px 0;
    }

    /* === Results Header === */
    .results-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 32px 0 16px 0;
    }

    .results-title {
        font-size: 18px;
        font-weight: 600;
        color: #E5E7EB;
    }
</style>
""", unsafe_allow_html=True)


def render_header():
    """Render app header."""
    st.markdown(
        '<div class="main-header">Municipal <span class="accent">Intel</span></div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="sub-header">Government ERP lead intelligence platform — Scan municipal meeting minutes for sales signals</div>',
        unsafe_allow_html=True
    )


def render_stats(results: list, total_docs: int, sources: int, munis: int):
    """Render stats summary."""
    hot = sum(1 for r in results if r.lead_type == "hot")
    warm = sum(1 for r in results if r.lead_type == "warm")
    cold = sum(1 for r in results if r.lead_type == "cold")

    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-box total">
            <div class="label">Total Leads</div>
            <div class="value">{len(results)}</div>
        </div>
        <div class="stat-box hot">
            <div class="label">Hot</div>
            <div class="value">{hot}</div>
        </div>
        <div class="stat-box warm">
            <div class="label">Warm</div>
            <div class="value">{warm}</div>
        </div>
        <div class="stat-box cold">
            <div class="label">Cold</div>
            <div class="value">{cold}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_lead_card(result):
    """Render a single lead card in CRM style."""
    pop_str = f" · Pop. {result.population:,}" if result.population else ""

    tags_html = "".join(
        f'<span class="signal-tag">{lbl}</span>'
        for lbl in result.signal_labels_found
    )

    st.markdown(f"""
    <div class="lead-card {result.lead_type}">
        <div class="card-header">
            <div>
                <div class="card-title">{result.municipality}, {result.state}</div>
                <div class="card-meta">{result.title} · {result.date}{pop_str}</div>
            </div>
            <div style="text-align: right;">
                <span class="lead-badge {result.lead_type}">{result.lead_type}</span>
                <div class="card-score">Score: <span class="number">{result.relevance_score}</span></div>
            </div>
        </div>
        <div class="action-callout">{result.recommended_action}</div>
        <div class="signal-tags">{tags_html}</div>
        <a class="source-link" href="{result.url}" target="_blank" rel="noopener">View source document</a>
    </div>
    """, unsafe_allow_html=True)


def render_table_view(results: list):
    """Render results as a table."""
    table_html = """
    <table class="results-table">
        <thead>
            <tr>
                <th>Municipality</th>
                <th>State</th>
                <th>Type</th>
                <th>Score</th>
                <th>Signals</th>
                <th>Document</th>
            </tr>
        </thead>
        <tbody>
    """

    for r in results:
        signals = ", ".join(r.signal_labels_found[:2])
        badge_class = r.lead_type
        table_html += f"""
            <tr>
                <td><strong>{r.municipality}</strong></td>
                <td>{r.state}</td>
                <td><span class="lead-badge {badge_class}">{r.lead_type}</span></td>
                <td>{r.relevance_score}</td>
                <td>{signals}</td>
                <td><a class="source-link" href="{r.url}" target="_blank">{r.title[:40]}...</a></td>
            </tr>
        """

    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)


def run_scan(selected_states: list, state_name: str, municipalities: list,
             max_cities: int, use_llm: bool):
    """Execute the full scan pipeline."""

    # Limit cities
    cities = municipalities[:max_cities]
    population_map = {m["name"]: m.get("population", 0) for m in cities}

    total_phases = 3
    progress = st.progress(0)
    status = st.empty()

    # Track timing for performance monitoring
    scan_start = time.time()
    phase_times = {}

    # ==========================================================
    # PHASE 1: Load Sources from Database (NEW ARCHITECTURE)
    # ==========================================================
    phase1_start = time.time()
    status.markdown('<div class="phase active">Phase 1/3 — Loading pre-discovered sources from database</div>', unsafe_allow_html=True)
    discovery_log = st.empty()

    # NEW: Load sources from database instead of probing
    db = SessionLocal()
    discovered_sources = []
    enriched_cities = []
    unenriched_cities = []
    failed_cities = []

    try:
        for i, muni in enumerate(cities):
            pct = int((i / len(cities)) * 33)
            progress.progress(pct)
            discovery_log.text(f"Loading sources for {muni['name']}, {muni.get('state', 'N/A')} ({i+1}/{len(cities)})")

            muni_id = muni.get("id")
            if not muni_id:
                failed_cities.append(muni["name"])
                continue

            # Check if city is enriched (has verified domain and sources)
            municipality = db.query(Municipality).filter_by(id=muni_id).first()
            if not municipality or municipality.domain_status != "verified":
                unenriched_cities.append(muni["name"])
                continue

            # Load sources from database
            sources = db.query(MunicipalSource).filter_by(municipality_id=muni_id).all()

            if not sources:
                unenriched_cities.append(muni["name"])
                continue

            # Convert MunicipalSource objects to DiscoveredSource objects (for compatibility)
            enriched_cities.append(muni["name"])
            for source in sources:
                discovered_source = DiscoveredSource(
                    municipality=muni["name"],
                    state=muni.get("state", ""),
                    url=source.url,
                    source_type=source.platform or source.source_type,
                    confidence=source.confidence,
                    population=muni.get("population", 0),
                )
                discovered_sources.append(discovered_source)

    finally:
        db.close()

    discovery_log.empty()

    # Count by source type
    meeting_count = sum(1 for s in discovered_sources if s.source_type in ["civicplus", "granicus", "html", "unknown", "boarddocs"])
    procurement_count = sum(1 for s in discovered_sources if s.source_type == "procurement")

    phase_times["Phase 1: Load Sources"] = time.time() - phase1_start

    # Show enrichment status
    if unenriched_cities:
        st.warning(f"⚠️ {len(unenriched_cities)} cities not enriched yet: {', '.join(unenriched_cities[:5])}{'...' if len(unenriched_cities) > 5 else ''}. Run enrichment first for better results.")

    status.markdown(f'<div class="phase done">Phase 1/3 — Loaded {len(discovered_sources)} sources from {len(enriched_cities)} cities ({meeting_count} meetings, {procurement_count} procurement) in {phase_times["Phase 1: Load Sources"]:.1f}s</div>', unsafe_allow_html=True)

    if not discovered_sources:
        st.warning("No meeting minutes sources could be discovered. The municipalities in this state may not have publicly accessible meeting minutes, or their websites may use non-standard formats.")
        progress.progress(100)
        return [], 0, 0, 0

    # ==========================================================
    # PHASE 2: Scraping
    # ==========================================================
    phase2_start = time.time()
    status2 = st.empty()
    status2.markdown('<div class="phase active">Phase 2/3 — Scraping meeting documents</div>', unsafe_allow_html=True)
    scrape_log = st.empty()

    # Optimized for speed: 0.5s delay, 8s timeout
    scraper = MunicipalScraper(delay=0.5, timeout=8, max_docs=10)
    all_docs = []

    for i, source in enumerate(discovered_sources):
        pct = 33 + int((i / len(discovered_sources)) * 33)
        progress.progress(pct)
        scrape_log.text(f"Scraping {source.municipality}, {source.state} ({i+1}/{len(discovered_sources)})")

        try:
            docs = scraper.scrape_source(source)
            all_docs.extend(docs)
        except Exception as e:
            logger.error(f"Scraping error for {source.url}: {e}")

    scrape_log.empty()
    phase_times["Phase 2: Scraping"] = time.time() - phase2_start
    status2.markdown(f'<div class="phase done">Phase 2/3 — Scraped {len(all_docs)} documents in {phase_times["Phase 2: Scraping"]:.1f}s</div>', unsafe_allow_html=True)

    if not all_docs:
        st.warning("Documents were found but could not be extracted. This often happens with JavaScript-heavy sites or non-standard PDF formats.")
        progress.progress(100)
        return [], 0, len(discovered_sources), 0

    # ==========================================================
    # PHASE 3: Analysis
    # ==========================================================
    phase3_start = time.time()
    status3 = st.empty()
    status3.markdown('<div class="phase active">Phase 3/3 — Analyzing for lead signals</div>', unsafe_allow_html=True)

    # Build a mapping of source URLs to source types
    source_type_map = {s.url: s.source_type for s in discovered_sources}

    analyzer = DocumentAnalyzer(use_llm=use_llm)
    results = []

    for i, doc in enumerate(all_docs):
        pct = 66 + int((i / len(all_docs)) * 34)
        progress.progress(min(pct, 99))

        pop = population_map.get(doc.municipality, 0)

        # Determine source type from the document's source URL
        source_type = source_type_map.get(doc.url, "meeting_minutes")
        if source_type in ["civicplus", "granicus", "html", "unknown"]:
            source_type = "meeting_minutes"

        result = analyzer.analyze_document(doc, population=pop, min_score=10, source_type=source_type)
        if result:
            results.append(result)

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    progress.progress(100)

    phase_times["Phase 3: Analysis"] = time.time() - phase3_start
    total_time = time.time() - scan_start

    hot = sum(1 for r in results if r.lead_type == "hot")
    warm = sum(1 for r in results if r.lead_type == "warm")
    cold = sum(1 for r in results if r.lead_type == "cold")
    status3.markdown(f'<div class="phase done">Phase 3/3 — Found {len(results)} leads ({hot} hot, {warm} warm, {cold} cold) in {phase_times["Phase 3: Analysis"]:.1f}s</div>', unsafe_allow_html=True)

    # Print timing summary
    timing_summary = st.empty()
    mins, secs = divmod(int(total_time), 60)
    timing_details = " | ".join([f"{phase}: {time:.1f}s" for phase, time in phase_times.items()])
    timing_summary.markdown(f'<div style="background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 14px;"><strong>⏱️ Total Time:</strong> {mins}m {secs}s | {timing_details}</div>', unsafe_allow_html=True)
    logger.info(f"Scan completed in {mins}m {secs}s | {timing_details}")

    return results, len(all_docs), len(discovered_sources), len(failed_cities)


def main():
    """Main application."""

    db = load_municipalities()
    state_options = get_state_options(db)

    # --- Sidebar ---
    with st.sidebar:
        st.markdown("### Scan Settings")

        # State selection (always multiselect)
        selected_states = st.multiselect(
            "Select States",
            options=list(state_options.keys()),
            format_func=lambda x: state_options[x],
            default=["UT"] if "UT" in state_options else [list(state_options.keys())[0]],
        )

        # Caselle Territory quick-select (subtle link style)
        st.markdown('<div id="caselle-link-label" style="margin-top: 8px; font-size: 13px; color: #6B7280;">Quick select:</div>', unsafe_allow_html=True)

        # Use a styled button that looks like a text link (key will be targeted in CSS)
        if st.button("Caselle Territory", key="caselle_territory_link", type="secondary"):
            available_territory = [s for s in CASELLE_TERRITORY if s in state_options]
            selected_states = available_territory
            st.rerun()

        # Combine municipalities from all selected states
        munis = []
        if selected_states:
            state_names_list = [db["states"][s]["name"] for s in selected_states]
            state_name = ", ".join(state_names_list)
            for state_abbr in selected_states:
                state_munis = db["states"][state_abbr].get("municipalities", [])
                for m in state_munis:
                    m_copy = m.copy()
                    m_copy["state"] = state_abbr
                    munis.append(m_copy)
        else:
            state_name = "None"
            state_names_list = []

        # Filters Section (Collapsible)
        with st.expander("Filters", expanded=False):
            st.markdown("**Population Tier**")

            # Population tier presets
            tier_options = list(POPULATION_TIERS.keys())
            preset = st.radio(
                "Target Market Segment",
                tier_options,
                index=2,  # Default to "Small-Mid (10,000 – 25,000)"
                label_visibility="collapsed"
            )

            # Get tier values
            tier_min, tier_max = POPULATION_TIERS[preset]

            # Custom min/max inputs (only enabled for Custom tier)
            if preset == "Custom":
                col_min, col_max = st.columns(2)
                with col_min:
                    min_population = st.number_input(
                        "Min. Population",
                        min_value=0,
                        max_value=10000000,
                        value=tier_min,
                        step=1000,
                    )
                with col_max:
                    max_population = st.number_input(
                        "Max. Population",
                        min_value=0,
                        max_value=10000000,
                        value=tier_max,
                        step=1000,
                    )
            else:
                min_population = tier_min
                max_population = tier_max

            st.markdown("**Sorting**")
            sort_by = st.selectbox(
                "Sort Cities By",
                ["Population (Smallest First)", "Population (Largest First)", "Name (A-Z)"],
                label_visibility="collapsed"
            )

            st.markdown("**City Search**")
            city_search = st.text_input(
                "Find specific city",
                placeholder="Type city name",
                label_visibility="collapsed"
            )

        # Advanced Section (Collapsible)
        with st.expander("Advanced", expanded=False):
            use_llm = st.toggle(
                "AI-Enhanced Analysis",
                value=False,
            )

    # --- Main Content ---
    render_header()

    # Show empty state if no states selected
    if not selected_states:
        st.markdown("""
        <div class="empty-state">
            <h3>No states selected</h3>
            <p>Select one or more states from the sidebar to begin scanning for leads.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # Filter municipalities by population range
    filtered_munis = [
        m for m in munis
        if min_population <= m.get("population", 0) <= max_population
    ]

    # Apply city search filter
    if city_search and city_search.strip():
        search_term = city_search.strip().lower()
        filtered_munis = [
            m for m in filtered_munis
            if search_term in m.get("name", "").lower()
        ]

    if not filtered_munis:
        if city_search and city_search.strip():
            st.warning(f"No cities matching '{city_search}' found in selected state(s).")
        else:
            st.warning(f"No municipalities in {state_name} with population between {min_population:,} and {max_population:,}.")
        return

    # Sort municipalities
    if sort_by == "Population (Smallest First)":
        filtered_munis.sort(key=lambda m: m.get("population", 0))
    elif sort_by == "Population (Largest First)":
        filtered_munis.sort(key=lambda m: m.get("population", 0), reverse=True)
    else:  # Name (A-Z)
        filtered_munis.sort(key=lambda m: m.get("name", ""))

    # Apply 200-city hard limit to prevent accidental hour-long scans
    MAX_CITIES_PER_SCAN = 200

    if len(filtered_munis) > MAX_CITIES_PER_SCAN:
        st.warning(f"⚠️ **200-city limit reached**. Showing first {MAX_CITIES_PER_SCAN} of {len(filtered_munis):,} cities. Narrow your filters to scan more specifically.")
        cities_to_scan = filtered_munis[:MAX_CITIES_PER_SCAN]
    else:
        cities_to_scan = filtered_munis

    num_cities = len(cities_to_scan)

    # Calculate estimated time (~4 seconds per city)
    estimated_seconds = num_cities * 4
    if estimated_seconds < 60:
        estimated_time = f"~{estimated_seconds} seconds"
    else:
        estimated_minutes = estimated_seconds // 60
        estimated_time = f"~{estimated_minutes} minute{'s' if estimated_minutes != 1 else ''}"

    # Determine population range string based on tier
    if preset == "All Cities":
        # For "All Cities", show actual min-max of matched cities
        if cities_to_scan:
            pop_values = [m.get("population", 0) for m in cities_to_scan]
            actual_min = min(pop_values) if pop_values else 0
            actual_max = max(pop_values) if pop_values else 0
            if actual_min == actual_max:
                pop_range_str = f"{actual_min:,}"
            else:
                pop_range_str = f"{actual_min:,} – {actual_max:,}"
        else:
            pop_range_str = "N/A"
        tier_display = "All Cities"
    elif preset == "Custom":
        # For Custom, show user-entered values
        pop_range_str = f"{min_population:,} – {max_population:,}"
        tier_display = "Custom"
    elif "under" in preset:
        # Micro (under 2,500)
        pop_range_str = f"0 – {tier_max:,}"
        tier_display = preset.split(" (")[0]  # "Micro"
    elif "+" in preset:
        # Large (150,000+)
        pop_range_str = f"{tier_min:,}+"
        tier_display = preset.split(" (")[0]  # "Large"
    else:
        # All other tiers with explicit ranges
        pop_range_str = f"{tier_min:,} – {tier_max:,}"
        tier_display = preset.split(" (")[0]  # e.g., "Small-Mid"

    # Pre-scan briefing (simplified, accurate)
    scan_briefing_html = f"""
    <div class="pre-scan-briefing">
        <div class="scan-info-line">
            <span class="label">STATES:</span>
            <span class="value">{state_name}</span>
        </div>
        <div class="scan-info-line">
            <span class="label">POPULATION:</span>
            <span class="value">{tier_display} ({pop_range_str})</span>
        </div>
        <div class="scan-info-line">
            <span class="label">CITIES MATCHED:</span>
            <span class="value">{num_cities}</span>
        </div>
        <div class="scan-info-line">
            <span class="label">ESTIMATED TIME:</span>
            <span class="value">{estimated_time}</span>
        </div>
        <div class="scan-summary">
            Scanning {num_cities} cities across {len(selected_states)} state{'s' if len(selected_states) != 1 else ''}
        </div>
    """

    # Add warning for large scans
    if estimated_seconds > 600:  # > 10 minutes
        scan_briefing_html += """
        <div class="scan-warning">
            Large scan — consider narrowing filters or scanning one state at a time
        </div>
        """

    scan_briefing_html += "</div>"
    st.markdown(scan_briefing_html, unsafe_allow_html=True)

    # Run button (normal-sized, not full-width)
    if st.button("Run Scan", type="primary"):
        with st.spinner(""):
            results, total_docs, sources_found, failed = run_scan(
                selected_states=selected_states,
                state_name=state_name,
                municipalities=cities_to_scan,
                max_cities=num_cities,
                use_llm=use_llm,
            )

        st.markdown("---")

        if results:
            # Stats
            render_stats(results, total_docs, sources_found, len(cities_to_scan))

            # Generate downloadable reports
            reporter = ReportGenerator(str(REPORT_DIR))
            state_abbr_str = ", ".join(selected_states)
            html_path = reporter.generate_html(
                results, state_name, state_abbr_str,
                total_docs, len(cities_to_scan), sources_found,
            )
            json_path = reporter.generate_json(
                results, state_name, state_abbr_str,
                total_docs, len(cities_to_scan), sources_found,
            )
            csv_path = reporter.generate_csv(
                results, state_name, state_abbr_str,
            )

            # Results header with export buttons
            st.markdown('<div class="results-header">', unsafe_allow_html=True)
            col_title, col_exports = st.columns([2, 1])
            with col_title:
                st.markdown('<div class="results-title">Lead Results</div>', unsafe_allow_html=True)
            with col_exports:
                export_col1, export_col2, export_col3 = st.columns(3)
                with export_col1:
                    with open(html_path, "r") as f:
                        st.download_button(
                            "HTML",
                            f.read(),
                            file_name=Path(html_path).name,
                            mime="text/html",
                            use_container_width=True,
                        )
                with export_col2:
                    with open(json_path, "r") as f:
                        st.download_button(
                            "JSON",
                            f.read(),
                            file_name=Path(json_path).name,
                            mime="application/json",
                            use_container_width=True,
                        )
                with export_col3:
                    with open(csv_path, "r") as f:
                        st.download_button(
                            "CSV",
                            f.read(),
                            file_name=Path(csv_path).name,
                            mime="text/csv",
                            use_container_width=True,
                        )
            st.markdown('</div>', unsafe_allow_html=True)

            # View mode toggle
            view_mode = st.radio(
                "View Mode",
                ["Cards", "Table"],
                horizontal=True,
                label_visibility="collapsed",
            )

            # Filter controls
            col_filter, col_spacer = st.columns([1, 3])
            with col_filter:
                filter_type = st.radio(
                    "Filter",
                    ["All", "Hot", "Warm", "Cold"],
                    horizontal=True,
                    label_visibility="collapsed",
                )

            type_map = {"All": None, "Hot": "hot", "Warm": "warm", "Cold": "cold"}
            active_filter = type_map[filter_type]

            # Filter results
            filtered_results = [
                r for r in results
                if not active_filter or r.lead_type == active_filter
            ]

            # Render based on view mode
            if view_mode == "Table":
                render_table_view(filtered_results)
            else:
                for result in filtered_results:
                    render_lead_card(result)

                    # Expandable context
                    with st.expander(f"View match contexts ({result.match_count} signals)"):
                        seen = set()
                        for m in result.signal_matches:
                            if m.keyword not in seen:
                                seen.add(m.keyword)
                                st.markdown(f"**{m.keyword}** ({m.signal_label})")
                                st.markdown(f"> {m.context}")
                                st.markdown("---")

                    if result.llm_analysis:
                        with st.expander("AI Sales Brief"):
                            st.markdown(result.llm_analysis)

        else:
            st.markdown("""
            <div class="empty-state">
                <h3>No signals detected</h3>
                <p>None of the documents analyzed contained ERP-related signals. This is common — most meeting minutes don't discuss software.</p>
            </div>
            """, unsafe_allow_html=True)

        if failed:
            with st.expander(f"{failed} cities with no discoverable sources"):
                st.write("These cities either don't have publicly posted meeting minutes or use non-standard website platforms.")


if __name__ == "__main__":
    main()
