# Frontier Dental AI Scraper

## Architecture

LangGraph StateGraph with 9 async nodes: navigator, pick_next_url, fetch_page, classifier, extract_listings, extract_product, validator, store, recovery. Playwright intercepts AJAX responses via `page.on("response")` for prices/stock. Claude Sonnet extracts structured data via tool_use.

## Tech Stack

Python 3.11+, LangGraph, Playwright, Claude API (Sonnet), SQLite, Pydantic, click, structlog

## Critical Rules

- NEVER use `wait_until="networkidle"` — use `page.on("response")` to intercept AJAX
- NEVER use httpx/BeautifulSoup — site requires JS execution for prices/stock
- ALL code is `async def` — use `graph.ainvoke()`, never mix sync/async
- NEVER mutate LangGraph state in-place — return partial updates only
- JSON-LD first, Claude fallback second — minimize API costs
- URL heuristic before LLM call — `/catalog/` = listing, `/product/` = detail
- 15-second max timeout on all page loads
- Import style: `from scraper.models import Product` (absolute, not relative)

## Interface Contracts

```python
# tools/browser.py — class-based
class BrowserManager:
    def __init__(self, headless, user_agent, viewport_width, viewport_height): ...
    async def start(self) -> None: ...
    async def fetch_page(self, url: str, timeout_ms: int = 15000) -> PageResult: ...
    async def close(self) -> None: ...

@dataclass
class PageResult:
    url: str
    html: str
    json_ld: Optional[dict]
    intercepted_data: dict       # AJAX payloads keyed by endpoint
    status_code: int
    error: Optional[str]

# tools/llm.py — class-based
class LLMClient:
    def __init__(self, api_key: str, model: str): ...
    async def classify_page(self, html_snippet: str, url: str) -> str: ...
    async def extract_product_data(self, html: str, url: str) -> dict: ...
    async def extract_subcategories(self, html: str, url: str) -> list[dict]: ...

# storage/database.py — module-level async functions
async def init_db(db_path: str) -> None: ...
async def upsert_product(product: Product, db_path: str) -> None: ...
async def log_error(error: ScrapingError, db_path: str) -> None: ...
async def get_run_stats(thread_id: str, db_path: str) -> dict: ...

# All graph node functions:
async def node_name(state: dict) -> dict:  # returns partial state update
```

## Commands

```bash
# Install
pip install -e ".[dev]" && playwright install chromium

# Test
pytest tests/ -v

# Lint
ruff check src/

# Run scraper
python -m scraper run

# Check status
python -m scraper status
```

## File Structure

```
src/scraper/
├── main.py              # CLI (click)
├── config.py            # Settings from config.yaml + .env
├── models.py            # Product, ProductVariant, Category, ScrapingError
├── state.py             # ScraperState TypedDict + reducers
├── graph.py             # StateGraph assembly
├── agents/
│   ├── navigator.py
│   ├── classifier.py
│   ├── extractor.py
│   ├── validator.py
│   └── recovery.py
├── tools/
│   ├── browser.py       # Playwright + on("response") interception
│   ├── llm.py           # Claude client + tool_use + prompt caching
│   └── rate_limiter.py
├── storage/
│   ├── database.py      # SQLite ops (aiosqlite)
│   ├── json_export.py   # JSONL export
│   └── schema.sql       # DDL
└── utils/
    └── logging.py       # structlog setup
```
