"""
Enrichment Pipeline for Municipal Intel

This module runs OFFLINE to:
1. Validate municipality domains (verify working URLs, handle redirects)
2. Discover meeting minutes/procurement sources
3. Store results in database for fast scanning

Enrichment happens once per city. Scanning reads from the database.
"""

import time
import logging
from datetime import datetime
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from sqlalchemy.orm import Session

from .database import SessionLocal, Municipality, MunicipalSource
from .signals import URL_PATTERNS, PROCUREMENT_PATTERNS
from .discovery import SourceDiscovery

logger = logging.getLogger(__name__)


class EnrichmentEngine:
    """Enriches municipality data: validates domains, discovers sources."""

    def __init__(self, request_delay: float = 1.0, timeout: int = 8):
        self.delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MunicipalIntel/1.0 (Government Meeting Research Tool)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _try_domain(self, domain: str) -> Optional[str]:
        """
        Try to verify a domain works. Returns resolved URL or None.
        Tests: domain, www.domain, and follows redirects.

        Tries both HEAD and GET requests (some servers block HEAD).
        Logs all failures for debugging.
        """
        variants = [
            f"https://{domain}",
            f"https://www.{domain}",
            f"http://{domain}",
            f"http://www.{domain}",
        ]

        for url in variants:
            # Try HEAD first (faster)
            try:
                response = self.session.head(url, timeout=5, allow_redirects=True)
                if response.status_code < 400:
                    logger.debug(f"      HEAD {url} → {response.status_code} → {response.url}")
                    return response.url
                else:
                    logger.debug(f"      HEAD {url} → {response.status_code} (rejected)")
            except requests.exceptions.SSLError as e:
                logger.debug(f"      HEAD {url} → SSL Error: {str(e)[:80]}")
            except requests.exceptions.Timeout:
                logger.debug(f"      HEAD {url} → Timeout (5s)")
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"      HEAD {url} → Connection Error")
            except Exception as e:
                logger.debug(f"      HEAD {url} → {type(e).__name__}: {str(e)[:80]}")

            # Try GET if HEAD failed (some servers block HEAD)
            try:
                response = self.session.get(url, timeout=5, allow_redirects=True)
                if response.status_code < 400:
                    logger.debug(f"      GET {url} → {response.status_code} → {response.url}")
                    return response.url
                else:
                    logger.debug(f"      GET {url} → {response.status_code} (rejected)")
            except requests.exceptions.SSLError as e:
                logger.debug(f"      GET {url} → SSL Error")
            except requests.exceptions.Timeout:
                logger.debug(f"      GET {url} → Timeout (5s)")
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"      GET {url} → Connection Error")
            except Exception as e:
                logger.debug(f"      GET {url} → {type(e).__name__}: {str(e)[:80]}")

        return None

    def _try_domain_alternatives(self, name: str, state: str, original_domain: str) -> Optional[str]:
        """
        Generate and test alternative domain patterns when original doesn't work.
        Returns first working domain URL or None.
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

        for alt_domain in alternatives:
            resolved_url = self._try_domain(alt_domain)
            if resolved_url:
                logger.info(f"    ✓ Found alternative: {alt_domain} (replaced {original_domain})")
                return resolved_url

        return None

    def _check_url_for_content(self, url: str) -> Optional[tuple[str, str]]:
        """
        Check if URL exists and contains meeting/procurement content.
        Returns (url, source_type) or None.

        source_type: "civicplus" | "granicus" | "boarddocs" | "html"
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

    def _check_url_for_procurement(self, url: str) -> bool:
        """Check if URL contains procurement/bidding content."""
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return False

            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return False

            html_lower = response.text.lower()

            # Check for procurement-related content
            procurement_indicators = [
                "bid", "rfp", "request for proposal", "procurement",
                "solicitation", "vendor", "purchasing", "opportunity",
            ]

            indicator_count = sum(1 for ind in procurement_indicators if ind in html_lower)
            return indicator_count >= 2

        except (requests.exceptions.RequestException, Exception):
            return False

    def enrich_municipality(self, municipality: Municipality, db: Session,
                           progress_callback: Optional[Callable] = None) -> dict:
        """
        Enrich a single municipality:
        1. Validate domain (if unverified)
        2. Discover sources (if domain verified)

        Returns dict with stats: {"domain_verified": bool, "sources_found": int}
        """
        stats = {"domain_verified": False, "sources_found": 0}

        # Step 1: Validate domain if unverified
        if municipality.domain_status == "unverified":
            if not municipality.domain:
                logger.warning(f"  {municipality.name}, {municipality.state}: No domain in database — marking as dead")
                municipality.domain_status = "dead"
                municipality.domain_verified_at = datetime.utcnow()
                db.commit()
                return stats

            logger.info(f"  Validating domain for {municipality.name}, {municipality.state}: {municipality.domain}")

            # Try original domain
            resolved_url = self._try_domain(municipality.domain)

            # If failed, try alternatives
            if not resolved_url:
                logger.info(f"    Original domain failed, trying alternatives...")
                resolved_url = self._try_domain_alternatives(
                    municipality.name,
                    municipality.state,
                    municipality.domain
                )

            if resolved_url:
                municipality.domain_status = "verified"
                municipality.resolved_url = resolved_url
                municipality.domain_verified_at = datetime.utcnow()
                db.commit()
                stats["domain_verified"] = True
                logger.info(f"    ✓ Domain verified: {resolved_url}")
            else:
                municipality.domain_status = "dead"
                municipality.domain_verified_at = datetime.utcnow()
                db.commit()
                logger.warning(f"    ✗ Domain dead: {municipality.domain}")
                return stats

        # Step 2: Discover sources if domain is verified
        if municipality.domain_status == "verified":
            # Delegate to SourceDiscovery which includes JS fallback for pop >= 10K
            discovery = SourceDiscovery(request_delay=self.delay, timeout=self.timeout)

            # Extract domain from resolved_url
            domain = municipality.domain
            if municipality.resolved_url:
                # Parse domain from resolved_url (e.g., "https://cityoflosangeles.com/" -> "cityoflosangeles.com")
                from urllib.parse import urlparse
                parsed = urlparse(municipality.resolved_url)
                domain = parsed.netloc.replace("www.", "")

            logger.info(f"  Discovering sources for {municipality.name}, {municipality.state}...")

            # Discover meeting minutes sources
            discovered = discovery.discover_municipality(
                name=municipality.name,
                state=municipality.state,
                domain=domain,
                population=municipality.population or 0,
                progress_callback=progress_callback
            )

            # Save discovered sources to database
            for source_obj in discovered:
                # Check if we already have this source
                existing = db.query(MunicipalSource).filter_by(url=source_obj.url).first()
                if existing:
                    continue

                # Create source record
                source = MunicipalSource(
                    municipality_id=municipality.id,
                    url=source_obj.url,
                    source_type="meeting_minutes",
                    platform=source_obj.source_type,
                    confidence=source_obj.confidence,
                    discovered_by_pattern="SourceDiscovery",
                )
                db.add(source)
                db.commit()
                stats["sources_found"] += 1
                logger.info(f"    ✓ Source found: {source_obj.url} ({source_obj.source_type})")

            # Also discover procurement sources
            procurement_sources = discovery.discover_procurement(
                name=municipality.name,
                state=municipality.state,
                domain=domain,
                population=municipality.population or 0
            )

            for source_obj in procurement_sources:
                # Check if already exists
                existing = db.query(MunicipalSource).filter_by(url=source_obj.url).first()
                if not existing:
                    source = MunicipalSource(
                        municipality_id=municipality.id,
                        url=source_obj.url,
                        source_type="procurement",
                        platform=source_obj.source_type,
                        confidence=source_obj.confidence,
                        discovered_by_pattern="SourceDiscovery",
                    )
                    db.add(source)
                    db.commit()
                    stats["sources_found"] += 1
                    logger.info(f"    ✓ Procurement source found: {source_obj.url}")

            if stats["sources_found"] == 0:
                logger.warning(f"    ✗ No sources found for {municipality.name}, {municipality.state}")

        return stats

    def enrich_state(self, state_abbr: str, progress_callback: Optional[Callable] = None,
                     force_reenrich: bool = False) -> dict:
        """
        Enrich all municipalities in a state.
        Returns dict with summary stats.

        Uses a per-municipality session to avoid SSL connection drops on long-running
        enrichments (Neon PostgreSQL drops idle connections after ~5 minutes).

        Args:
            state_abbr: Two-letter state abbreviation
            progress_callback: Optional callback function for progress updates
            force_reenrich: If True, re-discover sources even for cities that already have sources
        """
        # Load municipality IDs with a short-lived connection, then close it.
        db = SessionLocal()
        try:
            municipality_ids = [
                m.id for m in db.query(Municipality).filter_by(state=state_abbr)
                .order_by(Municipality.population.desc()).all()
            ]
        finally:
            db.close()

        total = len(municipality_ids)
        if total == 0:
            logger.warning(f"No municipalities found for state: {state_abbr}")
            return {}

        logger.info("=" * 70)
        logger.info(f"ENRICHMENT: {state_abbr} ({total} municipalities)")
        logger.info("=" * 70)

        stats = {
            "total": total,
            "domains_verified": 0,
            "domains_dead": 0,
            "sources_found": 0,
            "already_verified": 0,
        }

        for i, muni_id in enumerate(municipality_ids):
            # Fresh session per municipality — avoids idle SSL drops on Neon.
            db = SessionLocal()
            try:
                municipality = db.query(Municipality).filter_by(id=muni_id).first()
                if not municipality:
                    continue

                if progress_callback:
                    progress_callback(i, total, f"Enriching: {municipality.name}, {state_abbr}")

                # Skip if already verified and has sources (unless force_reenrich is True)
                has_sources = db.query(MunicipalSource).filter_by(
                    municipality_id=municipality.id
                ).count() > 0

                if municipality.domain_status == "verified" and has_sources and not force_reenrich:
                    stats["already_verified"] += 1
                    logger.info(f"[{i + 1}/{total}] {municipality.name}: Already enriched — skipping")
                    continue

                logger.info(f"[{i + 1}/{total}] Enriching {municipality.name}, {state_abbr}...")

                result = self.enrich_municipality(municipality, db, progress_callback)

                if result["domain_verified"]:
                    stats["domains_verified"] += 1
                elif municipality.domain_status == "dead":
                    stats["domains_dead"] += 1

                stats["sources_found"] += result["sources_found"]

            except Exception as e:
                logger.error(f"[{i + 1}/{total}] Error enriching {muni_id}: {e}")
            finally:
                db.close()

        # Summary
        logger.info("=" * 70)
        logger.info(f"ENRICHMENT SUMMARY: {state_abbr}")
        logger.info(f"  Total municipalities: {stats['total']}")
        logger.info(f"  Already enriched: {stats['already_verified']}")
        logger.info(f"  Domains verified: {stats['domains_verified']}")
        logger.info(f"  Domains dead: {stats['domains_dead']}")
        logger.info(f"  Sources discovered: {stats['sources_found']}")

        hit_rate = (stats['sources_found'] / stats['total'] * 100) if stats['total'] > 0 else 0
        logger.info(f"  Discovery rate: {hit_rate:.1f}%")
        logger.info("=" * 70)

        return stats

    def enrich_states(self, state_abbrs: list[str], progress_callback: Optional[Callable] = None) -> dict:
        """
        Enrich municipalities across multiple states.
        Returns dict with combined stats.
        """
        logger.info("=" * 70)
        logger.info(f"MULTI-STATE ENRICHMENT: {', '.join(state_abbrs)}")
        logger.info("=" * 70)

        combined_stats = {
            "total": 0,
            "domains_verified": 0,
            "domains_dead": 0,
            "sources_found": 0,
            "already_verified": 0,
        }

        for state in state_abbrs:
            logger.info(f"\nStarting enrichment for {state}...")
            state_stats = self.enrich_state(state, progress_callback)

            # Aggregate stats
            for key in combined_stats:
                combined_stats[key] += state_stats.get(key, 0)

        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("MULTI-STATE ENRICHMENT COMPLETE")
        logger.info("=" * 70)
        logger.info(f"States processed: {', '.join(state_abbrs)}")
        logger.info(f"Total municipalities: {combined_stats['total']}")
        logger.info(f"Already enriched: {combined_stats['already_verified']}")
        logger.info(f"Domains verified: {combined_stats['domains_verified']}")
        logger.info(f"Domains dead: {combined_stats['domains_dead']}")
        logger.info(f"Sources discovered: {combined_stats['sources_found']}")

        hit_rate = (combined_stats['sources_found'] / combined_stats['total'] * 100) if combined_stats['total'] > 0 else 0
        logger.info(f"Overall discovery rate: {hit_rate:.1f}%")
        logger.info("=" * 70)

        return combined_stats


def enrich_caselle_territory(progress_callback: Optional[Callable] = None) -> dict:
    """
    Convenience function to enrich all Caselle territory states.
    These are the core states where Caselle has strong market presence.
    """
    caselle_states = ["UT", "ID", "WY", "MT", "CO", "NV", "NM", "ND", "SD", "OR", "WA"]

    engine = EnrichmentEngine(request_delay=1.0, timeout=8)
    return engine.enrich_states(caselle_states, progress_callback)
