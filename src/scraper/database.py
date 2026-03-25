from __future__ import annotations
import json
from pathlib import Path
import aiosqlite
from scraper.models import Product, ScrapingError

# Fields stored as JSON strings in SQLite — must be deserialized on read
JSON_FIELDS = ("category_hierarchy", "variants", "specifications", "image_urls", "alternative_products")


async def init_db(db_path: str) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(schema)
        await db.commit()


async def upsert_product(product: Product, db_path: str) -> None:
    data = product.model_dump(mode="json")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO products
               (sku, product_name, brand, category_hierarchy, product_url, price,
                variants, unit_pack_size, availability, description, specifications,
                image_urls, alternative_products, scraped_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(sku) DO UPDATE SET
                   product_name=excluded.product_name,
                   brand=excluded.brand,
                   category_hierarchy=excluded.category_hierarchy,
                   product_url=excluded.product_url,
                   price=excluded.price,
                   variants=excluded.variants,
                   unit_pack_size=excluded.unit_pack_size,
                   availability=excluded.availability,
                   description=excluded.description,
                   specifications=excluded.specifications,
                   image_urls=excluded.image_urls,
                   alternative_products=excluded.alternative_products,
                   updated_at=CURRENT_TIMESTAMP
            """,
            (
                data["sku"],
                data["product_name"],
                data.get("brand"),
                json.dumps(data["category_hierarchy"]),
                data["product_url"],
                data.get("price"),
                json.dumps(data.get("variants", [])),
                data.get("unit_pack_size"),
                data.get("availability"),
                data.get("description"),
                json.dumps(data.get("specifications", {})),
                json.dumps(data.get("image_urls", [])),
                json.dumps(data.get("alternative_products", [])),
            ),
        )
        await db.commit()


async def log_error(error: ScrapingError, run_id: int, db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO errors
               (run_id, url, error_type, error_message, attempt_count)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, error.url, error.error_type, error.error_message, error.attempt_count),
        )
        await db.commit()


async def start_run(thread_id: str, db_path: str) -> int:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO scrape_runs (thread_id) VALUES (?)", (thread_id,),
        )
        await db.commit()
        return cursor.lastrowid


async def complete_run(run_id: int, stats: dict, db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE scrape_runs
               SET completed_at=CURRENT_TIMESTAMP,
               total_products=?, total_errors=?, status='completed'
               WHERE id=?""",
            (stats.get("products_saved", 0), stats.get("errors", 0), run_id),
        )
        await db.commit()


async def get_run_stats(thread_id: str, db_path: str) -> dict:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """SELECT total_products, total_errors, status FROM scrape_runs
               WHERE thread_id=? ORDER BY id DESC LIMIT 1""",
            (thread_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {"total_products": row[0], "total_errors": row[1], "status": row[2]}
        return {}


async def export_json(db_path: str, json_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products")
        rows = await cursor.fetchall()
    products = []
    for row in rows:
        product = dict(row)
        for field in JSON_FIELDS:
            if isinstance(product.get(field), str):
                product[field] = json.loads(product[field])
        products.append(product)
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(products, indent=2, default=str))
