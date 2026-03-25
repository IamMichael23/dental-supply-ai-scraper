import pytest
from unittest.mock import AsyncMock, MagicMock
from scraper.models import Product, ProductVariant, PageResult
from datetime import datetime, timezone


@pytest.fixture
def sample_product():
    return Product(
        product_name="Nitrile Exam Gloves", brand="SafeTouch", sku="GL-1001",
        category_hierarchy=["Gloves", "Nitrile Gloves"],
        product_url="https://www.safcodental.com/product/nitrile-exam-gloves",
        price=12.99,
        variants=[
            ProductVariant(variant_name="Small", sku="GL-1001-S", price=12.99, availability="In Stock"),
            ProductVariant(variant_name="Medium", sku="GL-1001-M", price=12.99, availability="In Stock"),
        ],
        unit_pack_size="100/box", availability="In Stock",
        description="Premium nitrile exam gloves",
        scraped_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_browser():
    mock = AsyncMock()
    mock.fetch_page.return_value = PageResult(
        url="https://www.safcodental.com/product/test",
        html="<html><body>test</body></html>",
        json_ld=None, intercepted_data={}, status_code=200, error=None,
    )
    return mock


@pytest.fixture
def mock_llm():
    mock = AsyncMock()
    mock.classify_page.return_value = "product_detail"
    mock.extract_product_data.return_value = {
        "product_name": "Test", "sku": "TEST-001", "price": 9.99,
        "category_hierarchy": ["Test"], "product_url": "https://example.com/product/test",
    }
    mock.extract_subcategories.return_value = []
    return mock
