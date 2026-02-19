"""
Arizona State Enrichment Script

Discovers meeting minutes sources for all Arizona municipalities using
domain verification and URL pattern probing.

Run:
    DATABASE_URL=... python3 scripts/enrich_arizona.py
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
    print('ARIZONA ENRICHMENT')
    print('='*60)

    enricher = EnrichmentEngine(request_delay=1.0, timeout=10)
    results = enricher.enrich_state('AZ', progress_callback=progress_callback)

    print(f'\n{'='*60}')
    print(f'RESULTS')
    print(f'{'='*60}')
    print(f'Domains verified: {results["verified"]}')
    print(f'Domains failed: {results["failed"]}')
    print(f'Sources discovered: {results["sources_found"]}')
    print(f'  Meeting minutes: {results.get("meeting_minutes", 0)}')
    print(f'  Procurement: {results.get("procurement", 0)}')
    print(f'  Budget: {results.get("budget", 0)}')

    print(f'\n✓ Arizona enrichment complete!')


if __name__ == '__main__':
    main()
