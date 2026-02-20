#!/usr/bin/env python3
"""
Test JavaScript fallback activation on San Francisco.
This verifies the fix to src/discovery.py works correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.database import SessionLocal, Municipality, MunicipalSource
from src.enrichment import EnrichmentEngine

print("="*70)
print("SAN FRANCISCO JS FALLBACK TEST")
print("Testing that JS fallback activates BEFORE domain root fallback")
print("="*70)

db = SessionLocal()

# Get San Francisco
sf = db.query(Municipality).filter_by(name="San Francisco", state="CA").first()

if not sf:
    print("ERROR: San Francisco not found in database")
    db.close()
    sys.exit(1)

print(f"\nTarget: {sf.name}, {sf.state}")
print(f"Population: {sf.population:,}")
print(f"Domain: {sf.domain}")
print(f"Domain status: {sf.domain_status}")
print(f"Resolved URL: {sf.resolved_url}")

# Check existing sources
existing_sources = db.query(MunicipalSource).filter_by(
    municipality_id=sf.id
).all()

print(f"\nExisting sources: {len(existing_sources)}")
for src in existing_sources:
    print(f"  - {src.url} (confidence={src.confidence})")

# Delete all sources to trigger fresh discovery
if existing_sources:
    print(f"\nDeleting {len(existing_sources)} source(s) to trigger fresh discovery...")
    for src in existing_sources:
        db.delete(src)
    db.commit()
    print("✓ Sources deleted")

print(f"\n{'='*70}")
print("RUNNING ENRICHMENT WITH NEW CODE")
print("Expected: Should see 'Trying JavaScript rendering fallback' message")
print("="*70)
print()

# Create enrichment engine
engine = EnrichmentEngine(request_delay=1.0, timeout=10)

# Run enrichment - should trigger JS fallback now that order is fixed
result = engine.enrich_municipality(sf, db)

print(f"\n{'='*70}")
print("ENRICHMENT RESULTS")
print("="*70)
print(f"Domain verified: {result['domain_verified']}")
print(f"Sources found: {result['sources_found']}")

# Check NEW sources
new_sources = db.query(MunicipalSource).filter_by(
    municipality_id=sf.id
).all()

print(f"\nTotal sources after enrichment: {len(new_sources)}")
for src in new_sources:
    print(f"  - {src.url}")
    print(f"    Platform: {src.platform}, Confidence: {src.confidence}")

db.close()

print(f"\n✓ Test complete!")
if result['sources_found'] > 0:
    print("✅ SUCCESS: JS fallback discovered sources!")
else:
    print("⚠️  No sources found - check logs for JS fallback activation")
