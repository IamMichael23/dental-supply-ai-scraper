from __future__ import annotations
import asyncio
import json
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Response
from scraper.models import PageResult


class BrowserManager:
    def __init__(self, headless: bool, user_agent: str, viewport_width: int, viewport_height: int,
                 request_delay: float = 1.5):
        self._headless = headless
        self._user_agent = user_agent
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._request_delay = request_delay
        self._playwright = None
        self._browser = None
        self._intercepted_data: dict = {}

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def fetch_page(self, url: str, timeout_ms: int = 15000) -> PageResult:
        self._intercepted_data = {}
        try:
            await asyncio.sleep(self._request_delay)
            context = await self._browser.new_context(
                user_agent=self._user_agent, viewport=self._viewport,
            )
            page = await context.new_page()
            page.on("response", self._on_response)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(1000)  # let AJAX settle — NOT networkidle
            html = await page.content()
            await page.close()
            await context.close()
            return PageResult(
                url=url, html=html, json_ld=self._extract_json_ld(html),
                intercepted_data=dict(self._intercepted_data), status_code=200,
            )
        except Exception as e:
            return PageResult(url=url, html="", json_ld=[], status_code=0, error=str(e))

    async def _on_response(self, response: Response) -> None:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = await response.json()
                path = urlparse(response.url).path
                self._intercepted_data[path] = data
            except Exception:
                pass

    def _extract_json_ld(self, html: str) -> list[dict]:
        matches = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        results = []
        for match in matches:
            try:
                parsed = json.loads(match)
                if isinstance(parsed, dict):
                    results.append(parsed)
                elif isinstance(parsed, list):
                    results.extend(item for item in parsed if isinstance(item, dict))
            except json.JSONDecodeError:
                pass
        return results

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
