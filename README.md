# Frontier Dental AI Scraper

An agent-based product scraping system for Safco Dental Supply. Built with LangGraph, Playwright, and Claude AI to discover, extract, and store structured dental product data.

---

## Architecture Overview

The system is a **LangGraph StateGraph** with four async agent nodes connected by conditional routing. Each node has a single responsibility and communicates only through immutable state updates.

```
                    ┌─────────┐
          ┌────────►│  fetch  │◄──────────────────────┐
          │         └────┬────┘                       │
          │         error│   success                  │
          │              ▼                            │
          │    ┌──────────────────────┐               │
          │    │ classify_and_extract │               │
          │    └──────────┬───────────┘               │
          │          error│   success                 │
          │               ▼                           │ next URL
          │    ┌───────────────────────┐              │
          │    │  validate_and_store   │──────────────┘
          │    └───────────────────────┘
          │                │ queue empty / max_pages
          │                ▼
          │             [END]
          │
     ┌────┴───────┐
     │  recover   │──► [END] (queue exhausted)
     └────────────┘
```

**Playwright intercepts AJAX responses** via `page.on("response")` — prices and stock data are loaded dynamically and cannot be captured with static HTTP clients.

**Claude AI is used selectively** — JSON-LD schema blocks are parsed first (zero API cost). Claude is only called when JSON-LD is absent or the page type is ambiguous.

---

## Agent Responsibilities

| Agent Node | Role |
|---|---|
| **fetch_node** | Launches a headless Chromium browser, loads the page, intercepts AJAX payloads, extracts JSON-LD blocks, and returns raw page data |
| **classify_and_extract_node** | Classifies the page type (listing vs product detail) using URL heuristics first, then Claude fallback. Extracts structured data from JSON-LD or via Claude tool-use |
| **validate_and_store_node** | Validates extracted data with Pydantic, upserts products to SQLite, and advances the URL queue |
| **recover_node** | Implements exponential retry on failure. Logs errors to the database only on final skip — retried URLs that eventually succeed leave no phantom error records |

---

## Why This Approach

- **LangGraph** provides a clean separation between node logic and routing, making it easy to add nodes (e.g. a deduplication agent) without touching existing nodes.
- **Playwright over httpx/BeautifulSoup** — Safco's prices and stock levels are loaded via AJAX. Static HTTP clients miss this data entirely.
- **JSON-LD first, Claude fallback** — most product pages include Schema.org `Product` blocks. Parsing these costs nothing. Claude is reserved for irregular layouts.
- **URL heuristics before LLM classification** — `/catalog/` paths are listings, `/product/` paths are detail pages. This avoids an API call on every URL.
- **Async throughout** — all I/O (browser, Claude API, SQLite) is non-blocking via `asyncio`, keeping the scraper fast without threading complexity.

---

## Setup & Execution

### Prerequisites

- Python 3.11+
- An Anthropic API key

### Install

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies and Chromium
pip install -e ".[dev]"
playwright install chromium
```

### Configure

```bash
# Copy the example env file and add your API key
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Review `config.yaml` to adjust scraping targets, rate limits, or output paths:
```yaml
scraping:
  seed_urls:
    - https://www.safcodental.com/catalog/sutures-surgical-products
    - https://www.safcodental.com/catalog/gloves
  max_pages: 500          # 0 = unlimited
  request_delay_seconds: 1.5

llm:
  model: claude-haiku-4-5-20251001   # cheapest; use claude-sonnet-4-6 for higher accuracy
  max_tokens: 1024
```

### Run

```bash
# Run the scraper
python -m scraper run

# Run with overrides
python -m scraper run --max-pages 50 --no-headless

# Check the last run's stats
python -m scraper status
```

### Test

```bash
pytest tests/ -v
```

---

## Output Schema

### SQLite Database (`output/products.db`)

**`products` table** — one row per unique SKU:

| Column | Type | Description |
|---|---|---|
| `sku` | TEXT UNIQUE | Product/item number (primary dedup key) |
| `product_name` | TEXT | Full product name |
| `brand` | TEXT | Manufacturer/brand |
| `category_hierarchy` | JSON | e.g. `["Gloves", "Exam Gloves", "Nitrile"]` |
| `product_url` | TEXT | Source URL |
| `price` | REAL | List price |
| `variants` | JSON | Array of `{variant_name, sku, price, availability}` |
| `unit_pack_size` | TEXT | e.g. `"Box of 100"` |
| `availability` | TEXT | e.g. `"In Stock"` |
| `description` | TEXT | Product description |
| `specifications` | JSON | Key-value attribute pairs |
| `image_urls` | JSON | Array of image URLs |
| `alternative_products` | JSON | Related/alternative SKUs |
| `scraped_at` | TIMESTAMP | First scraped (preserved on re-run) |
| `updated_at` | TIMESTAMP | Last updated |

**`scrape_runs` table** — one row per invocation, keyed by `thread_id` for resumability.

**`errors` table** — one row per permanently failed URL (after all retries exhausted).

### JSON Export (`output/products.json`)

Flat array of product objects matching the schema above, with JSON fields deserialized (not stored as strings).

---

## Limitations

- **No pagination handling** — if a category listing spans multiple pages, only the first page is processed. Page 2+ URLs would need to be discovered from "next page" links.
- **Price extraction is best-effort** — prices loaded via AJAX are intercepted but AJAX endpoint structure may change without notice.
- **No proxy rotation** — a single IP is used; aggressive scraping may trigger rate limiting or blocks.
- **No resume from mid-run** — the `thread_id` tracks run metadata but the URL queue is not persisted to disk, so a crash mid-run requires restarting from the seed URLs.
- **Claude fallback accuracy** — extraction quality depends on how well the HTML maps to the tool schema. Unusual product layouts may yield partial data.
- **Single-threaded crawling** — one page at a time; suitable for polite scraping, not high-throughput.

---

## Failure Handling

| Failure Type | Handling |
|---|---|
| Page load error / timeout | `recover_node` retries up to `max_retries` (default 3) with exponential backoff |
| LLM returns empty response | Treated as an error; routed to `recover_node` for retry |
| Pydantic validation failure | Logged as a warning; scraper advances to next URL without crashing |
| Permanently failed URL | Logged to `errors` table after all retries exhausted |
| Network intermittency | Playwright 15-second timeout; recover node handles the resulting error state |

Errors are only written to the database on **final skip** — URLs that succeed after retries leave no error records.

---

## Scaling to Full-Site Crawling in Production

| Concern | Approach |
|---|---|
| **Concurrency** | Replace single-browser sequential crawl with a worker pool (e.g. `asyncio.Queue` + N Playwright instances in parallel) |
| **Proxy rotation** | Integrate a residential proxy service (e.g. Bright Data, Oxylabs) with per-request rotation |
| **Persistent queue** | Persist `urls_to_visit` to Redis or SQLite so crashes resume mid-queue without restarting |
| **Distributed execution** | Package each node as a Celery task or deploy on a job queue (e.g. AWS SQS + Lambda) |
| **Rate limiting** | Per-domain token bucket; back off automatically on HTTP 429 responses |
| **Storage** | Swap SQLite for PostgreSQL; add a read replica for reporting queries |
| **Scheduling** | Cron-triggered re-scrapes to detect price/availability changes |
| **Secrets** | Move `ANTHROPIC_API_KEY` to AWS Secrets Manager or Vault; never in environment files |

---

## Monitoring Data Quality

| What to Monitor | How |
|---|---|
| **Missing required fields** | Alert when `sku` or `product_name` is null after extraction |
| **Price anomalies** | Flag products where price deviates >50% from last scraped value |
| **Extraction failure rate** | Track `errors / pages_fetched` per run; alert if >5% |
| **LLM fallback rate** | Log when Claude is used vs JSON-LD; high fallback rate signals site structure change |
| **Duplicate SKUs** | Monitor upsert vs insert ratio; unexpected duplicates indicate scraper loop |
| **Run duration drift** | Alert if a run takes 2x longer than baseline (may indicate throttling) |
| **Stale data** | Alert if `scraped_at` for any category hasn't been refreshed within SLA window |

---

## File Structure

```
src/scraper/
├── main.py          # CLI (click): run, status commands
├── models.py        # Pydantic models: Product, ProductVariant, ScrapingError, ScraperState
├── graph.py         # 4 LangGraph nodes + routing functions + graph builder
├── browser.py       # BrowserManager: Playwright + AJAX interception
├── llm.py           # LLMClient: Claude tool-use for classification and extraction
├── database.py      # SQLite: init, upsert_product, log_error, run tracking, JSON export
└── schema.sql       # DDL for all tables and indexes

tests/
├── conftest.py                  # Shared fixtures
├── test_models.py               # Data model validation
├── test_browser.py              # JSON-LD extraction, AJAX interception
├── test_llm.py                  # Claude tool-use response parsing
├── test_graph.py                # Node logic, routing, queue management
├── test_database.py             # DB operations, upsert, error logging
├── test_integration.py          # End-to-end pipeline tests
└── fixtures/
    ├── product_page.html        # Sample product page with JSON-LD
    └── category_page.html       # Sample category listing page

config.yaml          # Runtime configuration
.env.example         # API key template
pyproject.toml       # Dependencies and package config
```
