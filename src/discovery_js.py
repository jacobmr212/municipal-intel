"""
JavaScript-Enabled Source Discovery Engine
Uses Playwright to render JavaScript-heavy municipal websites that fail with static requests.
"""

import logging
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class JSSourceDiscovery:
    """Discovers meeting minutes pages on JavaScript-rendered websites."""

    def __init__(self, timeout: int = 10000, headless: bool = True):
        """
        Initialize JS discovery engine.

        Args:
            timeout: Page load timeout in milliseconds (default 10s)
            headless: Run browser in headless mode (default True)
        """
        self.timeout = timeout
        self.headless = headless
        self.browser = None
        self.playwright = None

    async def __aenter__(self):
        """Context manager entry - start Playwright browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def check_url(self, url: str) -> Optional[tuple[str, str]]:
        """
        Check if a URL exists and contains meeting content (with JS rendering).
        Returns (final_url, source_type) or None.

        Args:
            url: URL to check

        Returns:
            Tuple of (final_url, source_type) if valid meeting page, else None
        """
        if not self.browser:
            logger.error("Browser not initialized - use async context manager")
            return None

        try:
            page = await self.browser.new_page()

            # Navigate with network idle wait (ensures JS finishes loading)
            response = await page.goto(
                url,
                timeout=self.timeout,
                wait_until="networkidle"  # Wait for network to be idle
            )

            if not response or response.status != 200:
                await page.close()
                return None

            # Wait for DOM content to be fully loaded
            await page.wait_for_load_state("domcontentloaded")

            # Get page content after JS execution
            html_content = await page.content()
            html_lower = html_content.lower()

            # Check for meeting-related content
            meeting_indicators = [
                "meeting", "agenda", "minutes", "council",
                "session", "public hearing", "regular meeting",
                "board meeting", "commission meeting",
            ]

            indicator_count = sum(1 for ind in meeting_indicators if ind in html_lower)

            if indicator_count < 2:
                await page.close()
                return None

            # Get final URL BEFORE closing page
            final_url = page.url

            # Identify platform from rendered content
            source_type = "html"
            if "agendacenter" in url.lower() or "civicplus" in html_lower or "civicengage" in html_lower:
                source_type = "civicplus"
            elif "granicus" in html_lower or "legistar" in html_lower:
                source_type = "granicus"
            elif "boarddocs" in html_lower:
                source_type = "boarddocs"
            elif "novusagenda" in html_lower or "novus agenda" in html_lower:
                source_type = "novusagenda"
            elif "opengov" in html_lower:
                source_type = "opengov"

            # Close page after getting all needed data
            await page.close()

            logger.info(f"  ✓ JS-rendered page validated: {final_url[:70]} ({source_type})")
            return (final_url, source_type)

        except PlaywrightTimeout:
            logger.debug(f"  Timeout loading {url[:70]}")
            return None
        except Exception as e:
            logger.debug(f"  Error checking {url[:70]}: {str(e)[:40]}")
            return None

    async def check_urls_batch(self, urls: list[str]) -> list[tuple[str, str, str]]:
        """
        Check multiple URLs in parallel using Playwright.
        Returns list of (original_url, final_url, source_type) for successful checks.

        Args:
            urls: List of URLs to check

        Returns:
            List of tuples (original_url, final_url, source_type) for valid pages
        """
        if not self.browser:
            logger.error("Browser not initialized - use async context manager")
            return []

        results = []

        # Check URLs concurrently (limit to 5 at a time to avoid overwhelming browser)
        batch_size = 5
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]

            tasks = [self.check_url(url) for url in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for original_url, result in zip(batch, batch_results):
                if result and not isinstance(result, Exception):
                    final_url, source_type = result
                    results.append((original_url, final_url, source_type))

        return results


def check_url_with_js(url: str, timeout: int = 10000) -> Optional[tuple[str, str]]:
    """
    Synchronous wrapper for JS URL checking (for compatibility with existing code).

    Args:
        url: URL to check
        timeout: Timeout in milliseconds

    Returns:
        Tuple of (final_url, source_type) if valid, else None
    """
    async def _check():
        async with JSSourceDiscovery(timeout=timeout) as discovery:
            return await discovery.check_url(url)

    return asyncio.run(_check())


def check_urls_with_js(urls: list[str], timeout: int = 10000) -> list[tuple[str, str, str]]:
    """
    Synchronous wrapper for batch JS URL checking.

    Args:
        urls: List of URLs to check
        timeout: Timeout in milliseconds per page

    Returns:
        List of tuples (original_url, final_url, source_type) for valid pages
    """
    async def _check():
        async with JSSourceDiscovery(timeout=timeout) as discovery:
            return await discovery.check_urls_batch(urls)

    return asyncio.run(_check())
