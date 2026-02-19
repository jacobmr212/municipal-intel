"""
Comprehensive CO and ID source discovery.

Research findings (Feb 2026):
- Colorado: No centralized state portal. DLG e-filing portal requires login.
  Large cities use custom platforms (Granicus, PrimeGov, etc.).
  Many DB domains are wrong — this script fixes them.
- Idaho: townhall.idaho.gov is state agencies ONLY (no municipal govts).
  Cities primarily use CivicPlus or plain HTML.

Strategy:
1. Fix incorrect domains for cities where DB domain doesn't match reality
2. Seed known verified sources for large cities with custom platforms
3. Run expanded URL-pattern discovery for remaining no-source cities
4. Also scan existing-source cities for additional source types

Run:
    DATABASE_URL=... python3 scripts/discover_co_id_sources.py [--states CO ID]
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
from src.database import SessionLocal, Municipality, MunicipalSource

# ── Domain fixes: DB has wrong domain → correct resolved URL ─────────────────
# Format: (city_name, state) → correct_base_url
DOMAIN_FIXES = {
    # Colorado — DB has wrong domain → correct base URL
    ("Greeley", "CO"): "https://greeleyco.gov",              # DB: greeleygov.com
    ("Broomfield", "CO"): "https://broomfield.org",           # DB: broomfieldcity.org (DNS fail)
    ("Windsor", "CO"): "https://windsorgov.com",              # DB: windsorcity.org (DNS fail)
    ("Englewood", "CO"): "https://www.englewoodco.gov",       # DB: englewoodcity.org (DNS fail)
    ("Northglenn", "CO"): "https://www.northglenn.org",       # DB: northglenncity.org (DNS fail)
    ("Brighton", "CO"): "https://brightonco.gov",             # DB: brightoncity.org → Brighton MI
    ("Erie", "CO"): "https://www.erieco.gov",                 # DB: eriecity.org
    ("Wheat Ridge", "CO"): "https://www.ci.wheatridge.co.us", # DB: wheatridgecity.org
    ("Fruita", "CO"): "https://www.fruita.org",               # DB: fruitacity.org
    ("Monument", "CO"): "https://www.townofmonument.org",     # DB: monumentcity.org
    ("Wellington", "CO"): "https://www.wellingtoncolorado.gov",# DB: wellingtoncity.org
    ("Eagle", "CO"): "https://www.townofeagle.org",           # DB: eaglecity.org
    ("Sterling", "CO"): "https://www.sterlingcolo.com",       # DB: sterlingcity.org
    ("Fountain", "CO"): "https://fountain.colorado.gov",      # DB: fountaincity.org
    ("Golden", "CO"): "https://www.cityofgolden.gov",         # DB: goldencity.org
    ("Evans", "CO"): "https://www.evanscolorado.gov",         # DB: evanscity.org
    # Idaho — DB has wrong domain → correct base URL
    ("Post Falls", "ID"): "https://www.postfalls.gov",        # DB: postfallsidaho.org
    ("Chubbuck", "ID"): "https://cityofchubbuck.us",          # DB: chubbuckcity.org
    ("Hayden", "ID"): "https://www.haydenidaho.us",           # DB: haydencity.org
    ("Preston", "ID"): "https://www.prestonidaho.org",        # DB: prestoncity.org
}

# ── Known verified sources: large cities with custom/non-standard platforms ──
# Format: (city_name, state) → list of {url, platform, source_type, confidence}
# These are manually verified via web research.
KNOWN_SOURCES = {
    # ── Colorado (large cities with non-standard platforms) ───────────────────
    ("Denver", "CO"): [{
        "url": "https://denvergov.org/Public-Meetings",
        "platform": "granicus", "source_type": "meeting_minutes", "confidence": 0.95,
        "pattern": "known_direct",
    }],
    ("Aurora", "CO"): [{
        "url": "https://www.auroragov.org/city_hall/mayor___city_council/council_meetings",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.90,
        "pattern": "known_direct",
    }],
    ("Lakewood", "CO"): [{
        "url": "https://www.lakewoodco.gov/City-Hall/City-Council/City-Council/City-Council-Upcoming-Meetings",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.90,
        "pattern": "known_direct",
    }],
    ("Thornton", "CO"): [{
        # PrimeGov portal is the actual document hub (city's Drupal page just links here)
        "url": "https://thorntonco.primegov.com/public/portal",
        "platform": "primegov", "source_type": "meeting_minutes", "confidence": 0.95,
        "pattern": "known_direct",
    }],
    ("Greeley", "CO"): [{
        "url": "https://greeleyco.gov/government/city-administration/city-council",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.90,
        "pattern": "known_direct",
    }],
    ("Broomfield", "CO"): [{
        "url": "https://broomfield.org/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.95,
        "pattern": "known_direct",
    }],
    ("Loveland", "CO"): [{
        # CivicWeb portal — city's own site returns 403
        "url": "https://cilovelandco.civicweb.net/Portal/MeetingTypeList.aspx",
        "platform": "civicweb", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Windsor", "CO"): [{
        "url": "https://windsorgov.com/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.95,
        "pattern": "known_direct",
    }],
    ("Englewood", "CO"): [{
        "url": "https://www.englewoodco.gov/government/city-council",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.90,
        "pattern": "known_direct",
    }],
    ("Brighton", "CO"): [{
        "url": "https://brightonco.gov/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Wheat Ridge", "CO"): [{
        "url": "https://www.ci.wheatridge.co.us/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Erie", "CO"): [{
        "url": "https://www.erieco.gov/1134/View",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.88,
        "pattern": "known_direct",
    }],
    ("Wellington", "CO"): [{
        "url": "https://www.wellingtoncolorado.gov/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Fruita", "CO"): [{
        "url": "https://www.fruita.org/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Monument", "CO"): [{
        "url": "https://www.townofmonument.org/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Eagle", "CO"): [{
        "url": "https://www.townofeagle.org/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Sterling", "CO"): [{
        "url": "https://www.sterlingcolo.com/government/city_council/city_council_minutes.php",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.88,
        "pattern": "known_direct",
    }],
    ("Golden", "CO"): [{
        "url": "https://goldenco.granicus.com/ViewPublisher.php?view_id=2",
        "platform": "granicus", "source_type": "meeting_minutes", "confidence": 0.93,
        "pattern": "known_direct",
    }],
    ("Evans", "CO"): [{
        "url": "https://www.evanscolorado.gov/your-government/city-council/agendas-and-minutes/",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.88,
        "pattern": "known_direct",
    }],
    ("Fountain", "CO"): [{
        "url": "https://fountain.colorado.gov/government/city-council",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.88,
        "pattern": "known_direct",
    }],
    # ── Idaho (cities with no sources, non-standard platforms) ────────────────
    ("Rexburg", "ID"): [{
        "url": "https://www.rexburg.org/minutes-and-agendas",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.90,
        "pattern": "known_direct",
    }],
    ("Post Falls", "ID"): [{
        "url": "https://www.postfalls.gov/AgendaCenter",
        "platform": "civicplus", "source_type": "meeting_minutes", "confidence": 0.92,
        "pattern": "known_direct",
    }],
    ("Chubbuck", "ID"): [{
        "url": "https://cityofchubbuck.us/city-council/",
        "platform": "html", "source_type": "meeting_minutes", "confidence": 0.85,
        "pattern": "known_direct",
    }],
}

# ── Bad domain fragments (domain parkers, wrong-state cities) ─────────────────
BAD_DOMAIN_FRAGMENTS = [
    "hugedomains.com", "domainmarket.com", "domains.atom.com",
    "afternic.com", "godaddy.com", "sedo.com", "namecheap.com",
    "coinforcesupply.com",      # Lakewood CO bad domain
    "brightoncitymi.gov",       # Brighton MI, not CO
    "brightoncity.org",         # Resolves to Brighton MI
]

DOMAIN_PARKERS = [
    "buy this domain", "domain for sale", "this domain",
    "hugedomains", "domainmarket", "afternic", "sedo",
    "this web page is parked",
]

MEETING_INDICATORS = [
    "meeting", "agenda", "minutes", "council",
    "session", "public hearing", "regular meeting",
    "board meeting", "commission meeting", "city council",
]

# ── Expanded URL patterns (CivicPlus + generic paths) ─────────────────────────
URL_PATTERNS = [
    # CivicPlus (most common for small/mid cities)
    "/AgendaCenter",
    "/agendacenter",
    "/Archive.aspx",
    "/archive.aspx",
    # Generic meeting paths
    "/agendas-minutes",
    "/agendas-and-minutes",
    "/agendas",
    "/minutes",
    "/minutes-and-agendas",
    "/meeting-minutes",
    "/meetings",
    "/city-council",
    "/city-council/meetings",
    "/city-council/agendas-and-minutes",
    "/council/meetings",
    "/council-meetings",
    "/city-council-meetings",
    "/government/meetings",
    "/government/agendas",
    "/government/city-council",
    "/government/mayor-council",
    "/city-government/city-council",
    "/city-hall/city-council",
    "/citycouncil",
    "/citycouncil/page/city-council-agenda",
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
    "/council-minutes",
    # iCompass
    "/meetings/search",
    # Granicus
    "/Public-Meetings",
]


def is_domain_parker(html: str, url: str) -> bool:
    for bad in BAD_DOMAIN_FRAGMENTS:
        if bad in url.lower():
            return True
    html_lower = html.lower()
    for marker in DOMAIN_PARKERS:
        if marker in html_lower:
            return True
    return False


def detect_platform(html: str, url: str) -> str:
    html_lower = html.lower()
    url_lower = url.lower()
    if "agendacenter" in url_lower or "civicplus" in html_lower or "civicengage" in html_lower:
        return "civicplus"
    elif "granicus" in html_lower or "legistar" in html_lower:
        return "granicus"
    elif "boarddocs" in html_lower:
        return "boarddocs"
    elif "icompass" in html_lower:
        return "icompass"
    elif "primegov" in html_lower:
        return "primegov"
    elif "municipalimpact" in url_lower:
        return "municipalimpact"
    return "html"


def check_url(session: requests.Session, url: str) -> tuple[bool, str, str]:
    """
    Check if URL has meeting content.
    Returns (found: bool, resolved_url: str, platform: str)
    """
    try:
        r = session.get(url, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return False, url, "html"

        content_type = r.headers.get("content-type", "")
        if "html" not in content_type:
            return False, url, "html"

        html = r.text
        resolved = r.url

        if is_domain_parker(html, resolved):
            return False, resolved, "html"

        html_lower = html.lower()
        count = sum(1 for ind in MEETING_INDICATORS if ind in html_lower)
        if count < 2:
            return False, resolved, "html"

        platform = detect_platform(html, resolved)
        return True, resolved, platform

    except Exception:
        return False, url, "html"


def add_source(db, city, url: str, platform: str, source_type: str,
               confidence: float, pattern: str) -> bool:
    """Add a source to the DB. Returns True if newly added."""
    existing = db.query(MunicipalSource).filter_by(url=url).first()
    if existing:
        return False
    source = MunicipalSource(
        municipality_id=city.id,
        url=url,
        source_type=source_type,
        platform=platform,
        confidence=confidence,
        discovered_by_pattern=pattern,
    )
    db.add(source)
    db.commit()
    return True


def seed_known_sources(db, stats: dict) -> int:
    """Directly add known-verified sources for large cities with custom platforms."""
    added = 0
    for (city_name, state), sources in KNOWN_SOURCES.items():
        city = (
            db.query(Municipality)
            .filter_by(name=city_name, state=state)
            .first()
        )
        if not city:
            print(f"  [SKIP] {city_name}, {state}: not found in DB")
            continue

        for src_info in sources:
            if add_source(
                db, city,
                url=src_info["url"],
                platform=src_info["platform"],
                source_type=src_info["source_type"],
                confidence=src_info["confidence"],
                pattern=src_info["pattern"],
            ):
                added += 1
                print(f"  ✓ Seeded {city_name}, {state}: {src_info['url'][:70]} [{src_info['platform']}]")
            else:
                print(f"  ~ Already exists: {city_name}, {state}")

    stats["known_seeded"] = added
    return added


def probe_cities(state: str, db, session: requests.Session, stats: dict) -> int:
    """Probe URL patterns for cities with no sources (or with few sources)."""
    added = 0

    cities = (
        db.query(Municipality)
        .filter_by(state=state, domain_status="verified")
        .order_by(Municipality.population.desc())
        .all()
    )

    # Only probe cities with zero sources (already-sourced cities handled by seed)
    no_source_cities = [
        c for c in cities
        if db.query(MunicipalSource).filter_by(municipality_id=c.id).count() == 0
    ]

    print(f"\n{state}: {len(no_source_cities)} verified cities still needing sources")
    print("=" * 60)

    for city in no_source_cities:
        # Apply domain fix if known
        fix = DOMAIN_FIXES.get((city.name, state))
        if fix:
            base_url = fix
            print(f"  [{city.name} ({city.population:,})] DOMAIN-FIX → {base_url}")
        else:
            # Skip cities where DB domain is a bad/wrong domain
            base_url = (city.resolved_url or f"https://{city.domain}").rstrip("/")
            bad = any(frag in base_url.lower() for frag in BAD_DOMAIN_FRAGMENTS)
            if bad:
                print(f"  [{city.name}] SKIP (bad domain: {base_url[:60]})")
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue

            if not city.domain:
                print(f"  [{city.name}] SKIP (no domain)")
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue

            print(f"  [{city.name} ({city.population:,})] {base_url[:60]}")

        found = False
        for pattern in URL_PATTERNS:
            url = f"{base_url}{pattern}"
            ok, resolved_url, platform = check_url(session, url)

            if ok:
                if add_source(db, city, resolved_url, platform, "meeting_minutes",
                              confidence=0.9 if platform == "civicplus" else 0.85 if platform == "granicus" else 0.7,
                              pattern=pattern):
                    added += 1
                    print(f"    ✓ {pattern} → {resolved_url[:70]} [{platform}]")
                found = True
                break

            time.sleep(0.25)

        if not found:
            print(f"    ✗ No meeting page found")

        stats["probed"] = stats.get("probed", 0) + 1

    return added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", nargs="+", default=["CO", "ID"])
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "MunicipalIntel/1.0 (Government Research)"
    session.headers["Accept"] = "text/html,*/*;q=0.8"

    db = SessionLocal()
    stats = {}

    try:
        # Step 1: Seed known sources for large cities
        print("\n" + "=" * 60)
        print("STEP 1: Seeding known verified sources for large cities")
        print("=" * 60)
        known_added = seed_known_sources(db, stats)
        print(f"\n  Added {known_added} known sources")

        # Step 2: Probe URL patterns for remaining no-source cities
        total_probed = 0
        for state in args.states:
            if state not in ("CO", "ID"):
                print(f"  [SKIP] {state}: not in scope for this script")
                continue
            added = probe_cities(state, db, session, stats)
            total_probed += added
            print(f"\n  {state}: {added} sources added via pattern probing")

        print("\n" + "=" * 60)
        print(f"TOTAL: {known_added} known + {total_probed} probed = {known_added + total_probed} new sources")
        print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
