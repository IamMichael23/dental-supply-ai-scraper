# Frontier Dental AI Scraper — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use agent-team-driven-development to execute this plan.

> **Model config:** Lead runs on Opus. All specialist agents (implementers + reviewers) must be spawned with `model: "sonnet"` to use Claude Sonnet.

**Goal:** Build an agent-based scraping system that crawls 2 categories on safcodental.com, extracts all product data using Playwright + Claude, and stores results in JSON + SQLite.

**Architecture:** LangGraph StateGraph with 9 async nodes (navigator, pick_next_url, fetch_page, classifier, extract_listings, extract_product, validator, store, recovery). Playwright intercepts AJAX responses via `page.on("response")` for prices/stock. Claude Sonnet extracts structured data via tool_use.

**Tech Stack:** Python 3.11+, LangGraph, Playwright, Claude API (Sonnet), SQLite, Pydantic, click, structlog

---

## Wave Analysis

### Specialists

| Role | Expertise | Tasks |
|------|-----------|-------|
| browser-engineer | Playwright, async HTTP, AJAX interception, rate limiting | Tasks 4, 8 |
| agent-engineer | LangGraph nodes, Claude API prompts, extraction logic | Tasks 5, 7 |
| storage-engineer | SQLite, Pydantic validation, data normalization, JSON export | Tasks 6, 9 |

### Waves

**Wave 0: Foundation** — Lead only (sequential, must complete before team spawns)
- Task 1 (Lead) — Project scaffold, CLAUDE.md, config, dependencies
- Task 2 (Lead) — Core data models (Product, Category, State) + conftest fixtures
- Task 3 (Lead) — Config loading + structured logging

*No parallelism — these are sequential foundations everything else imports.*

**Wave 1: Tools & Storage** — 3 specialists parallel
- Task 4 (browser-engineer) — Playwright browser with `on("response")` interception + rate limiter
- Task 5 (agent-engineer) — Claude LLM client with tool_use + prompt caching
- Task 6 (storage-engineer) — SQLite database + JSONL export

*Parallel-safe because:* Different directories (`tools/browser.py`, `tools/llm.py`, `storage/*`), no import relationship between them. All import only from `scraper.models` and `scraper.config` (Wave 0 outputs).

*Depends on Wave 0:* `models.py` (Product, ScrapingError), `config.py` (Settings), `conftest.py` (mock fixtures)

**Wave 2: Agent Nodes** — 3 specialists parallel
- Task 7 (agent-engineer) — Navigator + Classifier nodes
- Task 8 (browser-engineer) — Extractor node (listings + product detail)
- Task 9 (storage-engineer) — Validator + Recovery nodes

*Parallel-safe because:* Different files in `agents/` (navigator.py+classifier.py, extractor.py, validator.py+recovery.py). No import relationship between agent nodes — they only share the state schema.

*Depends on Wave 1:* `tools/browser.py` (fetch_page), `tools/llm.py` (classify_page, extract_product_data), `storage/database.py` (upsert_product)

**Wave 3: Assembly** — Lead + 1 specialist
- Task 10 (agent-engineer) — Graph assembly: wire all nodes, edges, routing
- Task 11 (Lead) — CLI entry point

*Sequential:* Task 11 depends on Task 10 (CLI invokes graph).

*Depends on Wave 2:* All agent node functions, all tool functions

**Wave 4: Verification & Docs** — Lead only
- Task 12 (Lead) — Integration testing against real site
- Task 13 (Lead) — README + sample output

### Dependency Graph

```
Task 1 ──→ Task 2 ──→ Task 3 ──┐
                                ├──→ Task 4 ──→ Task 8 ──┐
                                ├──→ Task 5 ──→ Task 7 ──┤
                                ├──→ Task 6 ──→ Task 9 ──┤
                                                          ├──→ Task 10 ──→ Task 11 ──→ Task 12 ──→ Task 13
```

---

## Critical Rules (for CLAUDE.md)

- NEVER use `wait_until="networkidle"` — use `page.on("response")` to intercept AJAX
- NEVER use httpx/BeautifulSoup — site requires JS execution for prices/stock
- ALL code is `async def` — use `graph.ainvoke()`, never mix sync/async
- NEVER mutate LangGraph state in-place — return partial updates only
- JSON-LD first, Claude fallback second — minimize API costs
- URL heuristic before LLM call — `/catalog/` = listing, `/product/` = detail
- 15-second max timeout on all page loads
- Import style: `from scraper.models import Product` (absolute, not relative)

---

## Interface Contracts (all specialists use these)

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

---

## File Structure

```
frontier-dental-scraper/
├── CLAUDE.md
├── pyproject.toml
├── .env.example / .env (gitignored)
├── .gitignore
├── config.yaml
├── src/scraper/
│   ├── __init__.py
│   ├── main.py              # CLI (click)
│   ├── config.py            # Settings from config.yaml + .env
│   ├── models.py            # Product, ProductVariant, Category, ScrapingError
│   ├── state.py             # ScraperState TypedDict + reducers
│   ├── graph.py             # StateGraph assembly
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── navigator.py
│   │   ├── classifier.py
│   │   ├── extractor.py
│   │   ├── validator.py
│   │   └── recovery.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── browser.py       # Playwright + on("response") interception
│   │   ├── llm.py           # Claude client + tool_use + prompt caching
│   │   └── rate_limiter.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py      # SQLite ops (aiosqlite)
│   │   ├── json_export.py   # JSONL export
│   │   └── schema.sql       # DDL
│   └── utils/
│       ├── __init__.py
│       └── logging.py       # structlog setup
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_browser.py
│   ├── test_llm.py
│   ├── test_navigator.py
│   ├── test_classifier.py
│   ├── test_extractor.py
│   ├── test_validator.py
│   ├── test_recovery.py
│   ├── test_database.py
│   ├── test_json_export.py
│   ├── test_graph.py
│   └── fixtures/
│       ├── category_page.html
│       └── product_page.html
└── output/ (gitignored)
```

---

## Task 1: Project Scaffold + CLAUDE.md

**Specialist:** Lead
**Depends on:** None
**Produces:** Project skeleton, CLAUDE.md with all rules, pyproject.toml, config.yaml, schema.sql, .gitignore, conftest.py (base fixtures without model imports), all `__init__.py` files. All later tasks import from this foundation.

**Files:**
- Create: `CLAUDE.md`, `pyproject.toml`, `.gitignore`, `.env.example`, `config.yaml`
- Create: `src/scraper/storage/schema.sql`
- Create: all `__init__.py` files, `tests/conftest.py`

- [ ] **Step 1: git init**

```bash
cd "/Users/blackchina23/Work/Frontier Dental"
git init
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.env
output/
*.egg-info/
dist/
.ruff_cache/
.pytest_cache/
.venv/
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "frontier-dental-scraper"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.4,<1.0",
    "langgraph-checkpoint-sqlite>=2.0,<3.0",
    "langchain-anthropic>=0.3,<1.0",
    "langchain-core>=0.3,<1.0",
    "anthropic>=0.42,<1.0",
    "playwright>=1.49,<2.0",
    "pydantic>=2.10,<3.0",
    "pydantic-settings>=2.7,<3.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "click>=8.1",
    "structlog>=24.0",
    "aiosqlite>=0.20",
    "tenacity>=9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "ruff>=0.8",
]

[project.scripts]
scraper = "scraper.main:cli"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100
```

- [ ] **Step 4: Create `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

- [ ] **Step 5: Create `config.yaml`**

```yaml
scraping:
  seed_urls:
    - https://www.safcodental.com/catalog/sutures-surgical-products
    - https://www.safcodental.com/catalog/gloves
  base_url: https://www.safcodental.com
  max_pages: 500
  request_delay_seconds: 1.5
  page_load_timeout_ms: 15000

browser:
  headless: true
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
  viewport_width: 1280
  viewport_height: 720

llm:
  model: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0

retry:
  max_retries: 3
  base_delay_seconds: 2
  backoff_multiplier: 2

output:
  json_path: output/products.json
  database_path: output/products.db
  checkpoint_path: output/checkpoints.db
  log_dir: output/logs
```

- [ ] **Step 6: Create `src/scraper/storage/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    product_name TEXT NOT NULL,
    brand TEXT,
    category_hierarchy TEXT,
    product_url TEXT NOT NULL,
    price REAL,
    variants TEXT,
    unit_pack_size TEXT,
    availability TEXT,
    description TEXT,
    specifications TEXT,
    image_urls TEXT,
    alternative_products TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_brand ON products(brand);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    parent_category TEXT,
    product_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    total_products INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES scrape_runs(id),
    url TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    attempt_count INTEGER DEFAULT 1,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 7: Create directories and `__init__.py` files**

```bash
mkdir -p src/scraper/agents src/scraper/tools src/scraper/storage src/scraper/utils
mkdir -p tests/fixtures output/logs
touch src/scraper/__init__.py src/scraper/agents/__init__.py
touch src/scraper/tools/__init__.py src/scraper/storage/__init__.py
touch src/scraper/utils/__init__.py tests/__init__.py
```

- [ ] **Step 8: Create `CLAUDE.md`** with full assignment spec, critical rules, interface contracts, architecture, commands

- [ ] **Step 9: Create `tests/conftest.py`** (NO model imports — models don't exist yet)

```python
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
```

- [ ] **Step 10: Install dependencies**

```bash
pip install -e ".[dev]" && playwright install chromium
```

- [ ] **Step 11: Commit**

```bash
git add -A && git commit -m "feat: project scaffold with config, schema, fixtures"
```

---

## Task 2: Core Models & State

**Specialist:** Lead
**Depends on:** Task 1 (project structure)
**Produces:** `models.py` (Product, ProductVariant, Category, ScrapingError), `state.py` (ScraperState TypedDict), `sample_product` fixture in conftest. All agents and storage import these.

**Files:**
- Create: `src/scraper/models.py`, `src/scraper/state.py`, `tests/test_models.py`
- Modify: `tests/conftest.py` (add sample_product fixture)

- [ ] **Step 1: Write failing tests for models**

```python
# tests/test_models.py
import pytest
from datetime import datetime, timezone
from scraper.models import Product, ProductVariant, Category, ScrapingError


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
                    product_url="https://example.com/product/test", scraped_at=datetime.now(timezone.utc))
        assert p.brand is None
        assert p.variants == []

    def test_product_json_serializable(self, sample_product):
        d = sample_product.model_dump(mode="json")
        assert isinstance(d["scraped_at"], str)
        assert d["variants"][0]["sku"] == "GL-1001-S"


class TestCategory:
    def test_create_category(self):
        c = Category(name="Gloves", url="https://www.safcodental.com/catalog/gloves")
        assert c.parent_category is None

class TestScrapingError:
    def test_create_error(self):
        e = ScrapingError(url="https://example.com", error_type="timeout", error_message="Timed out")
        assert e.attempt_count == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_models.py -v
```

- [ ] **Step 3: Implement `src/scraper/models.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class ProductVariant(BaseModel):
    variant_name: Optional[str] = None
    sku: str
    price: Optional[float] = None
    availability: Optional[str] = None


class Product(BaseModel):
    product_name: str
    brand: Optional[str] = None
    sku: str
    category_hierarchy: list[str]
    product_url: str
    price: Optional[float] = None
    variants: list[ProductVariant] = Field(default_factory=list)
    unit_pack_size: Optional[str] = None
    availability: Optional[str] = None
    description: Optional[str] = None
    specifications: dict = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    alternative_products: list[str] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_page_type: str = "product_detail"
    validation_errors: list[str] = Field(default_factory=list)


class Category(BaseModel):
    name: str
    url: str
    parent_category: Optional[str] = None
    subcategories: list[str] = Field(default_factory=list)


class ScrapingError(BaseModel):
    url: str
    error_type: str
    error_message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 1
```

- [ ] **Step 4: Implement `src/scraper/state.py`**

```python
from __future__ import annotations
from operator import add
from typing import Annotated, TypedDict


class ScraperState(TypedDict):
    url_queue: Annotated[list[str], add]       # append-only; filter against visited_urls
    visited_urls: Annotated[list[str], add]
    current_url: str
    page_type: str
    page_html: str
    page_metadata: dict
    extracted_products: Annotated[list[dict], add]
    all_products: Annotated[list[dict], add]
    categories: Annotated[list[dict], add]
    discovered_product_urls: Annotated[list[str], add]
    errors: Annotated[list[dict], add]
    retry_counts: dict[str, int]               # {url: attempt_count} — overwrite
    dead_letter_queue: Annotated[list[dict], add]
    seen_skus: Annotated[list[str], add]
    status: str
    iteration_count: int
    max_iterations: int
```

- [ ] **Step 5: Add `sample_product` fixture to conftest.py**

```python
# Add to tests/conftest.py
from scraper.models import Product, ProductVariant
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
        specifications={"material": "nitrile", "powder": "no"},
        image_urls=["https://www.safcodental.com/media/gloves.jpg"],
        alternative_products=["GL-2001"], scraped_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
pytest tests/test_models.py -v
```

- [ ] **Step 7: Commit**

```bash
git add src/scraper/models.py src/scraper/state.py tests/test_models.py tests/conftest.py
git commit -m "feat: core data models and LangGraph state schema"
```

---

## Task 3: Config & Logging

**Specialist:** Lead
**Depends on:** Task 1 (config.yaml structure)
**Produces:** `config.py` (Settings + load_settings), `utils/logging.py` (setup_logging). All nodes use these.

**Files:**
- Create: `src/scraper/config.py`, `src/scraper/utils/logging.py`, `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import pytest
from scraper.config import load_settings

class TestConfig:
    def test_loads_from_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("scraping:\n  seed_urls:\n    - https://example.com\n  request_delay_seconds: 2.0\nbrowser:\n  headless: false\n")
        s = load_settings(str(f))
        assert s.seed_urls == ["https://example.com"]
        assert s.request_delay_seconds == 2.0
        assert s.browser_headless is False

    def test_defaults_when_no_file(self, tmp_path):
        s = load_settings(str(tmp_path / "nope.yaml"))
        assert s.max_pages == 500
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `src/scraper/config.py`**

```python
from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    seed_urls: list[str] = []
    base_url: str = "https://www.safcodental.com"
    max_pages: int = 500
    request_delay_seconds: float = 1.5
    page_load_timeout_ms: int = 15000
    browser_headless: bool = True
    browser_user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    viewport_width: int = 1280
    viewport_height: int = 720
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.0
    max_retries: int = 3
    base_delay_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    json_path: str = "output/products.json"
    database_path: str = "output/products.db"
    checkpoint_path: str = "output/checkpoints.db"
    log_dir: str = "output/logs"
    model_config = {"env_file": ".env", "extra": "ignore"}


def load_settings(config_path: str = "config.yaml") -> Settings:
    config_data = {}
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        for section, mapping in [
            ("scraping", {"seed_urls": "seed_urls", "base_url": "base_url", "max_pages": "max_pages",
                          "request_delay_seconds": "request_delay_seconds", "page_load_timeout_ms": "page_load_timeout_ms"}),
            ("browser", {"headless": "browser_headless", "user_agent": "browser_user_agent",
                         "viewport_width": "viewport_width", "viewport_height": "viewport_height"}),
            ("llm", {"model": "llm_model", "max_tokens": "llm_max_tokens", "temperature": "llm_temperature"}),
            ("retry", {"max_retries": "max_retries", "base_delay_seconds": "base_delay_seconds", "backoff_multiplier": "backoff_multiplier"}),
            ("output", {"json_path": "json_path", "database_path": "database_path", "checkpoint_path": "checkpoint_path", "log_dir": "log_dir"}),
        ]:
            for yaml_key, settings_key in mapping.items():
                val = raw.get(section, {}).get(yaml_key)
                if val is not None:
                    config_data[settings_key] = val
    return Settings(**config_data)
```

- [ ] **Step 4: Implement `src/scraper/utils/logging.py`**

```python
from __future__ import annotations
import structlog
from pathlib import Path

def setup_logging(log_dir: str = "output/logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if level == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(structlog.get_level_from_name(level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/scraper/config.py src/scraper/utils/logging.py tests/test_config.py
git commit -m "feat: config loading and structured logging"
```

---

## Task 4: Browser Tool with Response Interception

**Specialist:** browser-engineer
**Depends on:** Task 1 (project structure), Task 3 (config.py for Settings)
**Produces:** `tools/browser.py` (BrowserManager + PageResult), `tools/rate_limiter.py` (RateLimiter). Used by fetch_page_node, navigator, extractor.

**Files:**
- Create: `src/scraper/tools/browser.py`, `src/scraper/tools/rate_limiter.py`, `tests/test_browser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_browser.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scraper.tools.browser import BrowserManager, PageResult

class TestPageResult:
    def test_success(self):
        r = PageResult(url="https://example.com", html="<html></html>", json_ld={"@type": "Product"},
                       intercepted_data={}, status_code=200, error=None)
        assert r.error is None

    def test_error(self):
        r = PageResult(url="https://example.com", html="", json_ld=None,
                       intercepted_data={}, status_code=403, error="Forbidden")
        assert r.error == "Forbidden"

class TestResponseInterception:
    async def test_handler_captures_ajax(self):
        intercepted = {}
        async def handler(response):
            if "/rest/" in response.url:
                intercepted[response.url] = await response.json()
        mock_resp = AsyncMock()
        mock_resp.url = "https://www.safcodental.com/rest/V1/products"
        mock_resp.json.return_value = {"price": 12.99}
        await handler(mock_resp)
        assert intercepted[mock_resp.url]["price"] == 12.99
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `src/scraper/tools/rate_limiter.py`**

```python
from __future__ import annotations
import asyncio, time

class RateLimiter:
    def __init__(self, delay_seconds: float = 1.5):
        self._delay = delay_seconds
        self._last_request: float = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._delay:
            await asyncio.sleep(self._delay - elapsed)
        self._last_request = time.monotonic()
```

- [ ] **Step 4: Implement `src/scraper/tools/browser.py`**

Full implementation with:
- `page.on("response")` listener intercepting `/rest/`, `/graphql`, `/customer/section/load`
- 15-second max timeout
- JSON-LD extraction via `page.evaluate()`
- Anti-bot: realistic user-agent, 403 detection
- Graceful error handling returning `PageResult` with error field

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/scraper/tools/browser.py src/scraper/tools/rate_limiter.py tests/test_browser.py
git commit -m "feat: Playwright browser with AJAX response interception"
```

---

## Task 5: Claude LLM Client

**Specialist:** agent-engineer
**Depends on:** Task 1 (project structure)
**Produces:** `tools/llm.py` (LLMClient with classify_page, extract_product_data, extract_subcategories). Used by classifier, extractor, navigator.

**Files:**
- Create: `src/scraper/tools/llm.py`, `tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from scraper.tools.llm import LLMClient

class TestLLMClient:
    async def test_classify_catalog_url_no_claude_call(self):
        client = LLMClient(api_key="test", model="claude-sonnet-4-20250514")
        client._client = AsyncMock()
        result = await client.classify_page("<html></html>", "https://www.safcodental.com/catalog/gloves")
        assert result == "category_listing"
        client._client.messages.create.assert_not_called()

    async def test_classify_product_url_no_claude_call(self):
        client = LLMClient(api_key="test", model="claude-sonnet-4-20250514")
        client._client = AsyncMock()
        result = await client.classify_page("<html></html>", "https://www.safcodental.com/product/test")
        assert result == "product_detail"
        client._client.messages.create.assert_not_called()

    async def test_extract_product_data_uses_tool_use(self):
        client = LLMClient(api_key="test", model="claude-sonnet-4-20250514")
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(type="tool_use", input={"product_name": "Gloves", "sku": "GL-001", "price": 12.99})]
        client._client = AsyncMock()
        client._client.messages.create.return_value = mock_resp
        result = await client.extract_product_data("<html>product</html>", "https://example.com/product/test")
        assert result["sku"] == "GL-001"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `src/scraper/tools/llm.py`**

Full implementation with:
- URL heuristic in `classify_page` (the single source of truth for classification)
- `PRODUCT_EXTRACTION_TOOL` and `SUBCATEGORY_EXTRACTION_TOOL` schemas for tool_use
- `cache_control: {"type": "ephemeral"}` on system prompt for prompt caching
- `tenacity` retry for RateLimitError and InternalServerError
- HTML truncation to 100KB before sending

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/tools/llm.py tests/test_llm.py
git commit -m "feat: Claude LLM client with tool_use and prompt caching"
```

---

## Task 6: Storage Layer

**Specialist:** storage-engineer
**Depends on:** Task 2 (Product model for upsert), Task 1 (schema.sql)
**Produces:** `storage/database.py` (init_db, upsert_product, log_error, get_run_stats), `storage/json_export.py` (append_product_jsonl, export_all_json). Used by store_node.

**Files:**
- Create: `src/scraper/storage/database.py`, `src/scraper/storage/json_export.py`
- Create: `tests/test_database.py`, `tests/test_json_export.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_database.py
import pytest, json, aiosqlite
from scraper.storage.database import init_db, upsert_product

@pytest.fixture
async def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    return db_path

class TestDatabase:
    async def test_init_creates_tables(self, test_db):
        async with aiosqlite.connect(test_db) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in await cursor.fetchall()}
        assert {"products", "categories", "scrape_runs", "errors"} <= tables

    async def test_upsert_inserts(self, test_db, sample_product):
        await upsert_product(sample_product, test_db)
        async with aiosqlite.connect(test_db) as db:
            cursor = await db.execute("SELECT sku, price FROM products WHERE sku = ?", (sample_product.sku,))
            row = await cursor.fetchone()
        assert row[0] == "GL-1001" and row[1] == 12.99

    async def test_upsert_updates_on_conflict(self, test_db, sample_product):
        await upsert_product(sample_product, test_db)
        sample_product.price = 14.99
        await upsert_product(sample_product, test_db)
        async with aiosqlite.connect(test_db) as db:
            row = (await (await db.execute("SELECT price FROM products WHERE sku = ?", (sample_product.sku,))).fetchone())
        assert row[0] == 14.99

    async def test_variants_stored_as_json(self, test_db, sample_product):
        await upsert_product(sample_product, test_db)
        async with aiosqlite.connect(test_db) as db:
            row = (await (await db.execute("SELECT variants FROM products WHERE sku = ?", (sample_product.sku,))).fetchone())
        assert len(json.loads(row[0])) == 2
```

```python
# tests/test_json_export.py
import pytest, json
from scraper.storage.json_export import append_product_jsonl, export_all_json

class TestJsonExport:
    def test_append_jsonl(self, tmp_path, sample_product):
        path = str(tmp_path / "out.jsonl")
        append_product_jsonl(sample_product, path)
        append_product_jsonl(sample_product, path)
        assert len(open(path).readlines()) == 2

    def test_export_all(self, tmp_path, sample_product):
        path = str(tmp_path / "out.json")
        export_all_json([sample_product], path)
        assert json.loads(open(path).read())[0]["sku"] == "GL-1001"
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement `src/scraper/storage/database.py` and `json_export.py`**

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/storage/database.py src/scraper/storage/json_export.py tests/test_database.py tests/test_json_export.py
git commit -m "feat: SQLite storage with upsert and JSONL export"
```

---

## Task 7: Navigator & Classifier Nodes

**Specialist:** agent-engineer
**Depends on:** Task 5 (LLMClient for classify_page), Task 3 (config for seed_urls)
**Produces:** `agents/navigator.py` (navigator_node, pick_next_url_node), `agents/classifier.py` (classifier_node). Used by graph.py.

**Files:**
- Create: `src/scraper/agents/navigator.py`, `src/scraper/agents/classifier.py`
- Create: `tests/test_navigator.py`, `tests/test_classifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_classifier.py
import pytest
from scraper.agents.classifier import classifier_node

class TestClassifier:
    async def test_catalog_url(self):
        state = {"current_url": "https://www.safcodental.com/catalog/gloves", "page_html": "", "page_metadata": {}}
        assert (await classifier_node(state))["page_type"] == "category_listing"

    async def test_product_url(self):
        state = {"current_url": "https://www.safcodental.com/product/test", "page_html": "", "page_metadata": {}}
        assert (await classifier_node(state))["page_type"] == "product_detail"
```

```python
# tests/test_navigator.py
import pytest
from scraper.agents.navigator import pick_next_url_node

class TestPickNextUrl:
    async def test_picks_unvisited(self):
        state = {"url_queue": ["https://a.com", "https://b.com"], "visited_urls": ["https://a.com"]}
        result = await pick_next_url_node(state)
        assert result["current_url"] == "https://b.com"

    async def test_done_when_all_visited(self):
        state = {"url_queue": ["https://a.com"], "visited_urls": ["https://a.com"]}
        assert (await pick_next_url_node(state))["status"] == "done"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement classifier (delegates to LLMClient) and navigator (with injectable rate limiter)**

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/agents/navigator.py src/scraper/agents/classifier.py tests/test_navigator.py tests/test_classifier.py
git commit -m "feat: navigator and classifier agent nodes"
```

---

## Task 8: Extractor Node

**Specialist:** browser-engineer
**Depends on:** Task 4 (BrowserManager), Task 5 (LLMClient for extract_product_data)
**Produces:** `agents/extractor.py` (extract_listings_node, extract_product_node). Core extraction logic.

**Files:**
- Create: `src/scraper/agents/extractor.py`, `tests/test_extractor.py`

- [ ] **Step 1: Write failing tests** for JSON-LD extraction and pagination discovery

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** with JSON-LD first, Claude fallback, pagination detection via `?p=N`

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/agents/extractor.py tests/test_extractor.py
git commit -m "feat: extractor agent with JSON-LD + Claude fallback"
```

---

## Task 9: Validator & Recovery Nodes

**Specialist:** storage-engineer
**Depends on:** Task 2 (Product model for validation)
**Produces:** `agents/validator.py` (validator_node), `agents/recovery.py` (recovery_node). Used by graph.py.

**Files:**
- Create: `src/scraper/agents/validator.py`, `src/scraper/agents/recovery.py`
- Create: `tests/test_validator.py`, `tests/test_recovery.py`

- [ ] **Step 1: Write failing tests** for validation, dedup, normalization, recovery backoff, dead-letter

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** validator (Pydantic + price normalization + SKU dedup) and recovery (exponential backoff + dead-letter queue)

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/agents/validator.py src/scraper/agents/recovery.py tests/test_validator.py tests/test_recovery.py
git commit -m "feat: validator with dedup and recovery with backoff"
```

---

## Task 10: Graph Assembly

**Specialist:** agent-engineer
**Depends on:** Task 7 (navigator, classifier), Task 8 (extractor), Task 9 (validator, recovery), Task 4 (browser for fetch_page_node), Task 6 (storage for store_node)
**Produces:** `graph.py` (build_graph function, all routing functions, fetch_page_node, store_node). The core orchestration.

**Files:**
- Create: `src/scraper/graph.py`, `tests/test_graph.py`

- [ ] **Step 1: Write failing test** — graph compiles, routing test with mocks that verifies `ainvoke` runs

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** StateGraph with all nodes, conditional edges, routing functions

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/scraper/graph.py tests/test_graph.py
git commit -m "feat: LangGraph StateGraph with all nodes and routing"
```

---

## Task 11: CLI Entry Point

**Specialist:** Lead
**Depends on:** Task 10 (build_graph), Task 3 (load_settings, setup_logging), Task 6 (init_db)
**Produces:** `main.py` (click CLI with run, status commands). Entry point for the whole system.

**Files:**
- Create: `src/scraper/main.py`

- [ ] **Step 1: Implement CLI** with `run` (full scrape), `status` (show stats)

(Full code in previous plan — carry forward verbatim)

- [ ] **Step 2: Test CLI starts**

```bash
python -m scraper --help
```

- [ ] **Step 3: Commit**

```bash
git add src/scraper/main.py
git commit -m "feat: CLI entry point with run and status commands"
```

---

## Task 12: Integration Testing

**Specialist:** Lead
**Depends on:** Task 11 (CLI), all previous tasks
**Produces:** Verified working scraper, sample output files

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```

- [ ] **Step 2: Run against real site**

```bash
python -m scraper run
```

- [ ] **Step 3: Verify output** — prices are real numbers, stock present, both categories scraped, pagination handled

- [ ] **Step 4: Fix site-specific issues**

- [ ] **Step 5: Commit**

---

## Task 13: Documentation & Output

**Specialist:** Lead
**Depends on:** Task 12 (verified working system)
**Produces:** README.md, sample output dataset

- [ ] **Step 1: Create README.md** with architecture, agent responsibilities, setup, execution, schema, limitations, scaling plan, monitoring

- [ ] **Step 2: Generate sample output**

```bash
cp output/products.json output/sample_products.json
```

- [ ] **Step 3: Final commit**

```bash
git add -A && git commit -m "docs: README, sample output, final polish"
```

---

## Verification Checklist

1. `pytest tests/ -v` — all tests pass
2. `ruff check src/` — no lint errors
3. `python -m scraper run` — full scrape completes
4. `output/products.json` — real prices, not null/Loading
5. `output/products.db` — queryable with correct data
6. Both categories + subcategories scraped
7. Pagination handled (all pages)
8. Product variants captured (S/M/L/XL)
9. Post-scrape quality: missing prices count, category distribution
10. `Ctrl+C` → graceful shutdown, can resume

---

## Execution

Plan complete and saved to `docs/plans/2026-03-24-frontier-dental-scraper.md`.

**Recommended: Agent Team-Driven** — Parallel specialist agents (browser-engineer, agent-engineer, storage-engineer), wave-based execution, two-stage review after each task. Lead handles Wave 0 (foundation) then spawns team for Waves 1-3.

**Alternative: Subagent-Driven** — Serial execution, simpler orchestration, no team overhead. Better if you want to watch each step closely.

Which approach?
