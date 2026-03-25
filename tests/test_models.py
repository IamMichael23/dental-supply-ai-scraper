# tests/test_models.py
import pytest
from datetime import datetime, timezone
from scraper.models import Product, ProductVariant, Category, ScrapingError, PageResult, ScraperState


class TestProductVariant:
    def test_create_variant(self):
        v = ProductVariant(variant_name="Large", sku="GL-001-L", price=12.99, availability="In Stock")
        assert v.sku == "GL-001-L"

    def test_variant_optional_fields(self):
        v = ProductVariant(sku="GL-001")
        assert v.variant_name is None
        assert v.price is None


class TestProduct:
    def test_create_full_product(self, sample_product):
        assert sample_product.sku == "GL-1001"
        assert len(sample_product.variants) == 2

    def test_minimal_product(self):
        p = Product(product_name="Test", sku="T-001", category_hierarchy=["Test"],
                    product_url="https://example.com/product/test")
        assert p.brand is None
        assert p.variants == []

    def test_product_json_serializable(self, sample_product):
        d = sample_product.model_dump(mode="json")
        assert isinstance(d["scraped_at"], str)


class TestCategory:
    def test_create_category(self):
        c = Category(name="Gloves", url="https://www.safcodental.com/catalog/gloves")
        assert c.parent_category is None


class TestScrapingError:
    def test_create_error(self):
        e = ScrapingError(url="https://example.com", error_type="timeout", error_message="Timed out")
        assert e.attempt_count == 1


class TestPageResult:
    def test_create_page_result(self):
        pr = PageResult(url="https://example.com", html="<html></html>",
                        json_ld=None, intercepted_data={}, status_code=200, error=None)
        assert pr.status_code == 200


class TestScraperState:
    def test_initial_state(self):
        from scraper.models import make_initial_state
        state = make_initial_state(
            seed_urls=["https://example.com/catalog/gloves"],
            thread_id="test-run-1",
        )
        assert state["current_url"] == "https://example.com/catalog/gloves"
        assert state["stats"]["products_saved"] == 0
