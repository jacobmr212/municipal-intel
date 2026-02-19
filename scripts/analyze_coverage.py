"""
Coverage Analysis Script

Analyzes nationwide source coverage to identify gaps and opportunities
for maximizing municipal intelligence collection.

Run:
    DATABASE_URL=... python3 scripts/analyze_coverage.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database import SessionLocal, Municipality, MunicipalSource
from sqlalchemy import func


def analyze_coverage():
    """Analyze source coverage across all states."""
    db = SessionLocal()

    print('='*80)
    print('MUNICIPAL INTEL — NATIONWIDE COVERAGE ANALYSIS')
    print('='*80)

    # Overall statistics
    total_municipalities = db.query(Municipality).count()
    total_sources = db.query(MunicipalSource).count()
    municipalities_with_sources = db.query(Municipality).join(MunicipalSource).distinct().count()

    print(f'\n📊 OVERALL STATISTICS')
    print(f'{"="*80}')
    print(f'Total municipalities in database: {total_municipalities:,}')
    print(f'Municipalities with sources: {municipalities_with_sources:,} ({municipalities_with_sources/total_municipalities*100:.1f}%)')
    print(f'Total sources discovered: {total_sources:,}')
    print(f'Average sources per municipality: {total_sources/municipalities_with_sources:.2f}')

    # State-by-state breakdown
    print(f'\n🗺️  STATE-BY-STATE BREAKDOWN')
    print(f'{"="*80}')

    state_stats = (
        db.query(
            Municipality.state,
            func.count(func.distinct(Municipality.id)).label('munis'),
            func.count(MunicipalSource.id).label('sources')
        )
        .outerjoin(MunicipalSource, MunicipalSource.municipality_id == Municipality.id)
        .group_by(Municipality.state)
        .order_by(func.count(MunicipalSource.id).desc())
        .all()
    )

    print(f'{"State":<6} {"Munis":<8} {"Sources":<10} {"Coverage":<10} {"Avg/Muni"}')
    print(f'{"-"*80}')

    states_with_sources = []
    states_without_sources = []

    for state, munis, sources in state_stats:
        coverage_pct = (sources / munis * 100) if munis > 0 else 0
        avg_per_muni = (sources / munis) if munis > 0 else 0

        if sources > 0:
            states_with_sources.append((state, munis, sources, coverage_pct))
            print(f'{state:<6} {munis:<8,} {sources:<10,} {coverage_pct:>6.1f}%     {avg_per_muni:.2f}')
        else:
            states_without_sources.append((state, munis))

    if states_without_sources:
        print(f'\n⚠️  STATES WITHOUT SOURCES:')
        for state, munis in states_without_sources:
            print(f'  {state}: {munis} municipalities (enrichment in progress or pending)')

    # Source type distribution
    print(f'\n📁 SOURCE TYPE DISTRIBUTION')
    print(f'{"="*80}')

    type_stats = (
        db.query(
            MunicipalSource.source_type,
            func.count(MunicipalSource.id).label('count')
        )
        .group_by(MunicipalSource.source_type)
        .order_by(func.count(MunicipalSource.id).desc())
        .all()
    )

    for source_type, count in type_stats:
        pct = (count / total_sources * 100) if total_sources > 0 else 0
        print(f'{source_type:<20} {count:>6,} ({pct:>5.1f}%)')

    # Platform distribution (CivicPlus, Granicus, etc.)
    print(f'\n🏛️  PLATFORM DISTRIBUTION')
    print(f'{"="*80}')

    platform_stats = (
        db.query(
            MunicipalSource.platform,
            func.count(MunicipalSource.id).label('count')
        )
        .filter(MunicipalSource.platform.isnot(None))
        .group_by(MunicipalSource.platform)
        .order_by(func.count(MunicipalSource.id).desc())
        .all()
    )

    for platform, count in platform_stats:
        pct = (count / total_sources * 100) if total_sources > 0 else 0
        print(f'{platform:<20} {count:>6,} ({pct:>5.1f}%)')

    # Source type by state (top 10 states)
    print(f'\n📊 SOURCE TYPE BREAKDOWN (Top 10 States)')
    print(f'{"="*80}')

    top_states = [s[0] for s in states_with_sources[:10]]

    for state in top_states:
        type_breakdown = (
            db.query(
                MunicipalSource.source_type,
                func.count(MunicipalSource.id).label('count')
            )
            .join(Municipality, MunicipalSource.municipality_id == Municipality.id)
            .filter(Municipality.state == state)
            .group_by(MunicipalSource.source_type)
            .all()
        )

        type_dict = defaultdict(int)
        for stype, count in type_breakdown:
            type_dict[stype] = count

        total_state_sources = sum(type_dict.values())

        print(f'\n{state} ({total_state_sources} sources):')
        print(f'  Meeting Minutes:  {type_dict.get("meeting_minutes", 0):>4}  ({type_dict.get("meeting_minutes", 0)/total_state_sources*100:>5.1f}%)')
        print(f'  Procurement:      {type_dict.get("procurement", 0):>4}  ({type_dict.get("procurement", 0)/total_state_sources*100:>5.1f}%)')
        print(f'  Budget:           {type_dict.get("budget", 0):>4}  ({type_dict.get("budget", 0)/total_state_sources*100:>5.1f}%)')
        print(f'  State Portal:     {type_dict.get("state_portal", 0):>4}  ({type_dict.get("state_portal", 0)/total_state_sources*100:>5.1f}%)')

    # Coverage gaps and recommendations
    print(f'\n💡 COVERAGE RECOMMENDATIONS')
    print(f'{"="*80}')

    # Find states with low procurement/budget coverage
    low_procurement_states = []
    for state in top_states:
        type_breakdown = dict(
            db.query(
                MunicipalSource.source_type,
                func.count(MunicipalSource.id)
            )
            .join(Municipality, MunicipalSource.municipality_id == Municipality.id)
            .filter(Municipality.state == state)
            .group_by(MunicipalSource.source_type)
            .all()
        )

        total = sum(type_breakdown.values())
        procurement_pct = (type_breakdown.get('procurement', 0) / total * 100) if total > 0 else 0
        budget_pct = (type_breakdown.get('budget', 0) / total * 100) if total > 0 else 0

        if procurement_pct < 10 and total > 20:  # States with good overall coverage but lacking procurement
            low_procurement_states.append((state, procurement_pct, budget_pct, total))

    if low_procurement_states:
        print(f'\n1. States needing procurement/budget enrichment:')
        for state, proc_pct, budget_pct, total in low_procurement_states[:5]:
            print(f'   {state}: {total} sources, but only {proc_pct:.1f}% procurement, {budget_pct:.1f}% budget')
            print(f'       → Run: python3 scripts/discover_procurement_sources.py --states {state}')

    # Find states with low overall coverage
    print(f'\n2. States with low municipality coverage (<50%):')
    low_coverage_states = []
    for state, munis, sources, coverage_pct in states_with_sources:
        if coverage_pct < 50 and munis > 10:
            low_coverage_states.append((state, munis, sources, coverage_pct))

    if low_coverage_states:
        for state, munis, sources, coverage_pct in low_coverage_states[:5]:
            print(f'   {state}: {sources}/{munis} municipalities ({coverage_pct:.1f}% coverage)')
            print(f'       → Re-run enrichment with expanded URL patterns')
    else:
        print(f'   ✅ All states with 10+ municipalities have >50% coverage!')

    # Platform diversity recommendation
    print(f'\n3. Platform coverage:')
    platform_count = len(platform_stats)
    print(f'   Currently detecting {platform_count} distinct platforms')
    print(f'   ✅ Good platform diversity ensures we catch municipalities regardless of website vendor')

    # Domain status check
    print(f'\n4. Domain verification status:')
    domain_stats = (
        db.query(
            Municipality.domain_status,
            func.count(Municipality.id).label('count')
        )
        .group_by(Municipality.domain_status)
        .all()
    )

    for status, count in domain_stats:
        pct = (count / total_municipalities * 100) if total_municipalities > 0 else 0
        print(f'   {status or "NULL":<15} {count:>6,} ({pct:>5.1f}%)')

    unverified = sum(count for status, count in domain_stats if status in ['unverified', None])
    if unverified > 0:
        print(f'\n   ⚠️  {unverified:,} municipalities still unverified — enrichments likely in progress')

    print(f'\n{"="*80}')
    print(f'✅ Analysis complete!')
    print(f'{"="*80}')

    db.close()


if __name__ == '__main__':
    analyze_coverage()
