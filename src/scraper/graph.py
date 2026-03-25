from __future__ import annotations
import functools
from urllib.parse import urlparse, urljoin

import structlog
from langgraph.graph import StateGraph

from scraper.models import (
    Product, ScrapingError, ScraperState,
)
from scraper import database

log = structlog.get_logger()


# --- URL Heuristic ---

def _classify_by_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if "/catalog/" in path or "/category/" in path:
        return "listing"
    if "/product/" in path:
        return "product_detail"
    return "unknown"


# --- Node Functions ---
# Each accepts (state, **injected_deps) and returns a partial state dict.
# Dependencies are bound via functools.partial in build_graph().

async def fetch_node(state: dict, *, browser) -> dict:
    url = state["current_url"]
    log.info("fetch_node", url=url)
    result = await browser.fetch_page(url)
    return {
        "page_result": {
            "url": result.url, "html": result.html,
            "json_ld": result.json_ld, "intercepted_data": result.intercepted_data,
            "status_code": result.status_code,
        },
        "error": result.error,
        "visited_urls": [url],
        "stats": {**state["stats"], "pages_fetched": state["stats"]["pages_fetched"] + 1},
    }


async def classify_and_extract_node(state: dict, *, llm) -> dict:
    url = state["current_url"]
    page = state["page_result"]
    html = page["html"]
    json_ld = page.get("json_ld")

    # Step 1: Classify — URL heuristic first, LLM fallback
    page_type = _classify_by_url(url)
    if page_type == "unknown":
        page_type = await llm.classify_page(html, url)

    log.info("classify_and_extract_node", url=url, page_type=page_type)

    # Step 2: Extract
    try:
        if page_type == "product_detail":
            # JSON-LD first, Claude fallback
            product_ld = None
            if json_ld:
                for block in json_ld:
                    if isinstance(block, dict) and block.get("@type") == "Product":
                        product_ld = block
                        break
            if product_ld:
                product_data = {
                    "product_name": product_ld.get("name", ""),
                    "sku": product_ld.get("sku", ""),
                    "price": product_ld.get("offers", {}).get("price"),
                    "description": product_ld.get("description"),
                    "image_urls": [product_ld["image"]] if product_ld.get("image") else [],
                    "product_url": url,
                    "category_hierarchy": [],
                }
                return {"page_type": page_type, "extracted_data": {"product": product_data}, "error": None}
            else:
                product_data = await llm.extract_product_data(html, url)
                if not product_data or not product_data.get("product_name"):
                    log.warning("empty_llm_response", url=url, page_type="product_detail")
                    return {"page_type": page_type, "extracted_data": None, "error": "LLM returned empty product data"}
                product_data["product_url"] = url
                return {"page_type": page_type, "extracted_data": {"product": product_data}, "error": None}

        elif page_type == "listing":
            subcategories = await llm.extract_subcategories(html, url)
            if not subcategories:
                log.warning("empty_llm_response", url=url, page_type="listing")
                return {"page_type": page_type, "extracted_data": None, "error": "LLM returned no subcategories"}
            return {"page_type": page_type, "extracted_data": {"urls": subcategories}, "error": None}

        else:
            return {"page_type": page_type, "extracted_data": None, "error": None}

    except Exception as e:
        log.error("extraction_failed", url=url, error=str(e))
        return {"page_type": page_type, "extracted_data": None, "error": str(e)}


async def validate_and_store_node(state: dict, *, db_path: str, run_id: int, base_url: str) -> dict:
    stats = dict(state["stats"])
    new_urls = []

    if state.get("page_type") == "product_detail" and state.get("extracted_data"):
        product_data = state["extracted_data"].get("product", {})
        if product_data:
            try:
                product = Product(**product_data)
                await database.upsert_product(product, db_path)
                stats["products_saved"] += 1
                log.info("product_stored", sku=product.sku)
            except Exception as e:
                log.warning("validation_failed", error=str(e))
                stats["errors"] += 1

    elif state.get("page_type") == "listing" and state.get("extracted_data"):
        urls_data = state["extracted_data"].get("urls", [])
        visited = set(state.get("visited_urls", []))
        for item in urls_data:
            full_url = urljoin(base_url, item["url"])
            if full_url not in visited:
                new_urls.append(full_url)

    # Advance URL queue: pop next URL
    queue = list(state.get("urls_to_visit", [])) + new_urls
    if queue:
        next_url = queue.pop(0)
        return {
            "current_url": next_url,
            "urls_to_visit": queue,
            "stats": stats,
            "error": None,
            "retry_count": 0,
            "extracted_data": None,
            "page_result": None,
        }
    else:
        return {
            "current_url": "",
            "urls_to_visit": [],
            "stats": stats,
            "error": None,
            "retry_count": 0,
            "extracted_data": None,
            "page_result": None,
        }


async def recover_node(state: dict, *, max_retries: int, db_path: str, run_id: int) -> dict:
    url = state["current_url"]
    retry_count = state.get("retry_count", 0)
    stats = dict(state["stats"])

    if retry_count < max_retries:
        # Retry same URL — do NOT log an error yet (URL may still succeed)
        log.warning("recover_node_retry", url=url, retry_count=retry_count, max_retries=max_retries)
        return {"retry_count": retry_count + 1, "error": state.get("error"), "current_url": url}
    else:
        # Final skip — log error and advance to next URL
        error = ScrapingError(
            url=url, error_type="scrape_error",
            error_message=state.get("error", "unknown"), attempt_count=retry_count + 1,
        )
        await database.log_error(error, run_id, db_path)
        stats["errors"] += 1
        log.warning("recover_node_skip", url=url, retry_count=retry_count, max_retries=max_retries)
        queue = list(state.get("urls_to_visit", []))
        if queue:
            next_url = queue.pop(0)
            return {
                "current_url": next_url, "urls_to_visit": queue,
                "retry_count": 0, "error": None, "stats": stats,
            }
        else:
            return {
                "current_url": "", "urls_to_visit": [],
                "retry_count": 0, "error": None, "stats": stats,
            }


# --- Routing Functions ---

def route_after_fetch(state: dict) -> str:
    return "recover" if state.get("error") else "classify_and_extract"


def route_after_extract(state: dict) -> str:
    return "recover" if state.get("error") else "validate_and_store"


def route_after_validate(state: dict, *, max_pages: int = 0) -> str:
    if max_pages and state.get("stats", {}).get("pages_fetched", 0) >= max_pages:
        return "__end__"
    if not state.get("urls_to_visit") and not state.get("current_url"):
        return "__end__"
    return "fetch"


def route_after_recover(state: dict) -> str:
    # No current_url means queue exhausted after skip → end
    if not state.get("current_url"):
        return "__end__"
    # Both retrying (retry_count > 0) and skipping (retry_count = 0, next URL set) → fetch
    return "fetch"


# --- Graph Builder ---

def build_graph(browser, llm, config: dict):
    graph = StateGraph(ScraperState)

    # Bind dependencies to node functions via partial
    graph.add_node("fetch", functools.partial(fetch_node, browser=browser))
    graph.add_node("classify_and_extract", functools.partial(classify_and_extract_node, llm=llm))
    graph.add_node("validate_and_store", functools.partial(
        validate_and_store_node,
        db_path=config["db_path"], run_id=config["run_id"], base_url=config["base_url"],
    ))
    graph.add_node("recover", functools.partial(
        recover_node,
        max_retries=config.get("max_retries", 3),
        db_path=config["db_path"], run_id=config["run_id"],
    ))

    max_pages = config.get("max_pages", 0)
    def _route_validate(state: dict) -> str:
        return route_after_validate(state, max_pages=max_pages)

    graph.set_entry_point("fetch")
    graph.add_conditional_edges("fetch", route_after_fetch)
    graph.add_conditional_edges("classify_and_extract", route_after_extract)
    graph.add_conditional_edges("validate_and_store", _route_validate)
    graph.add_conditional_edges("recover", route_after_recover)

    return graph.compile()
