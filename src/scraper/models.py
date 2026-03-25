from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Optional, TypedDict
from operator import add
from pydantic import BaseModel, Field
import uuid


class ProductVariant(BaseModel):
    variant_name: Optional[str] = None
    sku: str
    price: Optional[float] = None
    availability: Optional[str] = None


class Product(BaseModel):
    product_name: str
    brand: Optional[str] = None
    sku: str
    category_hierarchy: list[str]
    product_url: str
    price: Optional[float] = None
    variants: list[ProductVariant] = Field(default_factory=list)
    unit_pack_size: Optional[str] = None
    availability: Optional[str] = None
    description: Optional[str] = None
    specifications: dict = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    alternative_products: list[str] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Category(BaseModel):
    name: str
    url: str
    parent_category: Optional[str] = None
    subcategories: list[str] = Field(default_factory=list)


class ScrapingError(BaseModel):
    url: str
    error_type: str
    error_message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 1


@dataclass
class PageResult:
    url: str
    html: str
    json_ld: Optional[dict]
    intercepted_data: dict = field(default_factory=dict)
    status_code: int = 200
    error: Optional[str] = None


class ScraperState(TypedDict, total=False):
    """LangGraph state. Only visited_urls uses an append reducer (add).
    urls_to_visit is a managed queue replaced wholesale by nodes — no add reducer."""
    urls_to_visit: list[str]
    visited_urls: Annotated[list[str], add]
    current_url: str
    page_result: Optional[dict]
    page_type: str
    extracted_data: Optional[dict]
    error: Optional[str]
    retry_count: int
    thread_id: str
    stats: dict


def make_initial_state(seed_urls: list[str], thread_id: str | None = None) -> dict:
    return {
        "urls_to_visit": seed_urls[1:] if len(seed_urls) > 1 else [],
        "visited_urls": [],
        "current_url": seed_urls[0] if seed_urls else "",
        "page_result": None,
        "page_type": "",
        "extracted_data": None,
        "error": None,
        "retry_count": 0,
        "thread_id": thread_id or uuid.uuid4().hex[:12],
        "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 0},
    }
