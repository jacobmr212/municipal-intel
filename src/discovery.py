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

from .signals import URL_PATTERNS

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

    def __init__(self, request_delay: float = 1.5, timeout: int = 15):
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

    def discover_municipality(self, name: str, state: str, domain: str,
                               population: int = 0, progress_callback=None) -> list[DiscoveredSource]:
        """
        Attempt to discover meeting minutes pages for a single municipality.
        Tries common URL patterns against the municipality's domain.
        """
        discovered = []
        base_urls = [
            f"https://www.{domain}",
            f"https://{domain}",
        ]

        for base_url in base_urls:
            for pattern in URL_PATTERNS:
                url = f"{base_url}{pattern}"
                time.sleep(self.delay)

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
                    logger.info(f"  ✓ Found: {found_url} ({source_type})")

                    # If we found a high-confidence source, we can stop
                    if confidence >= 0.85:
                        return discovered

        if not discovered:
            # Try the domain root as a fallback — some cities have meetings on the homepage
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
                    break

        return discovered

    def discover_state(self, municipalities: list[dict], state_abbr: str,
                        progress_callback=None) -> list[DiscoveredSource]:
        """
        Discover meeting minutes sources for all municipalities in a state.
        """
        all_sources = []
        total = len(municipalities)

        for i, muni in enumerate(municipalities):
            name = muni["name"]
            domain = muni.get("domain", "")
            population = muni.get("population", 0)

            if not domain:
                logger.warning(f"  No domain for {name}, {state_abbr} — skipping")
                continue

            logger.info(f"[{i + 1}/{total}] Discovering sources for {name}, {state_abbr}...")

            if progress_callback:
                progress_callback(i, total, f"Discovering: {name}, {state_abbr}")

            sources = self.discover_municipality(name, state_abbr, domain, population)
            all_sources.extend(sources)

        # Sort by confidence (highest first), then population (largest first)
        all_sources.sort(key=lambda s: (s.confidence, s.population), reverse=True)

        logger.info(f"Discovery complete: {len(all_sources)} sources found for {len(municipalities)} municipalities")
        return all_sources
