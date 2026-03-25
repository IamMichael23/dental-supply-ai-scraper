# tests/test_graph.py
import pytest
from unittest.mock import AsyncMock
from scraper.graph import (
    _classify_by_url, fetch_node, classify_and_extract_node,
    validate_and_store_node, recover_node,
    route_after_fetch, route_after_extract, route_after_validate,
    route_after_recover, build_graph,
)
from scraper.models import PageResult, make_initial_state


class TestURLHeuristic:
    def test_catalog_url_is_listing(self):
        assert _classify_by_url("https://safcodental.com/catalog/gloves") == "listing"

    def test_category_url_is_listing(self):
        assert _classify_by_url("https://safcodental.com/category/gloves") == "listing"

    def test_product_url_is_detail(self):
        assert _classify_by_url("https://safcodental.com/product/nitrile") == "product_detail"

    def test_unknown_url(self):
        assert _classify_by_url("https://safcodental.com/about") == "unknown"


class TestRouting:
    def test_route_after_fetch_error(self):
        assert route_after_fetch({"error": "timeout"}) == "recover"

    def test_route_after_fetch_ok(self):
        assert route_after_fetch({"error": None}) == "classify_and_extract"

    def test_route_after_extract_error(self):
        assert route_after_extract({"error": "parse failed"}) == "recover"

    def test_route_after_extract_ok(self):
        assert route_after_extract({"error": None}) == "validate_and_store"

    def test_route_after_validate_done(self):
        assert route_after_validate({"urls_to_visit": [], "current_url": ""}) == "__end__"

    def test_route_after_validate_continue(self):
        assert route_after_validate({"urls_to_visit": ["x"], "current_url": "x"}) == "fetch"

    def test_route_after_recover_retry(self):
        assert route_after_recover({"retry_count": 1, "error": "retry", "current_url": "https://example.com/product/fail"}) == "fetch"

    def test_route_after_recover_skip_with_next_url(self):
        # After skipping a URL, recover sets current_url to the next URL → fetch it
        assert route_after_recover({"retry_count": 0, "error": None, "current_url": "https://example.com/product/next"}) == "fetch"

    def test_route_after_recover_skip_empty_queue(self):
        # After skipping last URL, current_url is empty → end
        assert route_after_recover({"retry_count": 0, "error": None, "current_url": ""}) == "__end__"


class TestFetchNode:
    async def test_success(self, mock_browser):
        state = make_initial_state(["https://example.com/product/x"], "test")
        result = await fetch_node(state, browser=mock_browser)
        assert result["error"] is None
        assert result["page_result"] is not None
        mock_browser.fetch_page.assert_called_once_with("https://example.com/product/x")

    async def test_error(self, mock_browser):
        mock_browser.fetch_page.return_value = PageResult(
            url="https://example.com", html="", json_ld=None, status_code=0, error="timeout"
        )
        state = make_initial_state(["https://example.com"], "test")
        result = await fetch_node(state, browser=mock_browser)
        assert result["error"] == "timeout"


class TestClassifyAndExtractNode:
    async def test_product_page_via_heuristic(self, mock_llm):
        state = {
            "current_url": "https://safcodental.com/product/gloves",
            "page_result": {
                "html": "<html>product</html>", "json_ld": None,
                "url": "https://safcodental.com/product/gloves",
            },
            "error": None,
        }
        result = await classify_and_extract_node(state, llm=mock_llm)
        assert result["page_type"] == "product_detail"
        assert result["extracted_data"] is not None

    async def test_listing_page_via_heuristic(self, mock_llm):
        mock_llm.extract_subcategories.return_value = [
            {"name": "Nitrile", "url": "/catalog/nitrile"}
        ]
        state = {
            "current_url": "https://safcodental.com/catalog/gloves",
            "page_result": {
                "html": "<html>catalog</html>", "json_ld": None,
                "url": "https://safcodental.com/catalog/gloves",
            },
            "error": None,
        }
        result = await classify_and_extract_node(state, llm=mock_llm)
        assert result["page_type"] == "listing"
        assert "urls" in result["extracted_data"]

    async def test_json_ld_product_skips_llm(self, mock_llm):
        state = {
            "current_url": "https://safcodental.com/product/test",
            "page_result": {
                "html": "<html></html>",
                "json_ld": [
                    {"@type": "Organization", "name": "Acme"},
                    {"@type": "Product", "name": "Test", "sku": "T-001"},
                ],
                "url": "https://safcodental.com/product/test",
            },
            "error": None,
        }
        result = await classify_and_extract_node(state, llm=mock_llm)
        assert result["page_type"] == "product_detail"
        # LLM extract_product_data should NOT be called when JSON-LD has product data
        mock_llm.extract_product_data.assert_not_called()

    async def test_unknown_url_falls_back_to_llm(self, mock_llm):
        mock_llm.classify_page.return_value = "product_detail"
        state = {
            "current_url": "https://safcodental.com/some/path",
            "page_result": {
                "html": "<html>product</html>", "json_ld": None,
                "url": "https://safcodental.com/some/path",
            },
            "error": None,
        }
        result = await classify_and_extract_node(state, llm=mock_llm)
        mock_llm.classify_page.assert_called_once()
        assert result["page_type"] == "product_detail"


class TestValidateAndStoreNode:
    async def test_stores_product(self, tmp_path):
        from scraper import database
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("test", db_path)
        state = {
            "page_type": "product_detail",
            "extracted_data": {
                "product": {
                    "product_name": "Test", "sku": "T-001",
                    "category_hierarchy": ["Test"],
                    "product_url": "https://example.com/product/test",
                }
            },
            "urls_to_visit": [],
            "visited_urls": ["https://example.com/product/test"],
            "current_url": "https://example.com/product/test",
            "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 1},
            "error": None,
            "retry_count": 0,
        }
        result = await validate_and_store_node(
            state, db_path=db_path, run_id=run_id, base_url="https://example.com",
        )
        assert result["stats"]["products_saved"] == 1

    async def test_advances_url_queue(self, tmp_path):
        from scraper import database
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("test", db_path)
        state = {
            "page_type": "listing",
            "extracted_data": {
                "urls": [
                    {"name": "Sub", "url": "/catalog/sub"},
                ]
            },
            "urls_to_visit": ["https://example.com/product/other"],
            "visited_urls": ["https://example.com/catalog/main"],
            "current_url": "https://example.com/catalog/main",
            "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 1},
            "error": None,
            "retry_count": 0,
        }
        result = await validate_and_store_node(
            state, db_path=db_path, run_id=run_id, base_url="https://example.com",
        )
        assert result["current_url"] != ""

    async def test_no_url_duplication(self, tmp_path):
        """C1: returned urls_to_visit must be the exact remaining queue, not duplicated."""
        from scraper import database
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("test", db_path)
        state = {
            "page_type": "listing",
            "extracted_data": {"urls": [{"name": "A", "url": "/product/a"}]},
            "urls_to_visit": [
                "https://example.com/product/b",
                "https://example.com/product/c",
            ],
            "visited_urls": ["https://example.com/catalog/main"],
            "current_url": "https://example.com/catalog/main",
            "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 1},
            "error": None,
            "retry_count": 0,
        }
        result = await validate_and_store_node(
            state, db_path=db_path, run_id=run_id, base_url="https://example.com",
        )
        # The next URL is popped into current_url; remaining should be exactly 2 (b + c minus the popped one + new a)
        all_urls = [result["current_url"]] + result["urls_to_visit"]
        assert len(all_urls) == len(set(all_urls)), "URL duplication detected in queue"
        assert len(all_urls) == 3  # /product/a + /product/b + /product/c


class TestRecoverNode:
    async def test_retry(self, tmp_path):
        from scraper import database
        import aiosqlite
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("test", db_path)
        state = {
            "current_url": "https://example.com/product/fail",
            "error": "timeout",
            "retry_count": 0,
            "urls_to_visit": [],
            "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 0},
        }
        result = await recover_node(state, max_retries=3, db_path=db_path, run_id=run_id)
        assert result["retry_count"] == 1
        assert result["current_url"] == "https://example.com/product/fail"
        # C3: retries should NOT log an error row — only final skips should
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM errors")
            count = (await cursor.fetchone())[0]
        assert count == 0, "retry should not log an error — only final skip should"

    async def test_skip_after_max_retries(self, tmp_path):
        from scraper import database
        db_path = str(tmp_path / "test.db")
        await database.init_db(db_path)
        run_id = await database.start_run("test", db_path)
        state = {
            "current_url": "https://example.com/product/fail",
            "error": "timeout",
            "retry_count": 3,
            "urls_to_visit": ["https://example.com/product/next"],
            "stats": {"products_saved": 0, "errors": 0, "pages_fetched": 0},
        }
        result = await recover_node(state, max_retries=3, db_path=db_path, run_id=run_id)
        assert result["retry_count"] == 0
        assert result["error"] is None
        assert result["current_url"] == "https://example.com/product/next"


class TestBuildGraph:
    def test_compiles(self, mock_browser, mock_llm):
        config = {
            "max_retries": 3, "db_path": ":memory:",
            "base_url": "https://safcodental.com", "run_id": 1,
        }
        graph = build_graph(mock_browser, mock_llm, config)
        assert graph is not None
