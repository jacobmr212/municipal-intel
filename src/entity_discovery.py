"""
Multi-Entity Discovery Engine

Discovers multiple government entities within a single municipality:
- School Districts (separate ERP budgets!)
- Fire Districts
- Library Districts
- Water/Sewer Districts
- Parks & Recreation Districts
- Transportation Authorities
- County Government (overlapping jurisdiction)

Each entity is a separate sales opportunity with its own budget and ERP needs.
"""

import time
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class GovernmentEntity:
    """A discovered government entity."""
    entity_type: str  # "school_district", "fire_district", "library", etc.
    name: str
    municipality: str
    state: str
    domain: str
    url: str
    confidence: float  # 0.0 - 1.0
    notes: str = ""


class EntityDiscovery:
    """Discovers multiple government entities per municipality."""

    # Entity types we're looking for
    ENTITY_TYPES = {
        "school_district": {
            "keywords": ["school district", "schools", "isd", "unified school"],
            "domain_patterns": [
                "{city}schools.org",
                "{city}schooldistrict.org",
                "{city}schools.net",
                "{city}isd.org",
                "{city}usd.org",  # Unified School District
            ],
            "url_patterns": [
                "/departments/finance",
                "/business-office",
                "/budget",
                "/board-meetings"
            ]
        },
        "fire_district": {
            "keywords": ["fire department", "fire district", "fire protection"],
            "domain_patterns": [
                "{city}fire.org",
                "{city}firedistrict.org",
                "{city}fd.org",
            ],
            "url_patterns": [
                "/about/budget",
                "/board",
                "/meetings"
            ]
        },
        "library": {
            "keywords": ["library", "public library"],
            "domain_patterns": [
                "{city}library.org",
                "{city}publiclibrary.org",
                "{city}lib.org",
            ],
            "url_patterns": [
                "/about/board",
                "/board-meetings",
                "/budget"
            ]
        },
        "water_district": {
            "keywords": ["water district", "water department", "utilities", "water & sewer"],
            "domain_patterns": [
                "{city}water.org",
                "{city}utilities.org",
                "{city}waterdistrict.org",
            ],
            "url_patterns": [
                "/rates",
                "/board",
                "/meetings"
            ]
        },
        "parks_recreation": {
            "keywords": ["parks and recreation", "parks & rec", "recreation district"],
            "domain_patterns": [
                "{city}parks.org",
                "{city}parksandrec.org",
                "{city}rec.org",
            ],
            "url_patterns": [
                "/about/board",
                "/programs",
                "/facilities"
            ]
        },
        "county": {
            "keywords": ["county"],
            "domain_patterns": [
                "{county}county{state}.gov",
                "{county}county.org",
                "{county}co.gov",
            ],
            "url_patterns": [
                "/departments",
                "/budget",
                "/board-of-supervisors",
                "/commissioners"
            ]
        }
    }

    def __init__(self, request_delay: float = 1.0, timeout: int = 8):
        self.delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MunicipalIntel/1.0 (Government Entity Research Tool)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _check_url_exists(self, url: str) -> bool:
        """Quick check if URL exists and returns HTML."""
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code < 400
        except:
            return False

    def _verify_entity(self, url: str, entity_type: str) -> Optional[tuple[str, float]]:
        """
        Verify URL contains entity-specific content.
        Returns (verified_url, confidence) or None.
        """
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None

            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return None

            html_lower = response.text.lower()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Get keywords for this entity type
            keywords = self.ENTITY_TYPES[entity_type]["keywords"]

            # Count keyword matches
            keyword_matches = sum(1 for kw in keywords if kw in html_lower)

            # Check for government indicators
            gov_indicators = [
                "board of", "budget", "meeting", "council",
                "department", "administration", "finance",
                "procurement", "bid", "rfp"
            ]
            gov_matches = sum(1 for ind in gov_indicators if ind in html_lower)

            # Calculate confidence
            # Need at least one keyword match and one gov indicator
            if keyword_matches > 0 and gov_matches > 0:
                # More matches = higher confidence
                confidence = min(0.5 + (keyword_matches * 0.15) + (gov_matches * 0.05), 0.95)
                return (response.url, confidence)

            return None

        except Exception as e:
            logger.debug(f"    Error verifying {url}: {e}")
            return None

    def discover_entities(self, municipality_name: str, state: str,
                         main_domain: str, county_name: str = None) -> List[GovernmentEntity]:
        """
        Discover all government entities for a municipality.

        Args:
            municipality_name: City/town name (e.g., "Salt Lake City")
            state: State code (e.g., "UT")
            main_domain: Municipality's main domain (e.g., "slc.gov")
            county_name: Optional county name for county entity discovery

        Returns:
            List of discovered government entities
        """
        entities = []
        city_slug = municipality_name.lower().replace(" ", "").replace("-", "")
        state_lower = state.lower()

        logger.info(f"  Discovering entities for {municipality_name}, {state}...")

        # Try each entity type
        for entity_type, config in self.ENTITY_TYPES.items():
            # Skip county if no county name provided
            if entity_type == "county" and not county_name:
                continue

            logger.debug(f"    Checking for {entity_type}...")

            # Generate domain patterns
            domain_patterns = []
            for pattern in config["domain_patterns"]:
                if entity_type == "county" and county_name:
                    county_slug = county_name.lower().replace(" ", "").replace("-", "")
                    domain = pattern.format(county=county_slug, state=state_lower)
                else:
                    domain = pattern.format(city=city_slug)
                domain_patterns.append(domain)

            # Try each domain pattern
            for domain in domain_patterns:
                base_url = f"https://{domain}"

                # Check if domain exists
                time.sleep(self.delay)
                if not self._check_url_exists(base_url):
                    continue

                # Try root URL first
                result = self._verify_entity(base_url, entity_type)
                if result:
                    verified_url, confidence = result
                    entity = GovernmentEntity(
                        entity_type=entity_type,
                        name=self._generate_entity_name(municipality_name, entity_type, county_name),
                        municipality=municipality_name,
                        state=state,
                        domain=domain,
                        url=verified_url,
                        confidence=confidence,
                        notes=f"Discovered via domain pattern: {domain}"
                    )
                    entities.append(entity)
                    logger.info(f"    ✓ Found {entity_type}: {verified_url} (confidence: {confidence:.0%})")
                    break  # Found one for this entity type, move to next

                # Try URL patterns if root didn't work
                for url_pattern in config["url_patterns"]:
                    full_url = f"{base_url}{url_pattern}"
                    time.sleep(self.delay)

                    result = self._verify_entity(full_url, entity_type)
                    if result:
                        verified_url, confidence = result
                        entity = GovernmentEntity(
                            entity_type=entity_type,
                            name=self._generate_entity_name(municipality_name, entity_type, county_name),
                            municipality=municipality_name,
                            state=state,
                            domain=domain,
                            url=verified_url,
                            confidence=confidence,
                            notes=f"Discovered via URL: {url_pattern}"
                        )
                        entities.append(entity)
                        logger.info(f"    ✓ Found {entity_type}: {verified_url} (confidence: {confidence:.0%})")
                        break  # Found one, move to next entity type

                if entities and entities[-1].entity_type == entity_type:
                    break  # Already found this entity type, move on

        # Also check for entities on main municipal website
        # Many smaller towns list other entities on their main site
        entities.extend(self._check_main_site_for_entities(
            municipality_name, state, main_domain, county_name
        ))

        logger.info(f"  Discovered {len(entities)} entities for {municipality_name}")
        return entities

    def _check_main_site_for_entities(self, municipality_name: str, state: str,
                                     main_domain: str, county_name: str = None) -> List[GovernmentEntity]:
        """
        Check municipality's main website for links to other entities.
        Smaller towns often list school district, library, etc. on main site.
        """
        entities = []

        try:
            main_url = f"https://{main_domain}"
            response = self.session.get(main_url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return entities

            soup = BeautifulSoup(response.text, 'html.parser')
            html_lower = response.text.lower()

            # Look for links with entity keywords
            for entity_type, config in self.ENTITY_TYPES.items():
                if entity_type == "county":  # Skip county for main site check
                    continue

                for keyword in config["keywords"]:
                    # Find links containing this keyword
                    for link in soup.find_all('a', href=True):
                        link_text = link.get_text().lower()
                        href = link['href'].lower()

                        if keyword in link_text or keyword in href:
                            # Extract full URL
                            if href.startswith('http'):
                                entity_url = href
                            elif href.startswith('/'):
                                entity_url = f"{main_url}{href}"
                            else:
                                entity_url = f"{main_url}/{href}"

                            # Extract domain
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(entity_url)
                                entity_domain = parsed.netloc

                                # Skip if same as main domain (internal page, not separate entity)
                                if entity_domain == main_domain:
                                    continue

                                # Verify this is actually an entity
                                time.sleep(self.delay)
                                result = self._verify_entity(entity_url, entity_type)
                                if result:
                                    verified_url, confidence = result
                                    entity = GovernmentEntity(
                                        entity_type=entity_type,
                                        name=self._generate_entity_name(municipality_name, entity_type, county_name),
                                        municipality=municipality_name,
                                        state=state,
                                        domain=entity_domain,
                                        url=verified_url,
                                        confidence=confidence,
                                        notes=f"Found link on main municipal site: '{link_text}'"
                                    )
                                    entities.append(entity)
                                    logger.info(f"    ✓ Found {entity_type} via main site link: {entity_domain}")
                                    break  # Found one, move to next entity type

                            except Exception as e:
                                logger.debug(f"    Error parsing link {entity_url}: {e}")
                                continue

        except Exception as e:
            logger.debug(f"    Error checking main site for entities: {e}")

        return entities

    def _generate_entity_name(self, municipality_name: str, entity_type: str,
                             county_name: str = None) -> str:
        """Generate a descriptive name for an entity."""
        if entity_type == "school_district":
            return f"{municipality_name} School District"
        elif entity_type == "fire_district":
            return f"{municipality_name} Fire District"
        elif entity_type == "library":
            return f"{municipality_name} Public Library"
        elif entity_type == "water_district":
            return f"{municipality_name} Water District"
        elif entity_type == "parks_recreation":
            return f"{municipality_name} Parks & Recreation"
        elif entity_type == "county" and county_name:
            return f"{county_name} County"
        else:
            return f"{municipality_name} {entity_type.replace('_', ' ').title()}"
