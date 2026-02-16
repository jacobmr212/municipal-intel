"""
Municipal Intel — Government ERP Lead Intelligence Platform
Main Streamlit application.
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime

import streamlit as st

from src.discovery import SourceDiscovery
from src.scraper import MunicipalScraper
from src.analyzer import DocumentAnalyzer
from src.reporter import ReportGenerator

# --- Page Config ---
st.set_page_config(
    page_title="Municipal Intel",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Data ---
DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)


@st.cache_data
def load_municipalities():
    """Load the municipality database."""
    db_path = DATA_DIR / "municipalities.json"
    if not db_path.exists():
        st.error("Municipality database not found. Ensure data/municipalities.json exists.")
        st.stop()
    with open(db_path) as f:
        return json.load(f)


def get_state_options(db: dict) -> dict:
    """Build state selection options."""
    states = db.get("states", {})
    options = {}
    for abbr, info in sorted(states.items(), key=lambda x: x[1]["name"]):
        count = len(info.get("municipalities", []))
        options[abbr] = f"{info['name']} ({count} cities)"
    return options


# --- Custom CSS ---
st.markdown("""
<style>
    /* Global */
    .stApp { background-color: #0b0d11; }
    section[data-testid="stSidebar"] { background-color: #111520; }

    /* Header */
    .main-header {
        font-size: 36px; font-weight: 800; letter-spacing: -1px;
        background: linear-gradient(135deg, #5e8aff 0%, #a78bfa 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
    }
    .sub-header { color: #7a809e; font-size: 15px; margin-bottom: 24px; }

    /* Stat boxes */
    .stat-row { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
    .stat-box {
        flex: 1; min-width: 130px; background: #141720; border: 1px solid #2a3050;
        border-radius: 12px; padding: 16px 18px;
    }
    .stat-box .label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #7a809e; }
    .stat-box .value { font-size: 30px; font-weight: 800; margin-top: 2px; }
    .stat-box.hot .value { color: #ff4466; }
    .stat-box.warm .value { color: #ffb040; }
    .stat-box.cold .value { color: #40b8ff; }
    .stat-box.total .value { color: #5e8aff; }

    /* Lead cards */
    .lead-card {
        background: #141720; border: 1px solid #2a3050; border-radius: 12px;
        padding: 20px; margin-bottom: 12px; border-left: 4px solid transparent;
    }
    .lead-card.hot { border-left-color: #ff4466; }
    .lead-card.warm { border-left-color: #ffb040; }
    .lead-card.cold { border-left-color: #40b8ff; }

    /* Phase indicators */
    .phase { padding: 8px 16px; border-radius: 8px; margin: 6px 0; font-size: 14px; }
    .phase.active { background: rgba(94,138,255,.12); color: #5e8aff; }
    .phase.done { background: rgba(76,217,123,.12); color: #4cd97b; }
    .phase.waiting { background: rgba(122,128,158,.08); color: #7a809e; }

    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)


def render_header():
    """Render app header."""
    st.markdown('<div class="main-header">🏛️ Municipal Intel</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Government ERP Lead Intelligence — Scan municipal meeting minutes for sales signals</div>', unsafe_allow_html=True)


def render_stats(results: list, total_docs: int, sources: int, munis: int):
    """Render stats summary."""
    hot = sum(1 for r in results if r.lead_type == "hot")
    warm = sum(1 for r in results if r.lead_type == "warm")
    cold = sum(1 for r in results if r.lead_type == "cold")

    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-box total"><div class="label">Total Leads</div><div class="value">{len(results)}</div></div>
        <div class="stat-box hot"><div class="label">Hot</div><div class="value">{hot}</div></div>
        <div class="stat-box warm"><div class="label">Warm</div><div class="value">{warm}</div></div>
        <div class="stat-box cold"><div class="label">Cold</div><div class="value">{cold}</div></div>
    </div>
    """, unsafe_allow_html=True)


def render_lead_card(result):
    """Render a single lead card."""
    badge_colors = {"hot": "#ff4466", "warm": "#ffb040", "cold": "#40b8ff"}
    badge_bg = {"hot": "rgba(255,68,102,.12)", "warm": "rgba(255,176,64,.12)", "cold": "rgba(64,184,255,.12)"}
    color = badge_colors.get(result.lead_type, "#7a809e")
    bg = badge_bg.get(result.lead_type, "rgba(122,128,158,.08)")

    pop_str = f" · Pop. {result.population:,}" if result.population else ""

    tags_html = " ".join(
        f'<span style="display:inline-block;padding:2px 8px;border-radius:5px;font-size:11px;background:#1c2030;color:#7a809e;margin-right:4px">{lbl}</span>'
        for lbl in result.signal_labels_found
    )

    st.markdown(f"""
    <div class="lead-card {result.lead_type}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
                <div style="font-size:17px;font-weight:600">{result.municipality}, {result.state}</div>
                <div style="font-size:12px;color:#7a809e;margin-top:2px">{result.title} · {result.date}{pop_str}</div>
            </div>
            <div style="text-align:right">
                <span style="display:inline-block;padding:3px 10px;border-radius:50px;font-size:11px;font-weight:700;text-transform:uppercase;background:{bg};color:{color}">{result.lead_type}</span>
                <div style="font-size:12px;color:#7a809e;margin-top:4px">Score: {result.relevance_score}</div>
            </div>
        </div>
        <div style="width:100%;height:4px;background:#252a3a;border-radius:2px;margin:10px 0;overflow:hidden">
            <div style="height:100%;width:{result.relevance_score}%;background:{color};border-radius:2px"></div>
        </div>
        <div style="background:#1c2030;border-radius:8px;padding:10px 14px;font-size:13px;border-left:3px solid #5e8aff;margin:8px 0">
            <strong style="color:#5e8aff">→</strong> {result.recommended_action}
        </div>
        <div style="margin:8px 0">{tags_html}</div>
        <a href="{result.url}" target="_blank" style="color:#5e8aff;font-size:12px;text-decoration:none">View source →</a>
    </div>
    """, unsafe_allow_html=True)


def run_scan(state_abbr: str, state_name: str, municipalities: list,
             max_cities: int, use_llm: bool):
    """Execute the full scan pipeline."""

    # Limit cities
    cities = municipalities[:max_cities]
    population_map = {m["name"]: m.get("population", 0) for m in cities}

    total_phases = 3
    progress = st.progress(0)
    status = st.empty()

    # ==========================================================
    # PHASE 1: Source Discovery
    # ==========================================================
    status.markdown('<div class="phase active">🔍 Phase 1/3 — Discovering meeting minutes sources...</div>', unsafe_allow_html=True)
    discovery_log = st.empty()

    discovery = SourceDiscovery(request_delay=1.0, timeout=12)
    discovered_sources = []
    failed_cities = []

    for i, muni in enumerate(cities):
        pct = int((i / len(cities)) * 33)
        progress.progress(pct)
        discovery_log.text(f"  Probing {muni['name']}, {state_abbr} ({i+1}/{len(cities)})...")

        sources = discovery.discover_municipality(
            name=muni["name"],
            state=state_abbr,
            domain=muni.get("domain", ""),
            population=muni.get("population", 0),
        )
        if sources:
            discovered_sources.extend(sources)
        else:
            failed_cities.append(muni["name"])

    discovery_log.empty()
    status.markdown(f'<div class="phase done">✅ Phase 1/3 — Found {len(discovered_sources)} sources across {len(cities) - len(failed_cities)} municipalities</div>', unsafe_allow_html=True)

    if not discovered_sources:
        st.warning("No meeting minutes sources could be discovered. The municipalities in this state may not have publicly accessible meeting minutes, or their websites may use non-standard formats.")
        progress.progress(100)
        return [], 0, 0, 0

    # ==========================================================
    # PHASE 2: Scraping
    # ==========================================================
    status2 = st.empty()
    status2.markdown('<div class="phase active">📄 Phase 2/3 — Scraping meeting documents...</div>', unsafe_allow_html=True)
    scrape_log = st.empty()

    scraper = MunicipalScraper(delay=1.5, timeout=20, max_docs=10)
    all_docs = []

    for i, source in enumerate(discovered_sources):
        pct = 33 + int((i / len(discovered_sources)) * 33)
        progress.progress(pct)
        scrape_log.text(f"  Scraping {source.municipality}, {source.state} ({i+1}/{len(discovered_sources)})...")

        try:
            docs = scraper.scrape_source(source)
            all_docs.extend(docs)
        except Exception as e:
            logger.error(f"Scraping error for {source.url}: {e}")

    scrape_log.empty()
    status2.markdown(f'<div class="phase done">✅ Phase 2/3 — Scraped {len(all_docs)} documents</div>', unsafe_allow_html=True)

    if not all_docs:
        st.warning("Documents were found but could not be extracted. This often happens with JavaScript-heavy sites or non-standard PDF formats.")
        progress.progress(100)
        return [], 0, len(discovered_sources), 0

    # ==========================================================
    # PHASE 3: Analysis
    # ==========================================================
    status3 = st.empty()
    status3.markdown('<div class="phase active">🧠 Phase 3/3 — Analyzing for lead signals...</div>', unsafe_allow_html=True)

    analyzer = DocumentAnalyzer(use_llm=use_llm)
    results = []

    for i, doc in enumerate(all_docs):
        pct = 66 + int((i / len(all_docs)) * 34)
        progress.progress(min(pct, 99))

        pop = population_map.get(doc.municipality, 0)
        result = analyzer.analyze_document(doc, population=pop, min_score=10)
        if result:
            results.append(result)

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    progress.progress(100)

    hot = sum(1 for r in results if r.lead_type == "hot")
    warm = sum(1 for r in results if r.lead_type == "warm")
    cold = sum(1 for r in results if r.lead_type == "cold")
    status3.markdown(f'<div class="phase done">✅ Phase 3/3 — Found {len(results)} leads (🔥{hot} 🟡{warm} 🔵{cold})</div>', unsafe_allow_html=True)

    return results, len(all_docs), len(discovered_sources), len(failed_cities)


def main():
    """Main application."""

    db = load_municipalities()
    state_options = get_state_options(db)

    # --- Sidebar ---
    with st.sidebar:
        st.markdown("### ⚙️ Scan Settings")
        st.markdown("---")

        selected_state = st.selectbox(
            "Select State",
            options=list(state_options.keys()),
            format_func=lambda x: state_options[x],
            index=list(state_options.keys()).index("UT") if "UT" in state_options else 0,
        )

        state_info = db["states"][selected_state]
        state_name = state_info["name"]
        munis = state_info.get("municipalities", [])

        max_cities = st.slider(
            "Max Cities to Scan",
            min_value=1,
            max_value=min(len(munis), 50),
            value=min(len(munis), 10),
            help="More cities = more comprehensive but slower scan",
        )

        st.markdown("---")
        st.markdown("### 🔬 Advanced")

        use_llm = st.toggle(
            "AI-Enhanced Analysis",
            value=False,
            help="Use Claude to generate contextual sales briefs for hot/warm leads. Requires ANTHROPIC_API_KEY environment variable.",
        )

        min_population = st.number_input(
            "Min. Population",
            min_value=0,
            max_value=100000,
            value=0,
            step=1000,
            help="Filter out cities below this population",
        )

        st.markdown("---")
        st.markdown("### 📊 About")
        st.markdown(
            "Municipal Intel scans public meeting minutes for signals "
            "related to ERP software procurement, vendor evaluations, "
            "system pain points, and budget discussions."
        )
        st.markdown(
            "**Signal Categories:**\n"
            "- 🔴 Direct mentions (Caselle)\n"
            "- 🟠 Competitor mentions\n"
            "- 🟡 ERP/software signals\n"
            "- 🔵 Budget/procurement\n"
            "- ⚪ System pain points"
        )

    # --- Main Content ---
    render_header()

    # Filter municipalities by population
    filtered_munis = [m for m in munis if m.get("population", 0) >= min_population]
    if not filtered_munis:
        st.warning(f"No municipalities in {state_name} meet the minimum population filter of {min_population:,}.")
        return

    # Info bar
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("State", state_name)
    with col2:
        st.metric("Cities Available", len(filtered_munis))
    with col3:
        st.metric("Will Scan", min(max_cities, len(filtered_munis)))

    st.markdown("---")

    # Run button
    if st.button("🚀 Run Intelligence Scan", type="primary", use_container_width=True):
        cities_to_scan = filtered_munis[:max_cities]

        with st.spinner(""):
            results, total_docs, sources_found, failed = run_scan(
                state_abbr=selected_state,
                state_name=state_name,
                municipalities=cities_to_scan,
                max_cities=max_cities,
                use_llm=use_llm,
            )

        st.markdown("---")

        if results:
            # Stats
            render_stats(results, total_docs, sources_found, len(cities_to_scan))

            # Generate downloadable reports
            reporter = ReportGenerator(str(REPORT_DIR))
            html_path = reporter.generate_html(
                results, state_name, selected_state,
                total_docs, len(cities_to_scan), sources_found,
            )
            json_path = reporter.generate_json(
                results, state_name, selected_state,
                total_docs, len(cities_to_scan), sources_found,
            )

            # Download buttons
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                with open(html_path, "r") as f:
                    st.download_button(
                        "📥 Download HTML Report",
                        f.read(),
                        file_name=Path(html_path).name,
                        mime="text/html",
                        use_container_width=True,
                    )
            with col_dl2:
                with open(json_path, "r") as f:
                    st.download_button(
                        "📥 Download JSON Data",
                        f.read(),
                        file_name=Path(json_path).name,
                        mime="application/json",
                        use_container_width=True,
                    )

            st.markdown("---")
            st.markdown("### 📋 Lead Details")

            # Filter tabs
            filter_type = st.radio(
                "Filter",
                ["All", "🔥 Hot", "🟡 Warm", "🔵 Cold"],
                horizontal=True,
                label_visibility="collapsed",
            )

            type_map = {"All": None, "🔥 Hot": "hot", "🟡 Warm": "warm", "🔵 Cold": "cold"}
            active_filter = type_map[filter_type]

            for result in results:
                if active_filter and result.lead_type != active_filter:
                    continue
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
                    with st.expander("🤖 AI Sales Brief"):
                        st.markdown(result.llm_analysis)

        else:
            st.info(
                f"No ERP-related signals were found in the meeting documents scanned for {state_name}. "
                "This could mean the municipalities' documents aren't publicly accessible in standard formats, "
                "or there simply weren't relevant discussions in recent documents."
            )

        if failed:
            with st.expander(f"⚠️ {failed} cities with no discoverable sources"):
                st.write("These cities either don't have publicly posted meeting minutes or use non-standard website platforms.")


if __name__ == "__main__":
    main()
