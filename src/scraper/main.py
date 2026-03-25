from __future__ import annotations
import asyncio
from pathlib import Path

import click
import structlog
import yaml
from dotenv import load_dotenv

from scraper.browser import BrowserManager
from scraper.llm import LLMClient
from scraper.graph import build_graph
from scraper.models import make_initial_state
from scraper import database


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    load_dotenv()
    with open(path) as f:
        return yaml.safe_load(f)


def setup_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )


@click.group()
def cli():
    """Frontier Dental AI Scraper"""
    pass


@cli.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--headless/--no-headless", default=None, help="Override headless mode")
@click.option("--max-pages", type=int, default=None, help="Override max pages")
def run(config_path: str, headless: bool | None, max_pages: int | None):
    """Run the scraper."""
    config = load_config(config_path)
    setup_logging(config.get("output", {}).get("log_dir", "output/logs"))
    log = structlog.get_logger()

    if headless is not None:
        config["browser"]["headless"] = headless
    if max_pages is not None:
        config["scraping"]["max_pages"] = max_pages

    asyncio.run(_run_scraper(config, log))


async def _run_scraper(config: dict, log) -> None:
    import os

    browser_cfg = config["browser"]
    browser = BrowserManager(
        headless=browser_cfg["headless"],
        user_agent=browser_cfg["user_agent"],
        viewport_width=browser_cfg["viewport_width"],
        viewport_height=browser_cfg["viewport_height"],
        request_delay=config["scraping"].get("request_delay_seconds", 1.5),
    )
    llm = LLMClient(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model=config["llm"]["model"],
        max_tokens=config["llm"].get("max_tokens", 4096),
    )

    db_path = config["output"]["database_path"]
    json_path = config["output"]["json_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    await database.init_db(db_path)
    await browser.start()

    seed_urls = config["scraping"]["seed_urls"]
    state = make_initial_state(seed_urls)
    run_id = await database.start_run(state["thread_id"], db_path)

    graph_config = {
        "db_path": db_path, "run_id": run_id,
        "base_url": config["scraping"]["base_url"],
        "max_retries": config.get("retry", {}).get("max_retries", 3),
        "max_pages": config["scraping"].get("max_pages", 0),  # 0 = unlimited
    }
    graph = build_graph(browser, llm, graph_config)

    log.info("starting_scrape", seed_urls=seed_urls, thread_id=state["thread_id"])

    try:
        final_state = await graph.ainvoke(state, config={"recursion_limit": 2000})
        stats = final_state.get("stats", {})
        await database.complete_run(run_id, stats, db_path)
        await database.export_json(db_path, json_path)
        log.info("scrape_complete", **stats)
    finally:
        await browser.close()


@cli.command()
@click.option("--db-path", default="output/products.db", help="Path to database")
def status(db_path: str):
    """Show scrape run status."""
    asyncio.run(_show_status(db_path))


async def _show_status(db_path: str) -> None:
    if not Path(db_path).exists():
        click.echo("No database found.")
        return
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT thread_id, status, total_products, total_errors, started_at, completed_at "
            "FROM scrape_runs ORDER BY id DESC LIMIT 5"
        )
        rows = await cursor.fetchall()
    if not rows:
        click.echo("No runs found.")
        return
    for row in rows:
        click.echo(
            f"Run {row[0]}: {row[1]} | Products: {row[2]} | Errors: {row[3]} | "
            f"Started: {row[4]} | Completed: {row[5] or 'in progress'}"
        )
