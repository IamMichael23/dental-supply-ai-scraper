# tests/test_browser.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scraper.browser import BrowserManager
from scraper.models import PageResult


class TestBrowserManager:
    def test_init(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720)
        assert bm._headless is True

    def test_extract_json_ld_found(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720)
        html = '<html><script type="application/ld+json">{"@type":"Product","name":"Test"}</script></html>'
        result = bm._extract_json_ld(html)
        assert result["@type"] == "Product"

    def test_extract_json_ld_missing(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720)
        result = bm._extract_json_ld("<html><body>no json-ld</body></html>")
        assert result is None

    async def test_on_response_captures_json(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720)
        mock_response = AsyncMock()
        mock_response.url = "https://example.com/api/prices"
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"price": 9.99}
        await bm._on_response(mock_response)
        assert "/api/prices" in bm._intercepted_data

    async def test_on_response_ignores_non_json(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720)
        mock_response = AsyncMock()
        mock_response.url = "https://example.com/image.png"
        mock_response.headers = {"content-type": "image/png"}
        await bm._on_response(mock_response)
        assert len(bm._intercepted_data) == 0

    async def test_fetch_page_returns_page_result(self):
        bm = BrowserManager(headless=True, user_agent="test", viewport_width=1280, viewport_height=720,
                            request_delay=0)
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html><body>test</body></html>"
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page
        bm._browser = AsyncMock()
        bm._browser.new_context.return_value = mock_context
        result = await bm.fetch_page("https://example.com/product/test", timeout_ms=5000)
        assert isinstance(result, PageResult)
        assert result.error is None
        assert result.url == "https://example.com/product/test"
