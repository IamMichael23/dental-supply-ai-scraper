# tests/test_integration.py
import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock
from scraper.models import make_initial_state, PageResult
from scraper.graph import build_graph
from scraper import database


class TestIntegration:
    async def test_product_page_end_to_end(self, tmp_path, mock_llm):
        """Full pipeline: fetch a product page, extract, validate, store."""
        db_path = str(tmp_path / "test.db")
        json_path = str(tmp_path / "products.json")
        await database.init_db(db_path)
        run_id = await database.start_run("integration-test", db_path)

        product_html = Path("tests/fixtures/product_page.html").read_text()
        mock_browser = AsyncMock()
        mock_browser.fetch_page.return_value = PageResult(
            url="https://www.safcodental.com/product/nitrile-gloves",
            html=product_html, json_ld=None, intercepted_data={}, status_code=200,
        )
        mock_llm.extract_product_data.return_value = {
            "product_name": "Nitrile Exam Gloves", "sku": "GL-1001",
            "price": 12.99, "category_hierarchy": ["Gloves"],
            "product_url": "https://www.safcodental.com/product/nitrile-gloves",
        }

        config = {
            "max_retries": 3, "db_path": db_path, "run_id": run_id,
            "base_url": "https://www.safcodental.com",
        }
        graph = build_graph(mock_browser, mock_llm, config)
        state = make_initial_state(
            seed_urls=["https://www.safcodental.com/product/nitrile-gloves"],
            thread_id="integration-test",
        )

        final_state = await graph.ainvoke(state)

        # Verify product was stored
        assert final_state["stats"]["products_saved"] == 1

        # Verify DB has the product
        await database.export_json(db_path, json_path)
        data = json.loads(Path(json_path).read_text())
        assert len(data) == 1
        assert data[0]["sku"] == "GL-1001"

    async def test_error_recovery_path(self, tmp_path, mock_llm):
        """Fetch fails, recover retries, then succeeds."""
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("recovery-test", db_path)

        mock_browser = AsyncMock()
        # First call fails, second succeeds
        mock_browser.fetch_page.side_effect = [
            PageResult(url="https://example.com/product/x", html="", json_ld=None, status_code=0, error="timeout"),
            PageResult(url="https://example.com/product/x", html="<html>ok</html>", json_ld=None,
                       intercepted_data={}, status_code=200),
        ]
        mock_llm.extract_product_data.return_value = {
            "product_name": "Test", "sku": "T-001", "price": 5.0,
            "category_hierarchy": ["Test"],
            "product_url": "https://example.com/product/x",
        }

        config = {
            "max_retries": 3, "db_path": db_path, "run_id": run_id,
            "base_url": "https://example.com",
        }
        graph = build_graph(mock_browser, mock_llm, config)
        state = make_initial_state(["https://example.com/product/x"], "recovery-test")

        final_state = await graph.ainvoke(state)

        # Should have recovered and stored the product
        assert final_state["stats"]["products_saved"] == 1
        assert mock_browser.fetch_page.call_count == 2
