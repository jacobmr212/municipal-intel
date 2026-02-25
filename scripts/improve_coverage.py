"""
Enrichment Coverage Improvement Script

Analyzes current source coverage and systematically improves it by:
1. Re-enriching states with low coverage (< 20 sources)
2. Force re-enriching major metros that may have stale sources
3. Targeting cities with population >= 10K that have no sources
4. Retrying failed enrichments with fresh domain verification

Goal: Achieve 90%+ enrichment success rate across all targeted cities.
"""

import sys
import os
from sqlalchemy import func, and_, or_, case
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal, Municipality, MunicipalSource
from src.enrichment import EnrichmentEngine
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_coverage():
    """Analyze current enrichment coverage by state."""
    db = SessionLocal()

    try:
        # Get coverage statistics by state
        stats = db.query(
            Municipality.state,
            func.count(Municipality.id).label('total_cities'),
            func.sum(case(
                (Municipality.domain_status == 'verified', 1),
                else_=0
            )).label('verified'),
            func.sum(case(
                (Municipality.domain_status == 'dead', 1),
                else_=0
            )).label('dead'),
            func.sum(case(
                (Municipality.domain_status == 'unverified', 1),
                else_=0
            )).label('unverified'),
        ).filter(
            Municipality.population >= 2500  # Only count cities we target
        ).group_by(
            Municipality.state
        ).order_by(
            func.count(Municipality.id).desc()
        ).all()

        print("\n" + "="*80)
        print("ENRICHMENT COVERAGE ANALYSIS")
        print("="*80)
        print(f"{'State':<8} {'Total':<8} {'Verified':<10} {'Dead':<8} {'Unverified':<12} {'Coverage %':<12}")
        print("-"*80)

        total_cities = 0
        total_verified = 0
        total_dead = 0
        total_unverified = 0
        low_coverage_states = []

        for row in stats:
            state = row.state
            total = row.total_cities
            verified = row.verified or 0
            dead = row.dead or 0
            unverified = row.unverified or 0

            total_cities += total
            total_verified += verified
            total_dead += dead
            total_unverified += unverified

            coverage_pct = round((verified / total * 100), 1) if total > 0 else 0

            # Flag states with low coverage (< 50% verified)
            status_icon = "🔴" if coverage_pct < 50 else "🟡" if coverage_pct < 75 else "🟢"

            if coverage_pct < 50 and unverified > 5:
                low_coverage_states.append((state, unverified, coverage_pct))

            print(f"{status_icon} {state:<6} {total:<8} {verified:<10} {dead:<8} {unverified:<12} {coverage_pct}%")

        print("-"*80)

        overall_coverage = round((total_verified / total_cities * 100), 1) if total_cities > 0 else 0
        print(f"TOTAL    {total_cities:<8} {total_verified:<10} {total_dead:<8} {total_unverified:<12} {overall_coverage}%")
        print("="*80)

        # Get source count by state
        print("\nSOURCE COVERAGE BY STATE")
        print("="*80)
        source_stats = db.query(
            Municipality.state,
            func.count(MunicipalSource.id).label('source_count')
        ).join(
            MunicipalSource,
            Municipality.id == MunicipalSource.municipality_id
        ).group_by(
            Municipality.state
        ).order_by(
            func.count(MunicipalSource.id).desc()
        ).all()

        print(f"{'State':<8} {'Sources':<10}")
        print("-"*30)
        for row in source_stats:
            print(f"{row.state:<8} {row.source_count:<10}")

        print("="*80)

        return {
            'overall_coverage': overall_coverage,
            'low_coverage_states': low_coverage_states,
            'total_cities': total_cities,
            'total_verified': total_verified,
            'total_unverified': total_unverified,
        }

    finally:
        db.close()


def get_major_metros_without_sources():
    """Find major metro areas (pop >= 50K) that have no sources."""
    db = SessionLocal()

    try:
        # Find cities >= 50K with domain_status='verified' but no sources
        metros = db.query(Municipality).filter(
            and_(
                Municipality.population >= 50000,
                Municipality.domain_status == 'verified',
                ~Municipality.sources.any()  # No sources
            )
        ).order_by(
            Municipality.population.desc()
        ).limit(50).all()

        print("\nMAJOR METROS WITHOUT SOURCES (pop >= 50K)")
        print("="*80)
        print(f"{'City':<30} {'State':<8} {'Population':<12} {'Domain Status':<15}")
        print("-"*80)

        for city in metros:
            print(f"{city.name:<30} {city.state:<8} {city.population:>10,} {city.domain_status:<15}")

        print("="*80)
        print(f"Total: {len(metros)} major metros without sources\n")

        return metros

    finally:
        db.close()


def get_unverified_cities_by_state(state: str, limit: int = 100):
    """Get unverified cities in a specific state."""
    db = SessionLocal()

    try:
        cities = db.query(Municipality).filter(
            and_(
                Municipality.state == state,
                Municipality.domain_status == 'unverified',
                Municipality.population >= 2500
            )
        ).order_by(
            Municipality.population.desc()
        ).limit(limit).all()

        return cities

    finally:
        db.close()


def improve_state_coverage(state: str, force_reenrich: bool = False, max_cities: int = None):
    """
    Improve coverage for a specific state.

    Args:
        state: Two-letter state code
        force_reenrich: If True, re-enrich cities that already have sources
        max_cities: Maximum number of cities to process (None = all)
    """
    engine = EnrichmentEngine()

    logger.info(f"\n{'='*80}")
    logger.info(f"IMPROVING COVERAGE FOR {state}")
    logger.info(f"{'='*80}")
    logger.info(f"Force re-enrich: {force_reenrich}")
    logger.info(f"Max cities: {max_cities or 'unlimited'}")

    # Run enrichment
    results = engine.enrich_state(
        state,
        min_population=2500,
        force_reenrich=force_reenrich,
        max_cities=max_cities
    )

    logger.info(f"\n{'='*80}")
    logger.info(f"RESULTS FOR {state}")
    logger.info(f"{'='*80}")
    logger.info(f"✓ Verified: {results['verified']}")
    logger.info(f"✗ Dead: {results['dead']}")
    logger.info(f"📍 Sources found: {results['sources_found']}")
    logger.info(f"{'='*80}\n")

    return results


def improve_major_metros():
    """Force re-enrich major metros that have no sources."""
    metros = get_major_metros_without_sources()

    if not metros:
        logger.info("✓ All major metros have sources!")
        return

    logger.info(f"\nRe-enriching {len(metros)} major metros without sources...")

    engine = EnrichmentEngine()
    total_sources_found = 0

    for metro in metros:
        logger.info(f"\nRe-enriching: {metro.name}, {metro.state} (pop: {metro.population:,})")

        # Force re-discover sources for this city
        from src.discovery import SourceDiscovery
        discovery = SourceDiscovery(engine.db)

        sources = discovery.discover_municipality(metro)

        if sources:
            logger.info(f"  ✓ Found {len(sources)} sources for {metro.name}")
            total_sources_found += len(sources)
        else:
            logger.info(f"  ✗ No sources found for {metro.name}")

    logger.info(f"\n{'='*80}")
    logger.info(f"MAJOR METROS RE-ENRICHMENT COMPLETE")
    logger.info(f"Total new sources discovered: {total_sources_found}")
    logger.info(f"{'='*80}\n")


def improve_low_coverage_states(coverage_threshold: float = 50.0, max_states: int = 10):
    """
    Systematically improve states with coverage below threshold.

    Args:
        coverage_threshold: Only process states below this coverage percentage
        max_states: Maximum number of states to process
    """
    analysis = analyze_coverage()
    low_coverage = analysis['low_coverage_states']

    if not low_coverage:
        logger.info(f"✓ All states have coverage >= {coverage_threshold}%!")
        return

    # Sort by number of unverified cities (highest first)
    low_coverage.sort(key=lambda x: x[1], reverse=True)

    states_to_process = low_coverage[:max_states]

    logger.info(f"\n{'='*80}")
    logger.info(f"PROCESSING {len(states_to_process)} LOW-COVERAGE STATES")
    logger.info(f"{'='*80}")

    for state, unverified_count, current_coverage in states_to_process:
        logger.info(f"\nProcessing {state}: {current_coverage}% coverage, {unverified_count} unverified cities")

        # Process up to 50 cities per state
        improve_state_coverage(state, force_reenrich=False, max_cities=50)

    # Re-analyze coverage after improvements
    logger.info("\n\nFINAL COVERAGE ANALYSIS")
    analyze_coverage()


def main():
    """Main entry point for coverage improvement."""
    import argparse

    parser = argparse.ArgumentParser(description='Improve enrichment coverage')
    parser.add_argument('--analyze', action='store_true', help='Analyze current coverage')
    parser.add_argument('--state', type=str, help='Improve specific state (e.g., CA)')
    parser.add_argument('--force', action='store_true', help='Force re-enrich cities with sources')
    parser.add_argument('--metros', action='store_true', help='Re-enrich major metros without sources')
    parser.add_argument('--auto', action='store_true', help='Automatically improve low-coverage states')
    parser.add_argument('--max-cities', type=int, help='Max cities to process per state')
    parser.add_argument('--max-states', type=int, default=10, help='Max states to process in auto mode')

    args = parser.parse_args()

    if args.analyze:
        analyze_coverage()
    elif args.state:
        improve_state_coverage(args.state, force_reenrich=args.force, max_cities=args.max_cities)
    elif args.metros:
        improve_major_metros()
    elif args.auto:
        improve_low_coverage_states(coverage_threshold=50.0, max_states=args.max_states)
    else:
        # Default: show analysis and provide guidance
        analysis = analyze_coverage()
        get_major_metros_without_sources()

        print("\n" + "="*80)
        print("NEXT STEPS")
        print("="*80)
        print("\nTo improve coverage, run one of:")
        print("  python scripts/improve_coverage.py --auto           # Auto-improve low-coverage states")
        print("  python scripts/improve_coverage.py --metros         # Re-enrich major metros")
        print("  python scripts/improve_coverage.py --state CA       # Improve specific state")
        print("  python scripts/improve_coverage.py --state CA --force  # Force re-enrich CA")
        print("="*80 + "\n")


if __name__ == "__main__":
    main()
