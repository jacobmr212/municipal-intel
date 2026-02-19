"""
Michigan State Enrichment Script

Discovers meeting minutes sources for all Michigan municipalities using
domain verification and URL pattern probing.

Run:
    DATABASE_URL=... python3 scripts/enrich_michigan.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.enrichment import EnrichmentEngine

def progress_callback(current, total, message):
    """Print progress updates."""
    pct = int((current / total) * 100)
    print(f'[{pct:3d}%] ({current}/{total}) {message}', flush=True)

def main():
    print('='*60)
    print('MICHIGAN ENRICHMENT')
    print('='*60)

    enricher = EnrichmentEngine(request_delay=1.0, timeout=10)
    results = enricher.enrich_state('MI', progress_callback=progress_callback)

    print(f'\n{'='*60}')
    print(f'RESULTS')
    print(f'{'='*60}')
    print(f'Total municipalities: {results["total"]}')
    print(f'Already enriched: {results["already_verified"]}')
    print(f'Domains verified: {results["domains_verified"]}')
    print(f'Domains dead: {results["domains_dead"]}')
    print(f'Sources discovered: {results["sources_found"]}')

    print(f'\n✓ Michigan enrichment complete!')


if __name__ == '__main__':
    main()
