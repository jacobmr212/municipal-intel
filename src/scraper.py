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
from datetime import datetime
from urllib.parse import urljoin
from typing import Optional
from io import BytesIO

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

    def __init__(self, delay: float = 2.0, timeout: int = 30, max_docs: int = 15):
        self.delay = delay
        self.timeout = timeout
        self.max_docs = max_docs  # Max documents to scrape per source

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MunicipalIntel/1.0 (Government Meeting Research Tool)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        self.seen_hashes: set = set()

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
                        municipality=source.municipality,
                        state=source.state,
                        title=text or "Meeting Document",
                        url=full_url,
                        text=doc_text,
                        date=self._parse_date(doc_text),
                    )
                    docs.append(doc)
                    scraped_count += 1
                    logger.debug(f"    Scraped: {text[:60]}")

        return docs

    def scrape_source(self, source) -> list[ScrapedDocument]:
        """Scrape all available meeting documents from a discovered source."""
        docs = []

        logger.info(f"  Scraping {source.municipality}, {source.state}: {source.url}")

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
                    municipality=source.municipality,
                    state=source.state,
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
                                    municipality=source.municipality,
                                    state=source.state,
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
                        municipality=source.municipality,
                        state=source.state,
                        title=soup.title.string if soup.title else "Meeting Page",
                        url=source.url,
                        text=page_text,
                        date=self._parse_date(page_text),
                    ))

        logger.info(f"    Found {len(docs)} documents")
        return docs

    def scrape_all(self, sources: list, progress_callback=None) -> list[ScrapedDocument]:
        """Scrape all discovered sources."""
        all_docs = []
        total = len(sources)

        for i, source in enumerate(sources):
            if progress_callback:
                progress_callback(i, total, f"Scraping: {source.municipality}, {source.state}")

            try:
                docs = self.scrape_source(source)
                all_docs.extend(docs)
            except Exception as e:
                logger.error(f"  Error scraping {source.url}: {e}")

        logger.info(f"Total documents scraped: {len(all_docs)}")
        return all_docs
