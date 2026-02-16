"""
Test the full Municipal Intel pipeline against real Utah municipalities.
"""

import json
import logging
from pathlib import Path

from src.discovery import SourceDiscovery
from src.scraper import MunicipalScraper
from src.analyzer import DocumentAnalyzer

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    print("="*60)
    print("Municipal Intel — Pipeline Test")
    print("Testing against 5 Utah municipalities")
    print("="*60)

    # Load Utah municipalities
    with open("data/municipalities.json") as f:
        db = json.load(f)

    utah_munis = db["states"]["UT"]["municipalities"][:5]
    print(f"\nTesting with: {', '.join(m['name'] for m in utah_munis)}\n")

    # Phase 1: Discovery
    print("\n" + "="*60)
    print("PHASE 1: SOURCE DISCOVERY")
    print("="*60)

    discovery = SourceDiscovery(request_delay=0.5, timeout=10)
    all_sources = []

    for muni in utah_munis:
        logger.info(f"\nDiscovering sources for {muni['name']}, UT...")
        sources = discovery.discover_municipality(
            name=muni["name"],
            state="UT",
            domain=muni.get("domain", ""),
            population=muni.get("population", 0),
        )
        if sources:
            all_sources.extend(sources)
            print(f"  ✓ Found {len(sources)} source(s)")
            for s in sources:
                print(f"    - {s.url} ({s.source_type}, confidence={s.confidence:.0%})")
        else:
            print(f"  ✗ No sources found")

    print(f"\n✓ Discovery complete: {len(all_sources)} sources found across {len(utah_munis)} cities")

    if not all_sources:
        print("\n⚠️  WARNING: No sources discovered. Discovery engine needs fixing.")
        print("Check URL patterns in src/signals.py")
        return

    # Phase 2: Scraping
    print("\n" + "="*60)
    print("PHASE 2: SCRAPING")
    print("="*60)

    scraper = MunicipalScraper(delay=0.5, timeout=15, max_docs=5)
    all_docs = []

    for source in all_sources:
        logger.info(f"\nScraping {source.municipality}, UT...")
        try:
            docs = scraper.scrape_source(source)
            if docs:
                all_docs.extend(docs)
                print(f"  ✓ Scraped {len(docs)} document(s)")
                for doc in docs[:2]:  # Show first 2
                    print(f"    - {doc.title[:60]}...")
            else:
                print(f"  ✗ No documents extracted")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print(f"\n✓ Scraping complete: {len(all_docs)} documents from {len(all_sources)} sources")

    if not all_docs:
        print("\n⚠️  WARNING: No documents scraped. Scraper needs fixing.")
        print("Check scraping logic in src/scraper.py")
        return

    # Phase 3: Analysis
    print("\n" + "="*60)
    print("PHASE 3: ANALYSIS")
    print("="*60)

    analyzer = DocumentAnalyzer(use_llm=False)
    results = []

    population_map = {m["name"]: m.get("population", 0) for m in utah_munis}

    for doc in all_docs:
        pop = population_map.get(doc.municipality, 0)
        result = analyzer.analyze_document(doc, population=pop, min_score=10)
        if result:
            results.append(result)

    results.sort(key=lambda r: r.relevance_score, reverse=True)

    hot = sum(1 for r in results if r.lead_type == "hot")
    warm = sum(1 for r in results if r.lead_type == "warm")
    cold = sum(1 for r in results if r.lead_type == "cold")

    print(f"\n✓ Analysis complete: {len(results)} leads found")
    print(f"  🔥 Hot: {hot}")
    print(f"  🟡 Warm: {warm}")
    print(f"  🔵 Cold: {cold}")

    if results:
        print("\n" + "="*60)
        print("TOP 3 LEADS")
        print("="*60)
        for i, result in enumerate(results[:3], 1):
            print(f"\n{i}. {result.municipality} — {result.title[:50]}")
            print(f"   Score: {result.relevance_score} | Type: {result.lead_type.upper()}")
            print(f"   Signals: {', '.join(result.signal_labels_found)}")
            print(f"   URL: {result.url}")

    # Summary
    print("\n" + "="*60)
    print("PIPELINE TEST SUMMARY")
    print("="*60)
    print(f"✓ Cities tested: {len(utah_munis)}")
    print(f"✓ Sources discovered: {len(all_sources)}")
    print(f"✓ Documents scraped: {len(all_docs)}")
    print(f"✓ Leads identified: {len(results)} (🔥{hot} 🟡{warm} 🔵{cold})")

    if len(all_sources) == 0:
        print("\n⚠️  ISSUE: Discovery engine found no sources")
        print("   → Fix URL patterns in src/signals.py")
    elif len(all_docs) == 0:
        print("\n⚠️  ISSUE: Scraper extracted no documents")
        print("   → Fix scraping logic in src/scraper.py")
    elif len(results) == 0:
        print("\n⚠️  No leads found, but pipeline is working")
        print("   → This could be normal if no ERP signals in recent docs")
    else:
        print("\n✅ PIPELINE IS WORKING!")

    print("="*60)

if __name__ == "__main__":
    main()
