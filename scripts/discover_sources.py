"""
Targeted source discovery for states where enrichment found 0 sources.

Tries a comprehensive set of URL patterns against all verified cities
with no sources in CO, ID, MT, WY, NV, NM.

Run:
    DATABASE_URL=... python3 scripts/discover_sources.py [--states CO ID MT]
"""
import os, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
from datetime import datetime
from src.database import SessionLocal, Municipality, MunicipalSource

# ── Domain blocker list (domain parkers, brokers, wrong hosts) ──────────────
BAD_DOMAIN_FRAGMENTS = [
    "hugedomains.com", "domainmarket.com", "domains.atom.com",
    "afternic.com", "godaddy.com", "sedo.com", "namecheap.com",
    "coinforcesupply.com",  # Lakewood CO bad domain
    "brightoncitymi.gov",   # Brighton MI not CO
]

# ── Comprehensive URL patterns (ordered by hit likelihood) ──────────────────
URL_PATTERNS = [
    # CivicPlus (most common platform for small cities)
    "/AgendaCenter",
    "/agendacenter",
    "/Archive.aspx",
    "/archive.aspx",
    # Generic meeting paths
    "/agendas-minutes",
    "/agendas-and-minutes",
    "/agendas",
    "/minutes",
    "/meeting-minutes",
    "/meetings",
    "/city-council",
    "/city-council/meetings",
    "/council/meetings",
    "/council-meetings",
    "/city-council-meetings",
    "/government/meetings",
    "/government/agendas",
    "/government/city-council",
    "/city-government/city-council",
    "/city-hall/city-council",
    # CivicPlus DocumentCenter
    "/DocumentCenter",
    "/documentcenter",
    # Other platforms
    "/Meetings.aspx",
    "/Calendar.aspx",
    "/calendar.aspx",
    "/publicmeetings",
    "/public-meetings",
    "/meetings-minutes",
    "/council-agendas",
]

MEETING_INDICATORS = [
    "meeting", "agenda", "minutes", "council",
    "session", "public hearing", "regular meeting",
    "board meeting", "commission meeting", "city council",
]

DOMAIN_PARKERS = [
    "buy this domain", "domain for sale", "this domain",
    "hugedomains", "domainmarket", "afternic", "sedo",
    "this web page is parked",
]


def is_domain_parker(html: str, url: str) -> bool:
    """Return True if the resolved URL/content looks like a domain parker."""
    for bad in BAD_DOMAIN_FRAGMENTS:
        if bad in url.lower():
            return True
    html_lower = html.lower()
    for marker in DOMAIN_PARKERS:
        if marker in html_lower:
            return True
    return False


def check_url(session: requests.Session, url: str) -> tuple[bool, str, str]:
    """
    Check if URL has meeting content.
    Returns (found: bool, resolved_url: str, platform: str)
    """
    try:
        r = session.get(url, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return False, url, "html"

        content_type = r.headers.get("content-type", "")
        if "html" not in content_type:
            return False, url, "html"

        html = r.text
        resolved = r.url

        # Reject domain parkers
        if is_domain_parker(html, resolved):
            return False, resolved, "html"

        html_lower = html.lower()
        count = sum(1 for ind in MEETING_INDICATORS if ind in html_lower)
        if count < 2:
            return False, resolved, "html"

        # Detect platform
        platform = "html"
        if "agendacenter" in resolved.lower() or "civicplus" in html_lower or "civicengage" in html_lower:
            platform = "civicplus"
        elif "granicus" in html_lower or "legistar" in html_lower:
            platform = "granicus"
        elif "boarddocs" in html_lower:
            platform = "boarddocs"
        elif "icompass" in html_lower:
            platform = "icompass"
        elif "primegov" in html_lower:
            platform = "primegov"

        return True, resolved, platform

    except Exception:
        return False, url, "html"


def discover_sources_for_state(state: str, db, session: requests.Session) -> dict:
    stats = {"checked": 0, "found": 0, "skipped": 0}

    # Get all verified cities with no sources
    cities = (
        db.query(Municipality)
        .filter(Municipality.state == state, Municipality.domain_status == "verified")
        .order_by(Municipality.population.desc())
        .all()
    )

    no_source_cities = []
    for city in cities:
        source_count = db.query(MunicipalSource).filter_by(municipality_id=city.id).count()
        if source_count == 0:
            no_source_cities.append(city)

    print(f"\n{state}: {len(no_source_cities)} verified cities with no sources")
    print("=" * 60)

    for city in no_source_cities:
        base_url = (city.resolved_url or f"https://{city.domain}").rstrip("/")

        # Skip if base_url is a known bad domain
        bad = False
        for frag in BAD_DOMAIN_FRAGMENTS:
            if frag in base_url.lower():
                bad = True
                break
        if bad:
            print(f"  [{city.name}] SKIP (domain parker: {base_url[:60]})")
            stats["skipped"] += 1
            continue

        print(f"  [{city.name} ({city.population:,})] {base_url[:60]}")
        found = False

        for pattern in URL_PATTERNS:
            url = f"{base_url}{pattern}"
            ok, resolved_url, platform = check_url(session, url)

            if ok:
                # Check if source already exists
                existing = db.query(MunicipalSource).filter_by(url=resolved_url).first()
                if not existing:
                    confidence = 0.9 if platform == "civicplus" else 0.85 if platform == "granicus" else 0.7
                    source = MunicipalSource(
                        municipality_id=city.id,
                        url=resolved_url,
                        source_type="meeting_minutes",
                        platform=platform,
                        confidence=confidence,
                        discovered_by_pattern=pattern,
                    )
                    db.add(source)
                    db.commit()
                    stats["found"] += 1
                    print(f"    ✓ {pattern} → {resolved_url[:70]} [{platform}]")
                    found = True
                    break  # One confirmed source per city is enough
                else:
                    found = True
                    break

            time.sleep(0.3)  # Polite delay

        if not found:
            print(f"    ✗ No sources found")

        stats["checked"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--states", nargs="+",
        default=["CO", "ID", "MT", "WY", "NV", "NM"],
        help="States to process"
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "MunicipalIntel/1.0 (Government Research)"
    session.headers["Accept"] = "text/html,*/*;q=0.8"

    total_found = 0
    total_checked = 0

    for state in args.states:
        db = SessionLocal()
        try:
            stats = discover_sources_for_state(state, db, session)
            total_found += stats["found"]
            total_checked += stats["checked"]
            print(f"\n  {state} summary: {stats['found']} found / {stats['checked']} checked / {stats['skipped']} skipped")
        except Exception as e:
            print(f"ERROR processing {state}: {e}")
        finally:
            db.close()

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_found} new sources found across {total_checked} cities")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
