"""
Municipal Intel - Admin Page
Manage database enrichment and monitor coverage statistics.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import func

from src.database import SessionLocal, Municipality, MunicipalSource
from src.enrichment import EnrichmentEngine

# Page config
st.set_page_config(
    page_title="Admin - Municipal Intel",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ Admin Dashboard")
st.markdown("Manage database enrichment and monitor coverage statistics")

# Create tabs
tab_overview, tab_states, tab_enrich = st.tabs(["📊 Overview", "🗺️ States", "▶️ Run Enrichment"])

# --- TAB 1: OVERVIEW ---
with tab_overview:
    st.header("Database Overview")

    db = SessionLocal()
    try:
        # Overall statistics
        total_cities = db.query(Municipality).count()
        verified_cities = db.query(Municipality).filter_by(domain_status="verified").count()
        unverified_cities = db.query(Municipality).filter_by(domain_status="unverified").count()
        dead_cities = db.query(Municipality).filter_by(domain_status="dead").count()
        total_sources = db.query(MunicipalSource).count()

        # Display metrics
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Total Cities", f"{total_cities:,}")

        with col2:
            st.metric(
                "Verified",
                f"{verified_cities:,}",
                delta=f"{verified_cities/total_cities*100:.1f}%" if total_cities > 0 else "0%"
            )

        with col3:
            st.metric(
                "Unverified",
                f"{unverified_cities:,}",
                delta=f"{unverified_cities/total_cities*100:.1f}%" if total_cities > 0 else "0%",
                delta_color="inverse"
            )

        with col4:
            st.metric("Dead Domains", f"{dead_cities:,}")

        with col5:
            st.metric("Sources Discovered", f"{total_sources:,}")

        # Progress bar
        st.markdown("### Enrichment Progress")
        if total_cities > 0:
            progress = verified_cities / total_cities
            st.progress(progress)
            st.caption(f"{verified_cities:,} of {total_cities:,} cities enriched ({progress*100:.1f}%)")

        # Source type breakdown
        st.markdown("### Source Discovery Breakdown")
        source_stats = db.query(
            MunicipalSource.source_type,
            func.count(MunicipalSource.id).label("count")
        ).group_by(MunicipalSource.source_type).all()

        if source_stats:
            source_df = pd.DataFrame(source_stats, columns=["Source Type", "Count"])
            col1, col2 = st.columns([2, 1])
            with col1:
                st.bar_chart(source_df.set_index("Source Type"))
            with col2:
                st.dataframe(source_df, use_container_width=True, hide_index=True)

        # Platform breakdown
        st.markdown("### Platform Distribution")
        platform_stats = db.query(
            MunicipalSource.platform,
            func.count(MunicipalSource.id).label("count")
        ).group_by(MunicipalSource.platform).all()

        if platform_stats:
            platform_df = pd.DataFrame(platform_stats, columns=["Platform", "Count"])
            col1, col2 = st.columns([2, 1])
            with col1:
                st.bar_chart(platform_df.set_index("Platform"))
            with col2:
                st.dataframe(platform_df, use_container_width=True, hide_index=True)

    finally:
        db.close()


# --- TAB 2: STATES ---
with tab_states:
    st.header("Enrichment by State")

    db = SessionLocal()
    try:
        # Query state-level statistics
        state_stats = db.query(
            Municipality.state,
            func.count(Municipality.id).label("total"),
            func.sum(func.case((Municipality.domain_status == "verified", 1), else_=0)).label("verified"),
            func.sum(func.case((Municipality.domain_status == "unverified", 1), else_=0)).label("unverified"),
            func.sum(func.case((Municipality.domain_status == "dead", 1), else_=0)).label("dead"),
        ).group_by(Municipality.state).order_by(Municipality.state).all()

        # Convert to DataFrame
        df = pd.DataFrame(state_stats, columns=["State", "Total Cities", "Verified", "Unverified", "Dead"])
        df["Enrichment %"] = (df["Verified"] / df["Total Cities"] * 100).round(1)
        df["Sources"] = df["State"].apply(lambda state:
            db.query(func.count(MunicipalSource.id)).join(Municipality).filter(
                Municipality.state == state
            ).scalar()
        )

        # Display filters
        col1, col2 = st.columns([1, 3])
        with col1:
            min_enrichment = st.slider("Minimum Enrichment %", 0, 100, 0)

        # Filter dataframe
        filtered_df = df[df["Enrichment %"] >= min_enrichment]

        # Display summary
        st.markdown(f"**Showing {len(filtered_df)} of {len(df)} states**")

        # Color-code enrichment percentage
        def color_enrichment(val):
            if val >= 70:
                color = "background-color: #d4edda"  # Green
            elif val >= 40:
                color = "background-color: #fff3cd"  # Yellow
            else:
                color = "background-color: #f8d7da"  # Red
            return color

        styled_df = filtered_df.style.applymap(
            color_enrichment,
            subset=["Enrichment %"]
        ).format({
            "Total Cities": "{:,}",
            "Verified": "{:,}",
            "Unverified": "{:,}",
            "Dead": "{:,}",
            "Enrichment %": "{:.1f}%",
            "Sources": "{:,}",
        })

        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=600,
        )

        # Download CSV
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download State Statistics (CSV)",
            csv,
            file_name=f"state_enrichment_stats_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    finally:
        db.close()


# --- TAB 3: RUN ENRICHMENT ---
with tab_enrich:
    st.header("Run Enrichment")
    st.markdown("Trigger offline enrichment for unverified cities")

    db = SessionLocal()
    try:
        # Get state options
        state_stats = db.query(
            Municipality.state,
            func.count(Municipality.id).label("total"),
            func.sum(func.case((Municipality.domain_status == "unverified", 1), else_=0)).label("unverified"),
        ).group_by(Municipality.state).order_by(Municipality.state).all()

        state_options = [
            f"{state} ({unverified:,} unverified of {total:,})"
            for state, total, unverified in state_stats
        ]
        state_codes = [state for state, _, _ in state_stats]

        # Enrichment options
        st.markdown("### Select Enrichment Target")

        col1, col2 = st.columns(2)

        with col1:
            enrich_mode = st.radio(
                "Mode",
                ["Single State", "Multiple States", "All Unverified"],
                help="Choose which cities to enrich"
            )

        selected_states = []

        if enrich_mode == "Single State":
            with col2:
                selected_idx = st.selectbox(
                    "Select State",
                    range(len(state_options)),
                    format_func=lambda i: state_options[i]
                )
                selected_states = [state_codes[selected_idx]]

        elif enrich_mode == "Multiple States":
            with col2:
                st.markdown("**Select States:**")

            # Checkbox grid
            cols = st.columns(4)
            for i, (state_code, option) in enumerate(zip(state_codes, state_options)):
                with cols[i % 4]:
                    if st.checkbox(option, key=f"state_{state_code}"):
                        selected_states.append(state_code)

        else:  # All Unverified
            selected_states = state_codes
            st.info(f"Will enrich all {len(state_codes)} states")

        # Show what will be enriched
        if selected_states:
            st.markdown("### Enrichment Summary")

            cities_to_enrich = db.query(Municipality).filter(
                Municipality.state.in_(selected_states),
                Municipality.domain_status == "unverified"
            ).count()

            st.info(f"""
            **Target:** {len(selected_states)} state(s)
            **Cities to enrich:** {cities_to_enrich:,}
            **Estimated time:** {cities_to_enrich * 0.5:.0f}-{cities_to_enrich * 1:.0f} minutes
            """)

            # Warning for large batches
            if cities_to_enrich > 500:
                st.warning("⚠️ Large batch detected. Consider running enrichment for smaller batches or run in background.")

            # Start enrichment button
            if st.button("▶️ Start Enrichment", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Create enrichment engine
                engine = EnrichmentEngine()

                try:
                    status_text.text("Starting enrichment...")

                    # Run enrichment
                    if len(selected_states) == 1:
                        stats = engine.enrich_state(selected_states[0])
                    else:
                        stats = engine.enrich_states(selected_states)

                    progress_bar.progress(1.0)
                    status_text.empty()

                    # Show results
                    st.success("✅ Enrichment complete!")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Cities Processed", stats.get("total", 0))
                    with col2:
                        st.metric("Domains Verified", stats.get("verified", 0))
                    with col3:
                        st.metric("Sources Discovered", stats.get("sources", 0))

                    # Refresh statistics
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Enrichment failed: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

        else:
            st.warning("Please select at least one state to enrich")

    finally:
        db.close()


# Footer
st.markdown("---")
st.caption("Municipal Intel Admin Dashboard - Database-Driven Architecture")
