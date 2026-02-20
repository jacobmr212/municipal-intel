#!/usr/bin/env python3
"""
Test discovery with verbose logging to see which fallback section activates.
"""
import sys
import os
import logging

# Configure logging BEFORE importing modules
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)

sys.path.insert(0, os.path.dirname(__file__))

from src.discovery import SourceDiscovery

print("="*70)
print("DISCOVERY LOGGING TEST — San Francisco")
print("Testing which fallback section activates (should be JS, not root)")
print("="*70)
print()

# Create discovery instance
discovery = SourceDiscovery(request_delay=1.0, timeout=10)

# Test on San Francisco
print("Running discovery on San Francisco, CA (pop 873,965)...")
print("Domain: sf.gov")
print()
print("Expected flow:")
print("  1. Standard patterns → (likely fail)")
print("  2. Third-party platforms → (likely fail)")
print("  3. JS rendering fallback → (should activate HERE)")
print("  4. Domain root fallback → (should NOT reach this)")
print()
print("-" * 70)

sources = discovery.discover_municipality(
    name="San Francisco",
    state="CA",
    domain="sf.gov",
    population=873965
)

print("-" * 70)
print()
print(f"RESULTS: {len(sources)} source(s) found")
for s in sources:
    print(f"  - {s.url}")
    print(f"    Type: {s.source_type}, Confidence: {s.confidence}")
print()

if sources and sources[0].confidence == 0.3:
    print("⚠️  LOW CONFIDENCE (0.3) — This means domain root fallback was used!")
    print("❌ BUG: Domain root fallback ran BEFORE JS fallback")
elif sources and sources[0].confidence >= 0.85:
    print("✅ HIGH CONFIDENCE (0.85+) — JS fallback worked!")
else:
    print("🤔 Unexpected confidence level")
