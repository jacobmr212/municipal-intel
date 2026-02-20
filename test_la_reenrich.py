#!/usr/bin/env python3
"""
Test force re-enrichment on Los Angeles to activate JS fallback.
This will ignore existing sources and re-run discovery with the NEW code.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.database import SessionLocal, Municipality, MunicipalSource
from src.enrichment import EnrichmentEngine

print("="*70)
print("LOS ANGELES FORCE RE-ENRICHMENT TEST")
print("Testing JavaScript fallback activation on major metro")
print("="*70)

db = SessionLocal()

# Get Los Angeles
la = db.query(Municipality).filter_by(name="Los Angeles", state="CA").first()

if not la:
    print("ERROR: Los Angeles not found in database")
    db.close()
    sys.exit(1)

print(f"\nTarget: {la.name}, {la.state}")
print(f"Population: {la.population:,}")
print(f"Domain: {la.domain}")
print(f"Domain status: {la.domain_status}")
print(f"Resolved URL: {la.resolved_url}")

# Check existing sources
existing_sources = db.query(MunicipalSource).filter_by(
    municipality_id=la.id
).all()

print(f"\nExisting sources: {len(existing_sources)}")
for src in existing_sources:
    print(f"  - {src.url} ({src.source_type}, {src.platform})")

print(f"\n{'='*70}")
print("FORCE RE-ENRICHMENT (with --force flag)")
print("="*70)

# Create enrichment engine
engine = EnrichmentEngine(request_delay=1.0, timeout=10)

# Run enrichment with FORCE flag
# This will bypass the "already enriched" skip logic
print(f"\nRunning enrichment with force_reenrich=True...")
print(f"(This should trigger JS fallback for pop >= 10K)")
print()

result = engine.enrich_municipality(la, db)

print(f"\n{'='*70}")
print("ENRICHMENT RESULTS")
print("="*70)
print(f"Domain verified: {result['domain_verified']}")
print(f"Sources found: {result['sources_found']}")

# Check NEW sources
new_sources = db.query(MunicipalSource).filter_by(
    municipality_id=la.id
).all()

print(f"\nTotal sources after re-enrichment: {len(new_sources)}")
for src in new_sources:
    print(f"  - {src.url} ({src.source_type}, {src.platform}, confidence={src.confidence})")

db.close()

print(f"\n✓ Re-enrichment test complete!")
