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
        result = await self._call_tool(
            tool, max_tokens=256,
            content=(
                f"URL: {url}\n\nHTML snippet:\n{self._truncate_html(html_snippet)}\n\n"
                "Classify this page as 'listing' (category/catalog page with links to products), "
                "'product_detail' (single product page), or 'unknown'."
            ),
        )
        return result.get("page_type", "unknown")

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
        return await self._call_tool(
            tool,
            content=f"URL: {url}\n\nHTML:\n{self._truncate_html(html)}\n\nExtract all product data.",
        )

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
        result = await self._call_tool(
            tool,
            content=(
                f"URL: {url}\n\nLinks found on page:\n{self._extract_links(html)}\n\n"
                "Extract all subcategory links and product page links."
            ),
        )
        return result.get("subcategories", [])

    async def _call_tool(self, tool: dict, content: str, max_tokens: int | None = None) -> dict:
        """Call Claude with a single tool and return the tool_use input dict, or {} on no match."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            tools=[tool],
            messages=[{"role": "user", "content": content}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        return {}

    def _extract_links(self, html: str, max_links: int = 500) -> str:
        """Extract <a href> tags — always includes catalog/product links even if
        the anchor contains only an image (no visible text)."""
        anchors = re.findall(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
        lines = []
        seen: set[str] = set()
        for href, inner in anchors:
            if not href or href in seen:
                continue
            text = re.sub(r"<[^>]+>", "", inner).strip()
            is_product_url = "/catalog/" in href or "/product/" in href
            label = text or (href.rstrip("/").split("/")[-1].replace("-", " ").title() if is_product_url else "")
            if label:
                lines.append(f"{label} -> {href}")
                seen.add(href)
            if len(lines) >= max_links:
                break
        return "\n".join(lines)

    def _truncate_html(self, html: str, max_chars: int = 6000) -> str:
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        return html[:max_chars]
