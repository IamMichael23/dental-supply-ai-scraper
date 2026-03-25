import os
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_browser():
    mock = AsyncMock()
    mock.fetch_page.return_value = MagicMock(
        url="https://www.safcodental.com/product/test",
        html="<html><body>test</body></html>",
        json_ld=None, intercepted_data={}, status_code=200, error=None,
    )
    return mock


@pytest.fixture
def mock_llm():
    mock = AsyncMock()
    mock.classify_page.return_value = "product_detail"
    mock.extract_product_data.return_value = {"product_name": "Test", "sku": "TEST-001", "price": 9.99}
    return mock
