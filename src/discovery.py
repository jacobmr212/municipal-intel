"""
Source Discovery Engine
Automatically discovers meeting minutes pages for municipalities by probing
common URL patterns used by municipal website platforms.
"""

import time
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .signals import URL_PATTERNS, PROCUREMENT_PATTERNS

logger = logging.getLogger(__name__)


class DiscoveredSource:
    """A discovered meeting minutes source."""

    def __init__(self, municipality: str, state: str, url: str,
                 source_type: str, confidence: float, population: int = 0):
        self.municipality = municipality
        self.state = state
        self.url = url
        self.source_type = source_type  # "civicplus", "granicus", "html", "unknown"
        self.confidence = confidence    # 0.0 - 1.0
        self.population = population

    def __repr__(self):
        return f"<Source: {self.municipality}, {self.state} — {self.url} ({self.source_type}, conf={self.confidence:.0%})>"


class SourceDiscovery:
    """Discovers meeting minutes pages for municipalities."""

    def __init__(self, request_delay: float = 1.0, timeout: int = 8):
        self.delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MunicipalIntel/1.0 (Government Meeting Research Tool)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _check_url(self, url: str) -> Optional[tuple[str, str]]:
        """
        Check if a URL exists and appears to contain meeting content.
        Returns (url, source_type) or None.
        """
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None

            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return None

            html_lower = response.text.lower()

            # Check for meeting-related content
            meeting_indicators = [
                "meeting", "agenda", "minutes", "council",
                "session", "public hearing", "regular meeting",
                "board meeting", "commission meeting",
            ]

            indicator_count = sum(1 for ind in meeting_indicators if ind in html_lower)
            if indicator_count < 2:
                return None

            # Identify platform
            source_type = "html"
            if "agendacenter" in url.lower() or "civicplus" in html_lower or "civicengage" in html_lower:
                source_type = "civicplus"
            elif "granicus" in html_lower or "legistar" in html_lower:
                source_type = "granicus"
            elif "boarddocs" in html_lower:
                source_type = "boarddocs"

            return (response.url, source_type)

        except (requests.exceptions.RequestException, Exception):
            return None

    def _try_domain_alternatives(self, name: str, state: str, provided_domain: str) -> list[str]:
        """
        Generate alternative domain patterns when the provided domain doesn't work.
        Many municipal databases have outdated or incorrect domains - this tries common patterns.
        """
        city_slug = name.lower().replace(" ", "").replace("-", "").replace(".", "")
        state_lower = state.lower()

        # Common municipal domain patterns (ordered by likelihood)
        alternatives = [
            f"cityof{city_slug}.com",
            f"cityof{city_slug}.org",
            f"{city_slug}{state_lower}.gov",
            f"{city_slug}.{state_lower}.us",
            f"ci.{city_slug}.{state_lower}.us",
            f"{city_slug}city.org",
            f"{city_slug}city.com",
            f"cityof{city_slug}.gov",
        ]

        # Quick test which alternative domains actually exist
        working_domains = []
        for alt_domain in alternatives:
            try:
                response = self.session.head(f"https://{alt_domain}", timeout=3, allow_redirects=True)
                if response.status_code < 400:
                    working_domains.append(alt_domain)
                    logger.info(f"  Found alternative domain: {alt_domain} (replacing {provided_domain})")
                    break  # Stop after finding first working domain
            except:
                continue

        return working_domains

    def discover_municipality(self, name: str, state: str, domain: str,
                               population: int = 0, progress_callback=None) -> list[DiscoveredSource]:
        """
        Attempt to discover meeting minutes pages for a single municipality.
        Tries common URL patterns against the municipality's domain.
        """
        discovered = []

        # Extract city name for third-party platform checks
        city_slug = name.lower().replace(" ", "").replace("-", "")

        # Build list of base URLs to check (own domain + third-party platforms)
        base_urls = [
            f"https://www.{domain}",
            f"https://{domain}",
        ]

        # Try provided domain first
        domain_works = False
        try:
            response = self.session.head(base_urls[0], timeout=3, allow_redirects=True)
            if response.status_code < 400:
                domain_works = True
        except:
            pass

        # If provided domain doesn't work, try alternatives
        if not domain_works:
            logger.info(f"  Provided domain {domain} not responding — trying alternatives...")
            alt_domains = self._try_domain_alternatives(name, state, domain)
            if alt_domains:
                # Replace base_urls with working alternative
                base_urls = [f"https://www.{alt_domains[0]}", f"https://{alt_domains[0]}"]

        # Add third-party platform subdomains
        third_party_platforms = [
            # Meeting minutes platforms
            f"https://{city_slug}.civicweb.net",
            f"https://{city_slug}.legistar.com",
            f"https://{city_slug}.granicus.com",
            f"https://{city_slug}.boarddocs.com",
            f"https://{city_slug}.novusagenda.com",
            f"https://{city_slug}-{state.lower()}.municode.com",
            # Procurement/transparency platforms
            f"https://{city_slug}.primegov.com",
            f"https://{city_slug}.opengov.com",
            # Alternative city name formats
            f"https://{city_slug}{state.lower()}.civicweb.net",
            f"https://{city_slug}{state.lower()}.legistar.com",
        ]

        # Try most common patterns first (CivicPlus AgendaCenter is #1)
        priority_patterns = [
            "/AgendaCenter", "/agendacenter",
            "/Archive.aspx", "/archive.aspx",  # CivicPlus archive
            "/DocumentCenter", "/documentcenter",  # CivicPlus docs
            "/Meetings.aspx", "/Calendar.aspx",  # Granicus
            "/meetings", "/city-council/meetings", "/council/meetings",
        ]
        remaining_patterns = [p for p in URL_PATTERNS if p not in priority_patterns]
        ordered_patterns = priority_patterns + remaining_patterns

        checked_count = 0

        # First: Try own domain with common patterns (adaptive limit based on city size)
        # Larger cities have more complex site structures, so check more patterns
        if population >= 50000:
            max_patterns_to_check = 16  # Large cities
        elif population >= 10000:
            max_patterns_to_check = 12  # Medium cities
        else:
            max_patterns_to_check = 8   # Small cities
        for base_url in base_urls:
            for pattern in ordered_patterns:
                # Stop after reaching population-based pattern limit
                if checked_count >= max_patterns_to_check:
                    logger.info(f"  Checked {checked_count} patterns — moving on")
                    break

                url = f"{base_url}{pattern}"

                # Minimal delay to be respectful, but fast
                if checked_count > 0:
                    time.sleep(self.delay)
                checked_count += 1

                result = self._check_url(url)
                if result:
                    found_url, source_type = result

                    # Avoid duplicates
                    if any(d.url == found_url for d in discovered):
                        continue

                    # Higher confidence for platform-specific sources
                    confidence = 0.7
                    if source_type == "civicplus":
                        confidence = 0.9
                    elif source_type == "granicus":
                        confidence = 0.85

                    source = DiscoveredSource(
                        municipality=name,
                        state=state,
                        url=found_url,
                        source_type=source_type,
                        confidence=confidence,
                        population=population,
                    )
                    discovered.append(source)
                    logger.info(f"  ✓ Found: {found_url} ({source_type}) — pattern: {pattern}")

                    # If we found a high-confidence source, stop immediately
                    if confidence >= 0.85:
                        logger.info(f"  High confidence source found — stopping search for {name}")
                        return discovered

                    # If we found any source and checked 5+ patterns, stop
                    if len(discovered) >= 1 and checked_count >= 5:
                        logger.info(f"  Source found after {checked_count} checks — stopping")
                        return discovered

            # Break outer loop too if we hit the limit
            if checked_count >= max_patterns_to_check:
                break

        # Second: Try third-party platforms if nothing found on own domain
        if not discovered:
            logger.info(f"  Checking third-party platforms for {name}...")
            for platform_url in third_party_platforms:
                if checked_count > 0:
                    time.sleep(self.delay)
                checked_count += 1

                result = self._check_url(platform_url)
                if result:
                    found_url, source_type = result

                    # Third-party platforms are high confidence
                    confidence = 0.9
                    source = DiscoveredSource(
                        municipality=name,
                        state=state,
                        url=found_url,
                        source_type=source_type,
                        confidence=confidence,
                        population=population,
                    )
                    discovered.append(source)
                    logger.info(f"  ✓ Found on third-party platform: {found_url}")
                    return discovered

        # Third: Try the domain root as a fallback
        if not discovered:
            logger.info(f"  Trying domain root fallback for {name}...")
            for base_url in base_urls:
                result = self._check_url(base_url)
                if result:
                    found_url, source_type = result
                    discovered.append(DiscoveredSource(
                        municipality=name,
                        state=state,
                        url=found_url,
                        source_type=source_type,
                        confidence=0.3,
                        population=population,
                    ))
                    logger.info(f"  ~ Found (low confidence): {found_url}")
                    break

        # Log if nothing found
        if not discovered:
            logger.warning(f"  ✗ No sources found for {name}, {state} ({domain}) — checked {checked_count} URLs")

        return discovered

    def discover_procurement(self, name: str, state: str, domain: str,
                             population: int = 0) -> list[DiscoveredSource]:
        """
        Discover procurement/bidding pages for a municipality.
        Returns list of procurement sources found.
        """
        discovered = []
        base_urls = [
            f"https://www.{domain}",
            f"https://{domain}",
        ]

        checked_count = 0
        for base_url in base_urls:
            for pattern in PROCUREMENT_PATTERNS:
                url = f"{base_url}{pattern}"

                if checked_count > 0:
                    time.sleep(self.delay)
                checked_count += 1

                try:
                    response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                    if response.status_code != 200:
                        continue

                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type:
                        continue

                    html_lower = response.text.lower()

                    # Check for procurement-related content
                    procurement_indicators = [
                        "bid", "rfp", "request for proposal", "procurement",
                        "solicitation", "vendor", "purchasing", "opportunity",
                    ]

                    indicator_count = sum(1 for ind in procurement_indicators if ind in html_lower)
                    if indicator_count < 2:
                        continue

                    # Found a procurement page
                    source = DiscoveredSource(
                        municipality=name,
                        state=state,
                        url=response.url,
                        source_type="procurement",
                        confidence=0.85,
                        population=population,
                    )
                    discovered.append(source)
                    logger.info(f"  ✓ Found procurement portal: {response.url}")

                    # Stop after finding one procurement portal
                    return discovered

                except (requests.exceptions.RequestException, Exception):
                    continue

        if not discovered:
            logger.info(f"  ✗ No procurement portal found for {name}, {state}")

        return discovered

    def discover_state(self, municipalities: list[dict], state_abbr: str,
                        progress_callback=None) -> list[DiscoveredSource]:
        """
        Discover meeting minutes sources for all municipalities in a state.
        """
        all_sources = []
        total = len(municipalities)
        cities_found = set()
        cities_skipped_no_domain = []

        for i, muni in enumerate(municipalities):
            name = muni["name"]
            domain = muni.get("domain", "")
            population = muni.get("population", 0)

            if not domain:
                logger.warning(f"  No domain for {name}, {state_abbr} — skipping")
                cities_skipped_no_domain.append(name)
                continue

            logger.info(f"[{i + 1}/{total}] Discovering sources for {name}, {state_abbr}...")

            if progress_callback:
                progress_callback(i, total, f"Discovering: {name}, {state_abbr}")

            sources = self.discover_municipality(name, state_abbr, domain, population)
            if sources:
                cities_found.add(name)
            all_sources.extend(sources)

        # Sort by confidence (highest first), then population (largest first)
        all_sources.sort(key=lambda s: (s.confidence, s.population), reverse=True)

        # Calculate and log hit rate
        cities_with_domains = total - len(cities_skipped_no_domain)
        hit_rate = (len(cities_found) / cities_with_domains * 100) if cities_with_domains > 0 else 0

        logger.info("=" * 60)
        logger.info(f"DISCOVERY SUMMARY for {state_abbr}")
        logger.info(f"  Total municipalities: {total}")
        logger.info(f"  Sources found: {len(all_sources)} from {len(cities_found)} cities")
        logger.info(f"  Hit rate: {hit_rate:.1f}% ({len(cities_found)}/{cities_with_domains})")
        if cities_skipped_no_domain:
            logger.info(f"  Skipped (no domain): {len(cities_skipped_no_domain)}")
        logger.info("=" * 60)

        return all_sources
