from __future__ import annotations
import re
import anthropic


class LLMClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def classify_page(self, html_snippet: str, url: str) -> str:
        tool = {
            "name": "classify",
            "description": "Classify a dental supply web page type.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_type": {
                        "type": "string",
                        "enum": ["listing", "product_detail", "unknown"],
                    }
                },
                "required": ["page_type"],
            },
        }
        response = await self._client.messages.create(
            model=self._model, max_tokens=256, tools=[tool],
            messages=[{
                "role": "user",
                "content": (
                    f"URL: {url}\n\nHTML snippet:\n{self._truncate_html(html_snippet)}\n\n"
                    "Classify this page as 'listing' (category/catalog page with links to products), "
                    "'product_detail' (single product page), or 'unknown'."
                ),
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input["page_type"]
        return "unknown"

    async def extract_product_data(self, html: str, url: str) -> dict:
        tool = {
            "name": "extract_product",
            "description": "Extract structured product data from a dental supply product page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "brand": {"type": "string"},
                    "sku": {"type": "string"},
                    "price": {"type": "number"},
                    "category_hierarchy": {"type": "array", "items": {"type": "string"}},
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "variant_name": {"type": "string"},
                                "sku": {"type": "string"},
                                "price": {"type": "number"},
                                "availability": {"type": "string"},
                            },
                        },
                    },
                    "unit_pack_size": {"type": "string"},
                    "availability": {"type": "string"},
                    "description": {"type": "string"},
                    "specifications": {"type": "object"},
                    "image_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["product_name", "sku"],
            },
        }
        response = await self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, tools=[tool],
            messages=[{
                "role": "user",
                "content": f"URL: {url}\n\nHTML:\n{self._truncate_html(html)}\n\nExtract all product data.",
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        return {}

    async def extract_subcategories(self, html: str, url: str) -> list[dict]:
        tool = {
            "name": "extract_links",
            "description": "Extract subcategory and product links from a listing page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "subcategories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["name", "url"],
                        },
                    },
                },
                "required": ["subcategories"],
            },
        }
        response = await self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, tools=[tool],
            messages=[{
                "role": "user",
                "content": (
                    f"URL: {url}\n\nHTML:\n{self._truncate_html(html)}\n\n"
                    "Extract all subcategory links and product page links."
                ),
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input.get("subcategories", [])
        return []

    def _truncate_html(self, html: str, max_chars: int = 6000) -> str:
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        return html[:max_chars]
