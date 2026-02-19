"""
Find procurement/bids pages for existing CO and ID municipal sources.

Each city with a meeting minutes source likely also has:
- A bids/procurement page (active RFPs = direct sales leads)
- A budget documents page (financial planning signals)

These are high-value for ERP sales intelligence.

Run:
    DATABASE_URL=... python3 scripts/discover_procurement_sources.py [--states CO ID]
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
from src.database import SessionLocal, Municipality, MunicipalSource

# Procurement URL patterns (ordered by likelihood)
PROCUREMENT_PATTERNS = [
    "/bids-procurement",
    "/bids",
    "/Bids.aspx",
    "/purchasing",
    "/procurement",
    "/rfp",
    "/government/purchasing",
    "/government/procurement",
    "/city-clerk/bids",
    "/finance/purchasing",
    "/finance/bids",
    "/business/bids",
    "/business/procurement",
    "/doing-business/bids",
    "/doing-business/procurement",
    "/how-do-i/bid-on-a-city-contract",
]

# Budget URL patterns
BUDGET_PATTERNS = [
    "/budget",
    "/government/budget",
    "/finance/budget",
    "/city-hall/budget",
    "/city-budget",
    "/annual-budget",
    "/proposed-budget",
    "/finance",
    "/government/finance",
]

PROCUREMENT_INDICATORS = [
    "bid", "rfp", "rfq", "procurement", "vendor",
    "contract", "solicitation", "invitation to bid",
    "request for proposal", "request for quote",
]

BUDGET_INDICATORS = [
    "budget", "appropriation", "fiscal year", "revenue",
    "expenditure", "fund", "financial",
]

BAD_DOMAIN_FRAGMENTS = [
    "hugedomains.com", "domainmarket.com", "domains.atom.com",
    "afternic.com", "godaddy.com", "sedo.com", "namecheap.com",
    "coinforcesupply.com", "brightoncitymi.gov", "brightoncity.org",
]

DOMAIN_PARKERS = [
    "buy this domain", "domain for sale", "hugedomains",
    "domainmarket", "afternic", "sedo", "this web page is parked",
]


def is_valid_page(resp) -> bool:
    """Check if a response is a valid municipal content page."""
    if resp.status_code != 200:
        return False
    if "html" not in resp.headers.get("content-type", ""):
        return False
    html = resp.text.lower()
    for marker in DOMAIN_PARKERS:
        if marker in html:
            return False
    for frag in BAD_DOMAIN_FRAGMENTS:
        if frag in resp.url.lower():
            return False
    if "/error" in resp.url.lower():
        return False
    return True


def extract_base_url(source_url: str) -> str:
    """Extract the base URL from a source URL."""
    # Strip known path suffixes to get the domain root
    for suffix in ["/AgendaCenter", "/Archive.aspx", "/government", "/city-council",
                   "/agendas", "/minutes", "/meetings", "/citycouncil"]:
        if suffix.lower() in source_url.lower():
            idx = source_url.lower().find(suffix.lower())
            return source_url[:idx]

    # For Granicus subdomains (goldenco.granicus.com), skip
    if "granicus.com" in source_url or "civicweb.net" in source_url or "primegov.com" in source_url:
        return None

    # Just use the scheme + netloc
    from urllib.parse import urlparse
    parsed = urlparse(source_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def check_source(session: requests.Session, url: str, indicators: list[str]) -> tuple[bool, int]:
    """Check if URL has the specified indicators. Returns (valid, count)."""
    try:
        r = session.get(url, timeout=10, allow_redirects=True)
        if not is_valid_page(r):
            return False, 0
        html = r.text.lower()
        count = sum(1 for ind in indicators if ind in html)
        return count >= 2, count
    except Exception:
        return False, 0


def discover_additional_sources(state: str, db, session: requests.Session) -> dict:
    """Find procurement and budget sources for cities that already have meeting sources."""
    stats = {"procurement": 0, "budget": 0, "skipped": 0}

    cities = (
        db.query(Municipality)
        .filter_by(state=state, domain_status="verified")
        .order_by(Municipality.population.desc())
        .all()
    )

    print(f"\n{state}: Finding additional sources for {len(cities)} cities")
    print("=" * 60)

    for city in cities:
        sources = db.query(MunicipalSource).filter_by(municipality_id=city.id).all()

        if not sources:
            continue  # Skip cities with no sources at all

        # Build base URL from first meeting_minutes source
        mm_source = next((s for s in sources if s.source_type == "meeting_minutes"), None)
        if not mm_source:
            continue

        base_url = extract_base_url(mm_source.url)
        if not base_url:
            continue

        # Check if already has procurement source
        has_procurement = any(s.source_type == "procurement" for s in sources)
        has_budget = any(s.source_type == "budget" for s in sources)

        city_added = 0

        # Look for procurement source
        if not has_procurement:
            for pattern in PROCUREMENT_PATTERNS:
                url = f"{base_url}{pattern}"
                ok, count = check_source(session, url, PROCUREMENT_INDICATORS)
                if ok:
                    existing = db.query(MunicipalSource).filter_by(url=url).first()
                    if not existing:
                        src = MunicipalSource(
                            municipality_id=city.id,
                            url=url,
                            source_type="procurement",
                            platform="html",
                            confidence=0.80,
                            discovered_by_pattern=f"procurement{pattern}",
                        )
                        db.add(src)
                        db.commit()
                        stats["procurement"] += 1
                        city_added += 1
                        print(f"  ✓ PROCUREMENT {city.name}, {state}: {url[:70]}")
                    break
                time.sleep(0.2)

        # Look for budget source
        if not has_budget:
            for pattern in BUDGET_PATTERNS:
                url = f"{base_url}{pattern}"
                ok, count = check_source(session, url, BUDGET_INDICATORS)
                if ok:
                    existing = db.query(MunicipalSource).filter_by(url=url).first()
                    if not existing:
                        src = MunicipalSource(
                            municipality_id=city.id,
                            url=url,
                            source_type="budget",
                            platform="html",
                            confidence=0.75,
                            discovered_by_pattern=f"budget{pattern}",
                        )
                        db.add(src)
                        db.commit()
                        stats["budget"] += 1
                        city_added += 1
                        print(f"  ✓ BUDGET {city.name}, {state}: {url[:70]}")
                    break
                time.sleep(0.2)

        if city_added == 0:
            pass  # Silently skip cities where nothing new was found

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", nargs="+", default=["CO", "ID"])
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "MunicipalIntel/1.0 (Government Research)"
    session.headers["Accept"] = "text/html,*/*;q=0.8"

    db = SessionLocal()
    total_proc = 0
    total_budget = 0

    try:
        for state in args.states:
            stats = discover_additional_sources(state, db, session)
            total_proc += stats["procurement"]
            total_budget += stats["budget"]
            print(f"\n  {state}: {stats['procurement']} procurement + {stats['budget']} budget sources found")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_proc} procurement + {total_budget} budget = {total_proc + total_budget} new sources")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
