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
