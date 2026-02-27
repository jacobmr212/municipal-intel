"""
Municipal Meeting Minutes Scraper
Fetches and extracts text from meeting documents across various municipal website platforms.
"""

import re
import time
import hashlib
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin
from typing import Optional
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)


class ScrapedDocument:
    """A single scraped meeting document."""

    def __init__(self, municipality: str, state: str, title: str, url: str,
                 text: str, date: Optional[datetime] = None, doc_type: str = "minutes"):
        self.municipality = municipality
        self.state = state
        self.title = title
        self.url = url
        self.text = text
        self.date = date
        self.doc_type = doc_type
        self.doc_hash = hashlib.md5(text.encode()).hexdigest()

    def __repr__(self):
        return f"<Doc: {self.municipality}, {self.state} — {self.title[:50]}>"


class MunicipalScraper:
    """Scrapes meeting minutes from discovered municipal sources."""

    def __init__(self, delay: float = 2.0, timeout: int = 30, max_docs: int = 15, db_session=None, use_cache: bool = True):
        self.delay = delay
        self.timeout = timeout
        self.max_docs = max_docs  # Max documents to scrape per source
        self.db = db_session  # Database session for caching
        self.use_cache = use_cache  # Enable/disable caching

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MunicipalIntel/1.0 (Government Meeting Research Tool)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        self.seen_hashes: set = set()
        self.cache_hits = 0
        self.cache_misses = 0

    def _fetch(self, url: str) -> Optional[requests.Response]:
        """Fetch a page with polite delay."""
        try:
            time.sleep(self.delay)
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None

    def _get_cached_document(self, url: str, municipality_name: str, state: str):
        """Check cache for previously scraped document."""
        if not self.use_cache or not self.db:
            return None

        try:
            from src.database import CachedDocument
            from datetime import datetime

            url_hash = hashlib.md5(url.encode()).hexdigest()

            # Query for cached entry
            cached = self.db.query(CachedDocument).filter(
                CachedDocument.url_hash == url_hash,
                CachedDocument.expires_at > datetime.utcnow()
            ).first()

            if cached:
                # Update hit count
                cached.hit_count += 1
                self.db.commit()
                self.cache_hits += 1
                logger.info(f"    💾 Cache HIT: {municipality_name} (hits: {cached.hit_count})")
                return cached.content_text

            self.cache_misses += 1
            return None

        except Exception as e:
            logger.debug(f"Cache lookup error for {url}: {e}")
            return None

    def _save_to_cache(self, url: str, content_text: str, municipality_name: str, state: str):
        """Save scraped document to cache."""
        if not self.use_cache or not self.db or not content_text:
            return

        try:
            from src.database import CachedDocument
            from datetime import datetime, timedelta

            url_hash = hashlib.md5(url.encode()).hexdigest()
            content_hash = hashlib.md5(content_text.encode()).hexdigest()

            # Check if entry already exists (avoid duplicates)
            existing = self.db.query(CachedDocument).filter(
                CachedDocument.url_hash == url_hash
            ).first()

            if existing:
                # Update existing cache entry
                existing.content_text = content_text
                existing.content_hash = content_hash
                existing.scraped_at = datetime.utcnow()
                existing.expires_at = datetime.utcnow() + timedelta(days=7)
            else:
                # Create new cache entry
                cache_entry = CachedDocument(
                    url_hash=url_hash,
                    url=url[:500],  # Truncate long URLs
                    content_text=content_text,
                    content_hash=content_hash,
                    scraped_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=7),
                    hit_count=0,
                    municipality_name=municipality_name,
                    state=state
                )
                self.db.add(cache_entry)

            self.db.commit()
            logger.debug(f"    💾 Cached: {municipality_name} ({len(content_text)} chars)")

        except Exception as e:
            logger.debug(f"Cache save error for {url}: {e}")
            # Don't fail the scrape if caching fails
            pass

    def _extract_pdf_text(self, content: bytes) -> str:
        """Extract text from PDF bytes."""
        if not PDF_SUPPORT:
            return ""
        try:
            reader = PyPDF2.PdfReader(BytesIO(content))
            parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return "\n".join(parts)
        except Exception as e:
            logger.debug(f"PDF extraction failed: {e}")
            return ""

    def _parse_date(self, text: str) -> Optional[datetime]:
        """Try to extract a meeting date from text."""
        patterns = [
            r'(\w+ \d{1,2},?\s*\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        for pat in patterns:
            match = re.search(pat, text[:500])
            if match:
                try:
                    from dateutil.parser import parse as dateparse
                    return dateparse(match.group(1), fuzzy=True)
                except (ValueError, ImportError):
                    continue
        return None

    def _is_recent_document(self, doc_date: Optional[datetime]) -> bool:
        """Check if document is from last 18 months (still relevant)."""
        if doc_date is None:
            return True  # Keep documents without dates

        now = datetime.now()
        months_ago_18 = now - timedelta(days=547)  # ~18 months

        # Document is recent if it's from last 18 months
        return doc_date >= months_ago_18

    def _is_meeting_link(self, text: str, href: str) -> bool:
        """Check if a link likely points to meeting content."""
        combined = f"{text} {href}".lower()
        indicators = [
            "minute", "agenda", "meeting", "council", "commission",
            "board", "session", "packet", "regular meeting",
            "special meeting", "work session", "public hearing",
            "workshop", "hearing", "executive", "legislative",
            "assembly", "proceedings", "record", "summary",
            "approved minutes", "draft minutes", "official minutes",
            "meeting packet", "agenda packet", "council packet",
        ]
        return any(ind in combined for ind in indicators)

    def _is_pdf_link(self, href: str, content_type: str = "") -> bool:
        """Check if a URL points to a PDF."""
        return href.lower().endswith(".pdf") or "pdf" in content_type.lower()

    def _scrape_links_page(self, source, base_url: str, soup: BeautifulSoup) -> list[ScrapedDocument]:
        """Scrape meeting documents from a page containing links."""
        docs = []

        # Access municipality through relationship
        municipality = source.municipality

        links = soup.find_all("a", href=True)
        scraped_count = 0

        # Separate PDF links from HTML links - prioritize PDFs
        pdf_links = []
        html_links = []

        for link in links:
            href = link["href"]
            text = link.get_text(strip=True)

            if not self._is_meeting_link(text, href):
                continue

            full_url = urljoin(base_url, href)

            # Skip anchor links and javascript
            if full_url.startswith(("#", "javascript:")):
                continue

            if self._is_pdf_link(href):
                pdf_links.append((link, full_url, text))
            else:
                html_links.append((link, full_url, text))

        # Process PDF links first (they're more likely to have actual content)
        all_links = pdf_links + html_links

        for link, full_url, text in all_links:
            if scraped_count >= self.max_docs:
                break

            # Fetch the linked document
            resp = self._fetch(full_url)
            if not resp:
                continue

            content_type = resp.headers.get("content-type", "")
            doc_text = ""

            if self._is_pdf_link(href, content_type):
                # Skip PDFs over 2MB for performance
                pdf_size_mb = len(resp.content) / (1024 * 1024)
                if pdf_size_mb > 2.0:
                    logger.info(f"  Skipping large PDF ({pdf_size_mb:.1f}MB): {full_url}")
                    continue
                doc_text = self._extract_pdf_text(resp.content)
            elif "html" in content_type:
                page_soup = BeautifulSoup(resp.text, "lxml")
                content = (
                    page_soup.find("main")
                    or page_soup.find("article")
                    or page_soup.find("div", class_=re.compile(r"content|body|main|entry", re.I))
                    or page_soup.find("body")
                )
                if content:
                    doc_text = content.get_text(separator="\n", strip=True)

            if doc_text and len(doc_text) > 200:
                doc_hash = hashlib.md5(doc_text.encode()).hexdigest()
                if doc_hash not in self.seen_hashes:
                    self.seen_hashes.add(doc_hash)
                    doc = ScrapedDocument(
                        municipality=municipality.name,
                        state=municipality.state,
                        title=text or "Meeting Document",
                        url=full_url,
                        text=doc_text,
                        date=self._parse_date(doc_text),
                    )
                    docs.append(doc)
                    scraped_count += 1
                    logger.debug(f"    Scraped: {text[:60]}")

        return docs

    def _scrape_utah_portal(self, source, soup: BeautifulSoup) -> list[ScrapedDocument]:
        """Scrape meeting notices from Utah PMN portal pages."""
        docs = []

        # Access municipality through relationship
        municipality = source.municipality

        # Find the table containing meeting notices
        table = soup.find('table')
        if not table:
            return docs

        rows = table.find_all('tr')
        for row in rows[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) < 2:
                continue

            # Extract notice title and date
            notice_title = cols[0].get_text(strip=True) if cols[0] else ""
            event_date = cols[1].get_text(strip=True) if len(cols) > 1 else ""

            # Look for attachments (PDFs)
            if len(cols) > 2:
                attachment_cell = cols[2]
                pdf_links = attachment_cell.find_all('a', href=True)

                for link in pdf_links[:3]:  # Max 3 PDFs per notice
                    href = link['href']
                    if not href.endswith('.pdf'):
                        continue

                    full_url = urljoin(source.url, href)
                    pdf_resp = self._fetch(full_url)

                    if pdf_resp:
                        text = self._extract_pdf_text(pdf_resp.content)
                        if text and len(text) > 200:
                            doc_hash = hashlib.md5(text.encode()).hexdigest()
                            if doc_hash not in self.seen_hashes:
                                self.seen_hashes.add(doc_hash)
                                docs.append(ScrapedDocument(
                                    municipality=municipality.name,
                                    state=municipality.state,
                                    title=f"{notice_title} - {link.get_text(strip=True)}",
                                    url=full_url,
                                    text=text,
                                    date=self._parse_date(f"{event_date} {text[:500]}"),
                                ))
                                logger.debug(f"    Portal PDF: {notice_title[:40]}")

            # If no PDFs, use the row text itself
            if len(docs) == 0 and notice_title:
                row_text = row.get_text(separator=" ", strip=True)
                if len(row_text) > 100:
                    docs.append(ScrapedDocument(
                        municipality=municipality.name,
                        state=municipality.state,
                        title=notice_title,
                        url=source.url,
                        text=row_text,
                        date=self._parse_date(event_date),
                    ))

        return docs

    def _scrape_primegov_portal(self, source, soup: BeautifulSoup) -> list[ScrapedDocument]:
        """
        Scrape meeting documents from a PrimeGov public portal.
        PrimeGov is a React SPA but exposes a JSON API at /api/v2/PublicPortal/ListMeetings.
        Falls back to page-text document if API is unavailable.
        """
        docs = []
        municipality = source.municipality

        # Extract the base URL (e.g. https://thorntonco.primegov.com)
        from urllib.parse import urlparse
        parsed = urlparse(source.url)
        api_base = f"{parsed.scheme}://{parsed.netloc}"

        # Try the PrimeGov API for recent meetings
        api_url = f"{api_base}/api/v2/PublicPortal/ListMeetings"
        try:
            resp = self._fetch(api_url)
            if resp and resp.headers.get("content-type", "").startswith("application/json"):
                import json
                data = resp.json()
                meetings = data if isinstance(data, list) else data.get("meetings", data.get("items", []))
                for meeting in meetings[:self.max_docs]:
                    meeting_id = meeting.get("id") or meeting.get("meetingId")
                    meeting_title = meeting.get("name") or meeting.get("title") or "Meeting"
                    meeting_date = meeting.get("meetingDate") or meeting.get("date") or ""
                    if not meeting_id:
                        continue
                    # Try to get the agenda PDF
                    agenda_url = f"{api_base}/api/v2/PublicPortal/ListMeetingDocuments?meetingId={meeting_id}"
                    doc_resp = self._fetch(agenda_url)
                    if doc_resp and "json" in doc_resp.headers.get("content-type", ""):
                        docs_data = doc_resp.json()
                        for doc_info in (docs_data if isinstance(docs_data, list) else []):
                            doc_url = doc_info.get("url") or doc_info.get("path") or ""
                            if not doc_url:
                                continue
                            if not doc_url.startswith("http"):
                                doc_url = api_base + doc_url
                            pdf_resp = self._fetch(doc_url)
                            if pdf_resp:
                                text = self._extract_pdf_text(pdf_resp.content)
                                if text and len(text) > 200:
                                    doc_hash = hashlib.md5(text.encode()).hexdigest()
                                    if doc_hash not in self.seen_hashes:
                                        self.seen_hashes.add(doc_hash)
                                        docs.append(ScrapedDocument(
                                            municipality=municipality.name,
                                            state=municipality.state,
                                            title=f"{meeting_title} - {doc_info.get('name', 'Document')}",
                                            url=doc_url,
                                            text=text,
                                            date=self._parse_date(meeting_date),
                                        ))
        except Exception as e:
            logger.debug(f"PrimeGov API failed: {e}")

        # Fallback: scrape the portal page as regular HTML
        if not docs:
            docs = self._scrape_links_page(source, source.url, soup)

        # Final fallback: use page text itself
        if not docs:
            page_text = soup.get_text(separator="\n", strip=True)
            if len(page_text) > 300:
                docs.append(ScrapedDocument(
                    municipality=municipality.name,
                    state=municipality.state,
                    title="PrimeGov Meeting Portal",
                    url=source.url,
                    text=page_text,
                    date=self._parse_date(page_text),
                ))

        return docs

    def _scrape_civicweb_portal(self, source, soup: BeautifulSoup) -> list[ScrapedDocument]:
        """
        Scrape meeting documents from a CivicWeb portal.
        CivicWeb lists meeting types on MeetingTypeList.aspx;
        individual meetings are at MeetingInformation.aspx?Id=XXXX.
        """
        docs = []
        municipality = source.municipality

        from urllib.parse import urlparse, urljoin as urljoin2
        parsed = urlparse(source.url)
        portal_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}/"

        # Find links to individual meeting pages
        meeting_page_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "MeetingInformation" in href or "Meeting" in href and "aspx" in href:
                meeting_url = urljoin2(source.url, href)
                if meeting_url not in meeting_page_links:
                    meeting_page_links.append((meeting_url, text))

        # Visit meeting type pages to get individual meetings
        if not meeting_page_links:
            # Try to find meeting type links from the main list
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "MeetingType" in href or "Category" in href:
                    meeting_type_url = urljoin2(source.url, href)
                    resp = self._fetch(meeting_type_url)
                    if resp:
                        type_soup = BeautifulSoup(resp.text, "html.parser")
                        for a2 in type_soup.find_all("a", href=True):
                            if "MeetingInformation" in a2["href"]:
                                meeting_url = urljoin2(meeting_type_url, a2["href"])
                                meeting_page_links.append((meeting_url, a2.get_text(strip=True)))

        # Scrape individual meeting pages for documents
        for meeting_url, title in meeting_page_links[:self.max_docs]:
            resp = self._fetch(meeting_url)
            if not resp:
                continue
            m_soup = BeautifulSoup(resp.text, "html.parser")

            # Look for document links on the meeting page
            for a in m_soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower() or "document" in href.lower():
                    doc_url = urljoin2(meeting_url, href)
                    pdf_resp = self._fetch(doc_url)
                    if pdf_resp:
                        if ".pdf" in href.lower() or "pdf" in pdf_resp.headers.get("content-type", ""):
                            text = self._extract_pdf_text(pdf_resp.content)
                        else:
                            doc_soup = BeautifulSoup(pdf_resp.text, "html.parser")
                            text = doc_soup.get_text(separator="\n", strip=True)
                        if text and len(text) > 200:
                            doc_hash = hashlib.md5(text.encode()).hexdigest()
                            if doc_hash not in self.seen_hashes:
                                self.seen_hashes.add(doc_hash)
                                docs.append(ScrapedDocument(
                                    municipality=municipality.name,
                                    state=municipality.state,
                                    title=f"{title} - {a.get_text(strip=True) or 'Document'}",
                                    url=doc_url,
                                    text=text,
                                    date=self._parse_date(text),
                                ))

        # Fallback: use page text
        if not docs:
            page_text = soup.get_text(separator="\n", strip=True)
            if len(page_text) > 300:
                docs.append(ScrapedDocument(
                    municipality=municipality.name,
                    state=municipality.state,
                    title="CivicWeb Meeting Portal",
                    url=source.url,
                    text=page_text,
                    date=self._parse_date(page_text),
                ))

        return docs

    def scrape_source(self, source) -> list[ScrapedDocument]:
        """Scrape all available meeting documents from a discovered source."""
        docs = []

        # Access municipality through relationship
        municipality = source.municipality

        logger.info(f"  Scraping {municipality.name}, {municipality.state}: {source.url}")

        # Check cache first
        cached_text = self._get_cached_document(source.url, municipality.name, municipality.state)
        if cached_text:
            # Return cached document
            doc = ScrapedDocument(
                municipality=municipality.name,
                state=municipality.state,
                title="Cached Meeting Document",
                url=source.url,
                text=cached_text,
                date=self._parse_date(cached_text),
            )
            return [doc]

        resp = self._fetch(source.url)
        if not resp:
            logger.warning(f"    Could not reach {source.url}")
            return docs

        content_type = resp.headers.get("content-type", "")

        # If the source itself is a PDF, extract it directly
        if self._is_pdf_link(source.url, content_type):
            text = self._extract_pdf_text(resp.content)
            if text and len(text) > 200:
                doc = ScrapedDocument(
                    municipality=municipality.name,
                    state=municipality.state,
                    title="Meeting Document",
                    url=source.url,
                    text=text,
                    date=self._parse_date(text),
                )
                docs.append(doc)
            return docs

        # Parse the HTML page and find meeting document links
        if "html" not in content_type:
            return docs

        soup = BeautifulSoup(resp.text, "lxml")

        # Portal sources: Use specialized portal scraper
        if source.platform == "utah_pmn":
            logger.info(f"    Using Utah PMN portal scraper")
            docs = self._scrape_utah_portal(source, soup)
            logger.info(f"    Found {len(docs)} documents from portal")
            return docs

        if source.platform == "primegov":
            logger.info(f"    Using PrimeGov portal scraper")
            docs = self._scrape_primegov_portal(source, soup)
            logger.info(f"    Found {len(docs)} documents from PrimeGov")
            return docs

        if source.platform == "civicweb":
            logger.info(f"    Using CivicWeb portal scraper")
            docs = self._scrape_civicweb_portal(source, soup)
            logger.info(f"    Found {len(docs)} documents from CivicWeb")
            return docs

        # Strategy 1: Look for direct links to meeting documents
        docs = self._scrape_links_page(source, source.url, soup)

        # Strategy 2: If CivicPlus, look for AJAX-loaded content
        if source.source_type == "civicplus" and len(docs) == 0:
            # CivicPlus often loads content via specific divs
            agenda_divs = soup.find_all("div", class_=re.compile(r"agenda|meeting", re.I))
            for div in agenda_divs:
                pdf_links = div.find_all("a", href=re.compile(r"\.pdf$|ViewFile|ViewPacket", re.I))
                for link in pdf_links[:self.max_docs]:
                    href = link["href"]
                    full_url = urljoin(source.url, href)
                    pdf_resp = self._fetch(full_url)
                    if pdf_resp:
                        text = self._extract_pdf_text(pdf_resp.content)
                        if text and len(text) > 200:
                            doc_hash = hashlib.md5(text.encode()).hexdigest()
                            if doc_hash not in self.seen_hashes:
                                self.seen_hashes.add(doc_hash)
                                docs.append(ScrapedDocument(
                                    municipality=municipality.name,
                                    state=municipality.state,
                                    title=link.get_text(strip=True) or "Meeting Document",
                                    url=full_url,
                                    text=text,
                                    date=self._parse_date(text),
                                ))

        # Strategy 3: If we still found nothing, try the page text itself
        if len(docs) == 0:
            page_text = soup.get_text(separator="\n", strip=True)
            if len(page_text) > 500:
                meeting_words = ["council", "meeting", "agenda", "minutes", "motion", "vote"]
                if sum(1 for w in meeting_words if w in page_text.lower()) >= 3:
                    docs.append(ScrapedDocument(
                        municipality=municipality.name,
                        state=municipality.state,
                        title=soup.title.string if soup.title else "Meeting Page",
                        url=source.url,
                        text=page_text,
                        date=self._parse_date(page_text),
                    ))

        logger.info(f"    Found {len(docs)} documents")

        # Cache the scraped documents
        if docs:
            # Combine all document texts for caching (or just cache the first/primary one)
            # For simplicity, we'll cache the concatenated text
            combined_text = "\n\n---\n\n".join([doc.text for doc in docs])
            self._save_to_cache(source.url, combined_text, municipality.name, municipality.state)

        return docs

    def scrape_all(self, sources: list, progress_callback=None, max_workers: int = 10) -> list[ScrapedDocument]:
        """Scrape all discovered sources in parallel with date filtering.

        Args:
            sources: List of municipal sources to scrape
            progress_callback: Optional callback for progress updates
            max_workers: Number of parallel workers (default: 10)

        Returns:
            List of scraped documents from current year (2026)
        """
        all_docs = []
        total = len(sources)
        completed = 0
        filtered_old = 0

        def scrape_single_source(source):
            """Helper to scrape one source and filter by date."""
            try:
                docs = self.scrape_source(source)
                # Filter to only recent documents (last 18 months)
                recent_docs = []
                for doc in docs:
                    if self._is_recent_document(doc.date):
                        recent_docs.append(doc)
                    else:
                        nonlocal filtered_old
                        filtered_old += 1
                        doc_date_str = doc.date.strftime("%Y-%m-%d") if doc.date else "unknown"
                        logger.info(f"  Filtered out old document: {doc.title[:60]} (date: {doc_date_str})")
                return recent_docs
            except Exception as e:
                logger.error(f"  Error scraping {source.url}: {e}")
                return []

        # Parallel scraping with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all scraping tasks
            future_to_source = {executor.submit(scrape_single_source, src): src for src in sources}

            # Process results as they complete
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                completed += 1

                if progress_callback:
                    progress_callback(completed, total, f"Scraped: {source.municipality}, {source.state}")

                try:
                    docs = future.result()
                    all_docs.extend(docs)
                except Exception as e:
                    logger.error(f"  Exception processing {source.municipality}: {e}")

        logger.info(f"📄 Total documents scraped: {len(all_docs)} (filtered {filtered_old} old docs)")
        logger.info(f"⚡ Scraped {len(sources)} sources in parallel with {max_workers} workers")
        return all_docs
