# tests/test_database.py
import json
import pytest
from pathlib import Path
from scraper.database import (
    init_db,
    upsert_product,
    log_error,
    start_run,
    complete_run,
    get_run_stats,
    export_json,
)
from scraper.models import ScrapingError


class TestDatabase:
    async def test_init_db_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "products" in tables
        assert "categories" in tables
        assert "scrape_runs" in tables
        assert "errors" in tables

    async def test_upsert_product_insert(self, tmp_path, sample_product):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        await upsert_product(sample_product, db_path)
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT sku FROM products")
            rows = await cursor.fetchall()
        assert rows[0][0] == "GL-1001"

    async def test_upsert_product_update(self, tmp_path, sample_product):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        await upsert_product(sample_product, db_path)
        sample_product.price = 15.99
        await upsert_product(sample_product, db_path)
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT price FROM products WHERE sku='GL-1001'"
            )
            row = await cursor.fetchone()
        assert row[0] == 15.99

    async def test_upsert_preserves_scraped_at(self, tmp_path, sample_product):
        """I3: scraped_at must be preserved on re-upsert; updated_at must change."""
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        await upsert_product(sample_product, db_path)
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT scraped_at, updated_at FROM products WHERE sku='GL-1001'"
            )
            first_scraped_at, first_updated_at = await cursor.fetchone()
        # Re-upsert with a changed field
        sample_product.price = 99.99
        await upsert_product(sample_product, db_path)
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT scraped_at, updated_at FROM products WHERE sku='GL-1001'"
            )
            second_scraped_at, second_updated_at = await cursor.fetchone()
        assert second_scraped_at == first_scraped_at, "scraped_at must not change on upsert"
        assert second_updated_at >= first_updated_at, "updated_at must be refreshed on upsert"

    async def test_log_error(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        run_id = await start_run("test-thread", db_path)
        err = ScrapingError(
            url="https://example.com",
            error_type="timeout",
            error_message="Timed out",
        )
        await log_error(err, run_id, db_path)
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM errors")
            count = (await cursor.fetchone())[0]
        assert count == 1

    async def test_start_and_complete_run(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        run_id = await start_run("test-thread", db_path)
        assert run_id is not None
        await complete_run(run_id, {"products_saved": 5, "errors": 1}, db_path)
        stats = await get_run_stats("test-thread", db_path)
        assert stats["total_products"] == 5
        assert stats["status"] == "completed"

    async def test_export_json(self, tmp_path, sample_product):
        db_path = str(tmp_path / "test.db")
        json_path = str(tmp_path / "out.json")
        await init_db(db_path)
        await upsert_product(sample_product, db_path)
        await export_json(db_path, json_path)
        data = json.loads(Path(json_path).read_text())
        assert len(data) == 1
        assert data[0]["sku"] == "GL-1001"
