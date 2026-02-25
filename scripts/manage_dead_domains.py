#!/usr/bin/env python3
"""
Manage Dead Domains - View and Fix Dead Municipal Domains

This tool helps you:
1. List all municipalities with dead domains
2. Update a domain when you find the correct one manually
3. Re-trigger enrichment for specific cities
4. Export dead domains to CSV for batch research

Usage:
    # List all dead domains
    python3 scripts/manage_dead_domains.py --list

    # List dead domains for specific state
    python3 scripts/manage_dead_domains.py --list --state CA

    # List dead domains with population filter
    python3 scripts/manage_dead_domains.py --list --min-pop 10000

    # Update a domain
    python3 scripts/manage_dead_domains.py --update "Los Angeles" --state CA --domain lacity.gov

    # Update and re-enrich immediately
    python3 scripts/manage_dead_domains.py --update "Miami" --state FL --domain miamigov.com --reenrich

    # Export to CSV for research
    python3 scripts/manage_dead_domains.py --export dead_domains.csv

    # Export high-priority dead domains (pop > 50K)
    python3 scripts/manage_dead_domains.py --export priority_dead.csv --min-pop 50000
"""

import os
import sys
import argparse
import csv
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Municipality
from src.enrichment import EnrichmentEngine


def get_db_session():
    """Create database session."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        sys.exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def list_dead_domains(state: str = None, min_pop: int = 0, max_pop: int = None,
                     exclude_cdp: bool = False, limit: int = None):
    """List all municipalities with dead domains."""
    db = get_db_session()

    query = db.query(Municipality).filter(Municipality.domain_status == 'dead')

    if state:
        query = query.filter(Municipality.state == state.upper())

    if min_pop:
        query = query.filter(Municipality.population >= min_pop)

    if max_pop:
        query = query.filter(Municipality.population <= max_pop)

    if exclude_cdp:
        query = query.filter(~Municipality.name.like('%CDP%'))

    query = query.order_by(Municipality.population.desc())

    if limit:
        query = query.limit(limit)

    results = query.all()

    if not results:
        print("✅ No dead domains found!")
        return []

    print(f"\n{'='*100}")
    print(f"DEAD DOMAINS ({len(results)} municipalities)")
    print(f"{'='*100}")
    print(f"{'Municipality':<30} {'State':<6} {'Population':<12} {'Dead Domain':<40}")
    print(f"{'-'*100}")

    for muni in results:
        pop_str = f"{muni.population:,}" if muni.population else "N/A"
        domain = muni.domain or "N/A"
        print(f"{muni.name:<30} {muni.state:<6} {pop_str:<12} {domain:<40}")

    print(f"{'-'*100}")
    print(f"Total: {len(results)} municipalities\n")

    return results


def update_domain(city_name: str, state: str, new_domain: str, reenrich: bool = False):
    """Update domain for a municipality and optionally re-enrich."""
    db = get_db_session()

    # Find municipality
    muni = db.query(Municipality).filter(
        Municipality.name == city_name,
        Municipality.state == state.upper()
    ).first()

    if not muni:
        print(f"❌ Error: Municipality '{city_name}, {state}' not found")
        return False

    # Show before state
    print(f"\n📍 Updating: {muni.name}, {muni.state}")
    print(f"   Before: domain='{muni.domain}' status='{muni.domain_status}'")

    # Update domain
    old_domain = muni.domain
    muni.domain = new_domain
    muni.domain_status = 'unverified'  # Will be verified during enrichment
    muni.resolved_url = None  # Clear cached URL

    db.commit()

    print(f"   After:  domain='{muni.domain}' status='{muni.domain_status}'")
    print(f"✅ Domain updated successfully!")

    # Re-enrich if requested
    if reenrich:
        print(f"\n🔄 Re-enriching {muni.name}, {state}...")
        engine = EnrichmentEngine()

        # Clear existing sources
        db.execute(text("""
            DELETE FROM municipal_sources
            WHERE municipality_id = :muni_id
        """), {"muni_id": muni.id})
        db.commit()

        # Re-run enrichment
        try:
            from src.discovery import SourceDiscovery
            discovery = SourceDiscovery()
            results = discovery.discover_municipality(muni)

            if results['sources_found'] > 0:
                print(f"✅ Found {results['sources_found']} sources!")
                for source in results['sources'][:5]:  # Show first 5
                    print(f"   - {source['source_type']}: {source['url']}")
            else:
                print(f"⚠️  No sources found (domain may still be incorrect)")
        except Exception as e:
            print(f"❌ Enrichment error: {e}")

    print()
    return True


def export_to_csv(filename: str, state: str = None, min_pop: int = 0,
                 max_pop: int = None, exclude_cdp: bool = False):
    """Export dead domains to CSV for batch research."""
    db = get_db_session()

    query = db.query(Municipality).filter(Municipality.domain_status == 'dead')

    if state:
        query = query.filter(Municipality.state == state.upper())

    if min_pop:
        query = query.filter(Municipality.population >= min_pop)

    if max_pop:
        query = query.filter(Municipality.population <= max_pop)

    if exclude_cdp:
        query = query.filter(~Municipality.name.like('%CDP%'))

    query = query.order_by(Municipality.state, Municipality.population.desc())
    results = query.all()

    if not results:
        print("✅ No dead domains to export!")
        return

    # Write CSV
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Municipality', 'State', 'Population', 'Dead Domain',
            'Corrected Domain', 'Notes'
        ])

        for muni in results:
            writer.writerow([
                muni.name,
                muni.state,
                muni.population or 0,
                muni.domain or '',
                '',  # Empty column for manual correction
                ''   # Empty column for notes
            ])

    print(f"✅ Exported {len(results)} dead domains to: {filename}")
    print(f"   Edit the 'Corrected Domain' column and use --batch-update to apply changes")
    print()


def batch_update_from_csv(filename: str, reenrich: bool = False):
    """Update multiple domains from CSV file."""
    db = get_db_session()

    if not os.path.exists(filename):
        print(f"❌ Error: File not found: {filename}")
        return

    updates = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Corrected Domain', '').strip():
                updates.append({
                    'name': row['Municipality'],
                    'state': row['State'],
                    'new_domain': row['Corrected Domain'].strip()
                })

    if not updates:
        print("⚠️  No corrected domains found in CSV")
        return

    print(f"\n🔄 Batch updating {len(updates)} domains...\n")

    success_count = 0
    for update in updates:
        if update_domain(update['name'], update['state'], update['new_domain'], reenrich):
            success_count += 1

    print(f"\n✅ Updated {success_count}/{len(updates)} domains successfully!")


def main():
    parser = argparse.ArgumentParser(
        description="Manage dead municipal domains",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Commands
    parser.add_argument('--list', action='store_true',
                       help='List dead domains')
    parser.add_argument('--update', type=str, metavar='CITY',
                       help='Update domain for a city')
    parser.add_argument('--export', type=str, metavar='FILE',
                       help='Export dead domains to CSV')
    parser.add_argument('--batch-update', type=str, metavar='FILE',
                       help='Batch update domains from CSV')

    # Filters
    parser.add_argument('--state', type=str,
                       help='Filter by state (e.g., CA, TX)')
    parser.add_argument('--min-pop', type=int, default=0,
                       help='Minimum population filter')
    parser.add_argument('--max-pop', type=int,
                       help='Maximum population filter (useful for targeting small towns)')
    parser.add_argument('--exclude-cdp', action='store_true',
                       help='Exclude CDPs (Census Designated Places) - unincorporated areas')
    parser.add_argument('--limit', type=int,
                       help='Limit number of results')

    # Update options
    parser.add_argument('--domain', type=str,
                       help='New domain for --update')
    parser.add_argument('--reenrich', action='store_true',
                       help='Re-enrich after updating domain')

    args = parser.parse_args()

    # Execute command
    if args.list:
        list_dead_domains(args.state, args.min_pop, args.max_pop, args.exclude_cdp, args.limit)

    elif args.update:
        if not args.domain:
            print("❌ Error: --domain required with --update")
            sys.exit(1)
        if not args.state:
            print("❌ Error: --state required with --update")
            sys.exit(1)

        update_domain(args.update, args.state, args.domain, args.reenrich)

    elif args.export:
        export_to_csv(args.export, args.state, args.min_pop, args.max_pop, args.exclude_cdp)

    elif args.batch_update:
        batch_update_from_csv(args.batch_update, args.reenrich)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
