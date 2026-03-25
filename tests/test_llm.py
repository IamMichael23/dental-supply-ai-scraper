# tests/test_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from scraper.llm import LLMClient


class TestLLMClient:
    def test_init(self):
        client = LLMClient(api_key="test-key", model="claude-sonnet-4-20250514")
        assert client._model == "claude-sonnet-4-20250514"

    async def test_classify_page_returns_valid_type(self):
        client = LLMClient(api_key="test-key", model="test")
        client._client = AsyncMock()
        client._client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="tool_use", input={"page_type": "product_detail"})]
        )
        result = await client.classify_page("<html>product</html>", "https://example.com/product/x")
        assert result == "product_detail"

    async def test_classify_page_fallback_unknown(self):
        client = LLMClient(api_key="test-key", model="test")
        client._client = AsyncMock()
        client._client.messages.create.return_value = MagicMock(content=[])
        result = await client.classify_page("<html></html>", "https://example.com")
        assert result == "unknown"

    async def test_extract_product_data_returns_dict(self):
        client = LLMClient(api_key="test-key", model="test")
        client._client = AsyncMock()
        client._client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="tool_use", input={
                "product_name": "Gloves", "sku": "GL-001", "price": 9.99,
            })]
        )
        result = await client.extract_product_data("<html>product</html>", "https://example.com/product/x")
        assert result["sku"] == "GL-001"

    async def test_extract_subcategories_returns_list(self):
        client = LLMClient(api_key="test-key", model="test")
        client._client = AsyncMock()
        client._client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="tool_use", input={
                "subcategories": [{"name": "Nitrile", "url": "/catalog/nitrile"}]
            })]
        )
        result = await client.extract_subcategories("<html>catalog</html>", "https://example.com/catalog/gloves")
        assert len(result) == 1
        assert result[0]["name"] == "Nitrile"

    def test_truncate_html_strips_scripts(self):
        client = LLMClient(api_key="test-key", model="test")
        html = "<html><script>var x=1;</script><body>content</body></html>"
        result = client._truncate_html(html, max_chars=1000)
        assert "<script>" not in result
        assert "content" in result

    def test_truncate_html_limits_length(self):
        client = LLMClient(api_key="test-key", model="test")
        long_html = "<html>" + "x" * 10000 + "</html>"
        result = client._truncate_html(long_html, max_chars=100)
        assert len(result) <= 100
