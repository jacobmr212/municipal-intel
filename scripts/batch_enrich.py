"""
Batch Enrichment Runner

Runs enrichment across multiple states in parallel to maximize coverage.
Uses process pool to parallelize I/O-bound enrichment tasks.

Usage:
    python scripts/batch_enrich.py --all                  # All states
    python scripts/batch_enrich.py --states CA TX FL NY   # Specific states
    python scripts/batch_enrich.py --top 10               # Top 10 by population
    python scripts/batch_enrich.py --workers 5            # Custom worker count
"""

import sys
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.enrichment import EnrichmentEngine
from src.database import SessionLocal, Municipality
from sqlalchemy import func

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# State codes for all 50 states + DC + PR
ALL_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR'
]


def enrich_state_worker(state: str, force_reenrich: bool = False):
    """
    Worker function to enrich a single state.
    Runs in separate process for true parallelism.
    """
    try:
        logger.info(f"Starting enrichment for {state}")
        start_time = datetime.now()

        engine = EnrichmentEngine()
        results = engine.enrich_state(
            state,
            force_reenrich=force_reenrich
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"✓ {state} complete in {elapsed:.1f}s: "
                   f"{results['domains_verified']} verified, "
                   f"{results['sources_found']} sources")

        return {
            'state': state,
            'success': True,
            'results': results,
            'elapsed': elapsed
        }

    except Exception as e:
        logger.error(f"✗ {state} failed: {e}")
        return {
            'state': state,
            'success': False,
            'error': str(e),
            'elapsed': 0
        }


def get_state_priorities():
    """
    Get states prioritized by total city count (population >= 2500).
    Returns list of (state, city_count) tuples sorted by count descending.
    """
    db = SessionLocal()
    try:
        priorities = db.query(
            Municipality.state,
            func.count(Municipality.id).label('city_count')
        ).filter(
            Municipality.population >= 2500
        ).group_by(
            Municipality.state
        ).order_by(
            func.count(Municipality.id).desc()
        ).all()

        return [(row.state, row.city_count) for row in priorities]

    finally:
        db.close()


def batch_enrich(states: list[str], max_workers: int = 3, force_reenrich: bool = False):
    """
    Enrich multiple states in parallel.

    Args:
        states: List of state codes to enrich
        max_workers: Number of parallel workers (default: 3)
        force_reenrich: Re-enrich cities that already have sources
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"BATCH ENRICHMENT: {len(states)} states, {max_workers} workers")
    logger.info(f"{'='*80}")
    logger.info(f"States: {', '.join(states)}")
    logger.info(f"Force re-enrich: {force_reenrich}")
    logger.info(f"{'='*80}\n")

    start_time = datetime.now()
    results = []

    # Use ProcessPoolExecutor for true parallelism (I/O-bound with GIL-free domains)
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all state enrichment jobs
        future_to_state = {
            executor.submit(enrich_state_worker, state, force_reenrich): state
            for state in states
        }

        # Collect results as they complete
        for future in as_completed(future_to_state):
            state = future_to_state[future]
            try:
                result = future.result()
                results.append(result)

                # Progress update
                completed = len(results)
                logger.info(f"Progress: {completed}/{len(states)} states completed")

            except Exception as e:
                logger.error(f"State {state} raised exception: {e}")
                results.append({
                    'state': state,
                    'success': False,
                    'error': str(e),
                    'elapsed': 0
                })

    # Summary report
    total_elapsed = (datetime.now() - start_time).total_seconds()
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    total_verified = sum(r['results']['domains_verified'] for r in successful)
    total_dead = sum(r['results']['domains_dead'] for r in successful)
    total_sources = sum(r['results']['sources_found'] for r in successful)

    logger.info(f"\n{'='*80}")
    logger.info(f"BATCH ENRICHMENT COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Total time: {total_elapsed/60:.1f} minutes")
    logger.info(f"Successful: {len(successful)}/{len(states)} states")
    logger.info(f"Failed: {len(failed)} states")
    logger.info(f"\nResults:")
    logger.info(f"  ✓ Verified domains: {total_verified}")
    logger.info(f"  ✗ Dead domains: {total_dead}")
    logger.info(f"  📍 Sources found: {total_sources}")

    if failed:
        logger.info(f"\nFailed states: {', '.join([r['state'] for r in failed])}")

    # Top 10 by sources found
    successful_sorted = sorted(successful, key=lambda r: r['results']['sources_found'], reverse=True)
    logger.info(f"\nTop 10 states by sources found:")
    for i, r in enumerate(successful_sorted[:10], 1):
        logger.info(f"  {i}. {r['state']}: {r['results']['sources_found']} sources "
                   f"({r['results']['domains_verified']} verified)")

    logger.info(f"{'='*80}\n")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch state enrichment')
    parser.add_argument('--all', action='store_true', help='Enrich all states')
    parser.add_argument('--states', nargs='+', help='Specific states to enrich (e.g., CA TX FL)')
    parser.add_argument('--top', type=int, help='Enrich top N states by city count')
    parser.add_argument('--workers', type=int, default=3, help='Number of parallel workers (default: 3)')
    parser.add_argument('--force', action='store_true', help='Force re-enrich cities with sources')
    parser.add_argument('--exclude', nargs='+', help='States to exclude (e.g., UT ID)')

    args = parser.parse_args()

    # Determine which states to enrich
    if args.all:
        states = ALL_STATES
    elif args.states:
        states = [s.upper() for s in args.states]
    elif args.top:
        priorities = get_state_priorities()
        states = [state for state, _ in priorities[:args.top]]
    else:
        # Default: Show priorities and exit
        priorities = get_state_priorities()
        print("\nSTATE PRIORITIES (by city count, pop >= 2.5K)")
        print("="*50)
        for i, (state, count) in enumerate(priorities[:20], 1):
            print(f"  {i:2d}. {state}: {count:3d} cities")
        print("="*50)
        print("\nUsage:")
        print("  python scripts/batch_enrich.py --all              # All states")
        print("  python scripts/batch_enrich.py --top 10           # Top 10")
        print("  python scripts/batch_enrich.py --states CA TX FL  # Specific states")
        print("  python scripts/batch_enrich.py --workers 5        # Custom workers")
        return

    # Exclude states if specified
    if args.exclude:
        exclude_upper = [s.upper() for s in args.exclude]
        states = [s for s in states if s not in exclude_upper]
        logger.info(f"Excluding: {', '.join(exclude_upper)}")

    if not states:
        logger.error("No states to enrich!")
        return

    # Run batch enrichment
    batch_enrich(states, max_workers=args.workers, force_reenrich=args.force)


if __name__ == "__main__":
    main()
