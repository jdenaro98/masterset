#!/usr/bin/env python3
"""
TCGPlayer VSTAR Universe (S12a) Cart Optimizer
==============================================
Scrapes TCGPlayer for every seller listing across all target cards in
the VSTAR Universe (S12a) set, then solves a set-cover optimisation to
minimise the number of distinct sellers you need to buy from, then
minimises total spend within that constraint.

QUICK START
-----------
  pip install -r requirements.txt
  playwright install chromium
  python vstar_optimizer.py

The script runs in three sequential phases and saves progress after each
one, so it can be safely interrupted and resumed at any time.

Phase 1  Discover all product IDs/URLs for the set from the TCGPlayer
         search pages.  Output: products.json
Phase 2  Visit every product page and scrape the seller listing table.
         Output: listings.json  (appended incrementally)
Phase 3  Run the set-cover optimisation and write results.
         Output: optimized_cart.csv  +  summary.txt

CONFIGURATION  (edit the block below)
--------------------------------------
  EXCLUDED_CARD_NUMBERS  Cards to skip, identified by their printed
                         number on the card (as a string).
  ACCEPTED_CONDITIONS    Only listings whose condition contains one of
                         these strings (case-insensitive) are kept.
  HEADLESS               Set True to run the browser invisibly, False
                         to watch it work (default False – less likely
                         to be blocked).
  MIN_DELAY / MAX_DELAY  Seconds to pause between page loads.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Standard library
# ──────────────────────────────────────────────────────────────────────────────
import asyncio
import json
import csv
import os
import re
import random
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Third-party  (pip install playwright)
# ──────────────────────────────────────────────────────────────────────────────
from playwright.async_api import async_playwright, Page, BrowserContext, Response

# ==============================================================================
# CONFIGURATION  ← edit here
# ==============================================================================

# Card numbers to skip (as strings matching what is printed on the card).
# #263 is listed by the user but does not appear in the official set numbering
# (the set tops out at #262).  It is included here anyway so if TCGPlayer
# carries an alternate-art listing under that number it will also be skipped.
EXCLUDED_CARD_NUMBERS: set[str] = {"205", "212", "221", "259", "261", "262", "263"}

# Only purchase Near Mint or Lightly Played cards.  The check is a
# case-insensitive substring match, so "Near Mint Japanese" is accepted.
ACCEPTED_CONDITIONS: tuple[str, ...] = ("near mint", "lightly played")

# Run the browser visibly so you can see it work – recommended for first run.
HEADLESS: bool = False

# Seconds to wait between page loads.  Higher values are safer but slower.
MIN_DELAY: float = 2.5
MAX_DELAY: float = 5.0

# How many extra listings to reveal by clicking "Show More" on a product page.
# Each click shows ~25 more rows.  10 clicks = up to ~250 listings per card.
MAX_SHOW_MORE_CLICKS: int = 10

# ==============================================================================
# FILE PATHS
# ==============================================================================
PRODUCTS_FILE  = Path("products.json")
LISTINGS_FILE  = Path("listings.json")
OUTPUT_CSV     = Path("optimized_cart.csv")
SUMMARY_FILE   = Path("summary.txt")

# ==============================================================================
# TCGPlayer URL TEMPLATES
# ==============================================================================
SET_SEARCH_URL = (
    "https://www.tcgplayer.com/search/pokemon-japan/s12a-vstar-universe"
    "?productLineName=pokemon-japan&setName=s12a-vstar-universe"
    "&view=grid&page={page}"
)
PRODUCT_BASE_URL = "https://www.tcgplayer.com/product/{product_id}"


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class Product:
    """One distinct TCGPlayer product listing (a single card + variant)."""
    product_id: str
    name: str          # Full display name including variant suffix
    card_number: str   # Numeric portion only, e.g. "107"
    variant: str       # "Normal", "Holofoil", etc.
    url: str


@dataclass
class Listing:
    """One seller's offer for a specific product."""
    product_id: str
    seller: str
    price: float       # Card price in USD
    shipping: float    # Shipping cost in USD (0 = free)
    condition: str


@dataclass
class Assignment:
    """Final cart row: one card assigned to one seller."""
    card_number: str
    card_name: str
    variant: str
    product_id: str
    seller: str
    price: float
    shipping: float
    condition: str
    tcgplayer_url: str


# ==============================================================================
# UTILITY HELPERS
# ==============================================================================

def parse_price(text: str) -> float:
    """Extract a USD float from strings like '$1.23', 'FREE', '+$0.99 shipping'."""
    if not text:
        return 0.0
    if "free" in text.lower():
        return 0.0
    m = re.search(r"(\d[\d,]*\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else 0.0


def random_delay() -> float:
    return random.uniform(MIN_DELAY, MAX_DELAY)


def log(msg: str):
    print(msg, flush=True)


# ==============================================================================
# PHASE 1 – DISCOVER ALL PRODUCTS IN THE SET
# ==============================================================================

async def discover_products(ctx: BrowserContext) -> list[Product]:
    """
    Paginate through the TCGPlayer set search and collect every product
    URL + metadata.  Excluded card numbers are filtered out here.

    Result is cached to PRODUCTS_FILE so subsequent runs skip this phase.
    """
    if PRODUCTS_FILE.exists():
        log(f"[Phase 1] Loading cached product list from {PRODUCTS_FILE}")
        with PRODUCTS_FILE.open() as fh:
            return [Product(**p) for p in json.load(fh)]

    log("[Phase 1] Discovering products from TCGPlayer set search …")
    products: list[Product] = []
    page = await ctx.new_page()
    page_num = 1

    while True:
        url = SET_SEARCH_URL.format(page=page_num)
        log(f"  → page {page_num}: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=60_000)
        except Exception as exc:
            log(f"  WARNING: could not load page {page_num}: {exc}")
            break

        await asyncio.sleep(random_delay())

        # ── Wait for product grid ────────────────────────────────────────────
        try:
            await page.wait_for_selector(
                ".search-result, .product-card, [data-testid='product-card']",
                timeout=15_000,
            )
        except Exception:
            log(f"  No product grid found on page {page_num} – stopping.")
            break

        # ── Extract product cards ────────────────────────────────────────────
        # TCGPlayer renders product cards as <a> links inside the grid.
        # We match all links whose href contains /product/.
        card_links = await page.query_selector_all("a[href*='/product/']")
        seen_ids: set[str] = {p.product_id for p in products}
        new_on_page = 0

        for link_el in card_links:
            try:
                href = await link_el.get_attribute("href") or ""
                if not href:
                    continue

                m_id = re.search(r"/product/(\d+)/", href)
                if not m_id:
                    continue
                product_id = m_id.group(1)

                if product_id in seen_ids:
                    continue

                # Full name comes from the link text or an aria-label
                name_raw = (await link_el.text_content() or "").strip()
                # aria-label is sometimes richer
                aria = await link_el.get_attribute("aria-label") or ""
                name = aria.strip() if aria.strip() else name_raw

                # Strip excess whitespace / newlines
                name = re.sub(r"\s+", " ", name).strip()
                if not name:
                    continue

                # ── Card number ──────────────────────────────────────────────
                # The URL slug often contains the card number, e.g.:
                #   /product/571645/pokemon-japan-s12a-vstar-universe-rayquaza-v
                # Number is also embedded in the name as "107/172" or "#107"
                number_match = re.search(r"\b(\d{1,3})/172\b", name) or \
                               re.search(r"#(\d{1,3})\b", name) or \
                               re.search(r"\b(\d{1,3})\b", href.split("/")[-1])
                card_number = number_match.group(1) if number_match else "?"

                # Skip excluded cards
                if card_number in EXCLUDED_CARD_NUMBERS:
                    continue

                # ── Variant ──────────────────────────────────────────────────
                name_lower = name.lower()
                if "reverse holofoil" in name_lower:
                    variant = "Reverse Holofoil"
                elif "holofoil" in name_lower:
                    variant = "Holofoil"
                else:
                    variant = "Normal"

                full_url = (
                    f"https://www.tcgplayer.com{href}"
                    if href.startswith("/") else href
                )

                products.append(Product(
                    product_id=product_id,
                    name=name,
                    card_number=card_number,
                    variant=variant,
                    url=full_url,
                ))
                seen_ids.add(product_id)
                new_on_page += 1

            except Exception as exc:
                log(f"  WARNING: error parsing product card: {exc}")

        log(f"  Found {new_on_page} new products on page {page_num} "
            f"(running total: {len(products)})")

        if new_on_page == 0:
            log("  No new products found – end of set.")
            break

        # ── Next page ────────────────────────────────────────────────────────
        # Try a few selector patterns for the "Next" pagination button.
        next_btn = (
            await page.query_selector(".tcg-pagination__right:not([disabled])") or
            await page.query_selector("button[aria-label='Next page']:not([disabled])") or
            await page.query_selector("a[aria-label='Next']:not([disabled])")
        )
        if not next_btn:
            log("  No enabled 'Next' button found – end of pages.")
            break

        page_num += 1

    await page.close()

    if not products:
        log("ERROR: No products were discovered.  TCGPlayer may have changed "
            "its layout or you may be rate-limited.  Try again later.")
        sys.exit(1)

    with PRODUCTS_FILE.open("w") as fh:
        json.dump([asdict(p) for p in products], fh, indent=2)
    log(f"[Phase 1] Done – {len(products)} products saved to {PRODUCTS_FILE}")
    return products


# ==============================================================================
# PHASE 2 – SCRAPE SELLER LISTINGS FOR EACH PRODUCT
# ==============================================================================

async def _wait_for_listings(page: Page, timeout_ms: int = 15_000) -> bool:
    """Return True if listing rows appear within timeout_ms milliseconds."""
    selectors = [
        ".listing-item",
        "[data-testid='listing-row']",
        ".seller-listing__row",
        "table.listing-table tr",
    ]
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout_ms // len(selectors))
            return True
        except Exception:
            pass
    return False


async def _click_show_more(page: Page):
    """Click 'Show More' buttons to expose additional listings."""
    for _ in range(MAX_SHOW_MORE_CLICKS):
        btn = (
            await page.query_selector("button:has-text('Show More')") or
            await page.query_selector("[data-testid='show-more-button']")
        )
        if not btn:
            break
        try:
            await btn.scroll_into_view_if_needed()
            await btn.click()
            await asyncio.sleep(1.2)
        except Exception:
            break


def _condition_ok(text: str) -> bool:
    tl = text.lower()
    return any(ac in tl for ac in ACCEPTED_CONDITIONS)


async def _parse_dom_listings(page: Page, product_id: str) -> list[Listing]:
    """
    DOM-based fallback scraper.  Tries multiple selector strategies to
    find the seller, condition, price and shipping on a product page.
    """
    listings: list[Listing] = []
    rows = (
        await page.query_selector_all(".listing-item") or
        await page.query_selector_all("[data-testid='listing-row']") or
        await page.query_selector_all(".seller-listing__row")
    )

    for row in rows:
        try:
            # ── Seller ───────────────────────────────────────────────────────
            seller_el = (
                await row.query_selector(".seller-info__name") or
                await row.query_selector("[data-testid='seller-name']") or
                await row.query_selector(".seller-name")
            )
            seller = (await seller_el.text_content() if seller_el else "").strip()
            if not seller:
                continue

            # ── Condition ────────────────────────────────────────────────────
            cond_el = (
                await row.query_selector(".listing-item__condition") or
                await row.query_selector("[data-testid='listing-condition']") or
                await row.query_selector(".condition-label")
            )
            condition = (await cond_el.text_content() if cond_el else "").strip()
            if not _condition_ok(condition):
                continue

            # ── Price ────────────────────────────────────────────────────────
            price_el = (
                await row.query_selector(".listing-item__listing-data__info__price") or
                await row.query_selector("[data-testid='listing-price']") or
                await row.query_selector(".price")
            )
            price_text = (await price_el.text_content() if price_el else "").strip()
            price = parse_price(price_text)
            if price <= 0:
                continue

            # ── Shipping ─────────────────────────────────────────────────────
            ship_el = (
                await row.query_selector(".shipping-price") or
                await row.query_selector("[data-testid='shipping-price']") or
                await row.query_selector(".listing-item__shipping")
            )
            ship_text = (await ship_el.text_content() if ship_el else "").strip()
            shipping = parse_price(ship_text)

            listings.append(Listing(
                product_id=product_id,
                seller=seller,
                price=price,
                shipping=shipping,
                condition=condition,
            ))
        except Exception:
            pass

    return listings


async def _parse_network_listings(
    captured: list[dict], product_id: str
) -> list[Listing]:
    """
    Parse TCGPlayer API JSON responses captured via network interception.
    Handles the most common response shapes seen in the TCGPlayer frontend.
    """
    listings: list[Listing] = []

    for entry in captured:
        data = entry.get("data", {})

        # Shape 1: {"results": [...]}
        results = data.get("results") or data.get("listings") or []
        if not results and isinstance(data, list):
            results = data

        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                seller = (
                    item.get("sellerName") or
                    item.get("seller", {}).get("name", "") or
                    item.get("storeName", "")
                )
                if not seller:
                    continue

                condition = (
                    item.get("conditionName") or
                    item.get("condition", {}).get("name", "") or
                    item.get("printing", "")
                )
                if not _condition_ok(condition):
                    continue

                price = float(
                    item.get("price") or
                    item.get("lowestPrice") or
                    item.get("buyItNowPrice") or 0
                )
                if price <= 0:
                    continue

                shipping = float(
                    item.get("shippingPrice") or
                    item.get("shipping") or
                    item.get("shippingCost") or 0
                )

                listings.append(Listing(
                    product_id=product_id,
                    seller=seller,
                    price=price,
                    shipping=shipping,
                    condition=condition,
                ))
            except Exception:
                pass

    return listings


async def scrape_product_listings(page: Page, product: Product) -> list[Listing]:
    """
    Navigate to a TCGPlayer product page and return all qualifying
    seller listings.  Uses network interception as the primary method
    and DOM scraping as a fallback.
    """
    captured: list[dict] = []

    # ── Network interception ─────────────────────────────────────────────────
    async def on_response(resp: Response):
        url = resp.url
        if any(kw in url for kw in
               ("sellerlisting", "listing", "v1/product", "pricing", "marketplace", "storefront")):
            try:
                if resp.status == 200:
                    body = await resp.body()
                    data = json.loads(body)
                    captured.append({"url": url, "data": data})
            except Exception:
                pass

    page.on("response", on_response)

    try:
        await page.goto(product.url, wait_until="networkidle", timeout=60_000)
        await asyncio.sleep(random_delay())
    except Exception as exc:
        log(f"    WARNING: failed to load {product.url}: {exc}")
        page.remove_listener("response", on_response)
        return []
    finally:
        page.remove_listener("response", on_response)

    # ── Expand hidden listings ───────────────────────────────────────────────
    await _click_show_more(page)

    # ── Try network-captured data first ─────────────────────────────────────
    net_listings = await _parse_network_listings(captured, product.product_id)
    if net_listings:
        return net_listings

    # ── Fallback: DOM scraping ───────────────────────────────────────────────
    if not await _wait_for_listings(page, timeout_ms=8_000):
        log(f"    No listing rows found for {product.name} – skipping.")
        return []

    dom_listings = await _parse_dom_listings(page, product.product_id)
    return dom_listings


def _load_existing_listings() -> dict[str, list[Listing]]:
    if not LISTINGS_FILE.exists():
        return {}
    with LISTINGS_FILE.open() as fh:
        raw = json.load(fh)
    return {
        pid: [Listing(**l) for l in llist]
        for pid, llist in raw.items()
    }


def _save_listings(all_listings: dict[str, list[Listing]]):
    with LISTINGS_FILE.open("w") as fh:
        json.dump(
            {pid: [asdict(l) for l in llist] for pid, llist in all_listings.items()},
            fh, indent=2,
        )


async def scrape_all_listings(
    ctx: BrowserContext, products: list[Product]
) -> dict[str, list[Listing]]:
    """
    Iterate over every product and scrape its seller listings.
    Progress is saved incrementally every 10 cards so the script can
    be safely interrupted and resumed.
    """
    all_listings = _load_existing_listings()

    todo = [p for p in products if p.product_id not in all_listings]
    if not todo:
        log("[Phase 2] All listings already scraped – loading from cache.")
        return all_listings

    log(f"[Phase 2] Scraping listings for {len(todo)} products "
        f"({len(all_listings)} already cached) …")

    page = await ctx.new_page()

    for idx, product in enumerate(todo):
        pct = f"{idx + 1}/{len(todo)}"
        log(f"[Phase 2] [{pct}] #{product.card_number} {product.name} ({product.variant})")

        listings = await scrape_product_listings(page, product)
        all_listings[product.product_id] = listings

        log(f"    → {len(listings)} qualifying listings found")

        # Save progress every 10 cards
        if (idx + 1) % 10 == 0 or idx == len(todo) - 1:
            _save_listings(all_listings)
            log(f"    [saved progress – {idx + 1}/{len(todo)} done]")

        await asyncio.sleep(random_delay())

    await page.close()
    _save_listings(all_listings)
    log(f"[Phase 2] Done – listings for {len(all_listings)} products saved to {LISTINGS_FILE}")
    return all_listings


# ==============================================================================
# PHASE 3 – OPTIMISATION (SET COVER + LOCAL SEARCH)
# ==============================================================================

def _cheapest_per_seller(
    all_listings: dict[str, list[Listing]],
    products: list[Product],
) -> tuple[dict[str, dict[str, Listing]], list[Product]]:
    """
    Build:
      seller_inv[seller][product_id] = cheapest Listing for that seller/card

    Also returns a list of products with zero listings (uncoverable).
    """
    seller_inv: dict[str, dict[str, Listing]] = {}
    uncoverable: list[Product] = []

    for product in products:
        raw = all_listings.get(product.product_id, [])
        if not raw:
            uncoverable.append(product)
            continue
        for listing in raw:
            s = listing.seller
            pid = listing.product_id
            if s not in seller_inv:
                seller_inv[s] = {}
            prev = seller_inv[s].get(pid)
            if prev is None or listing.price < prev.price:
                seller_inv[s][pid] = listing

    return seller_inv, uncoverable


def _greedy_set_cover(
    needed: set[str],
    seller_inv: dict[str, dict[str, Listing]],
) -> set[str]:
    """
    Greedy set-cover: repeatedly select the seller that covers the most
    still-uncovered cards.  Tie-break on lowest total cost for those cards.
    Returns the chosen set of seller names.
    """
    chosen: set[str] = set()
    covered: set[str] = set()

    while covered < needed:
        best_seller: Optional[str] = None
        best_gain = 0
        best_cost = float("inf")

        for seller, inv in seller_inv.items():
            if seller in chosen:
                continue
            new_cards = set(inv.keys()) & (needed - covered)
            gain = len(new_cards)
            if gain == 0:
                continue
            cost = sum(inv[pid].price for pid in new_cards)
            if gain > best_gain or (gain == best_gain and cost < best_cost):
                best_seller, best_gain, best_cost = seller, gain, cost

        if best_seller is None:
            log("  WARNING: Cannot cover all cards – some products may have no listings.")
            break

        chosen.add(best_seller)
        covered |= set(seller_inv[best_seller].keys()) & needed
        log(f"  + Added '{best_seller}' → covers {best_gain} new cards "
            f"(covered {len(covered)}/{len(needed)})")

    return chosen


def _local_search_remove_redundant(
    chosen: set[str],
    needed: set[str],
    seller_inv: dict[str, dict[str, Listing]],
    price_tolerance: float = 0.15,
) -> set[str]:
    """
    Post-processing pass: try to eliminate sellers that either:
      (a) Are now fully redundant (every card they hold is also held by
          another chosen seller), or
      (b) Only uniquely cover ≤ 2 cards that another single non-chosen
          seller could cover at a cost ≤ original × (1 + price_tolerance).

    Repeat until no improvement is found.
    """
    improved = True
    while improved:
        improved = False
        for seller in sorted(chosen):          # sorted for determinism
            others = chosen - {seller}
            other_coverage = set().union(*(set(seller_inv[s].keys()) for s in others))
            unique = (set(seller_inv[seller].keys()) & needed) - other_coverage

            # Case (a): fully redundant
            if not unique:
                chosen = others
                log(f"  - Removed redundant seller '{seller}'")
                improved = True
                break

            # Case (b): sole coverage of ≤ 2 cards → try to swap
            if len(unique) <= 2:
                old_cost = sum(seller_inv[seller][pid].price for pid in unique)
                for alt, alt_inv in seller_inv.items():
                    if alt in chosen:
                        continue
                    if unique.issubset(set(alt_inv.keys())):
                        new_cost = sum(alt_inv[pid].price for pid in unique)
                        if new_cost <= old_cost * (1 + price_tolerance):
                            chosen = (chosen - {seller}) | {alt}
                            log(f"  ~ Swapped '{seller}' → '{alt}' "
                                f"(saves a seller; cost Δ ${new_cost - old_cost:+.2f})")
                            improved = True
                            break
            if improved:
                break

    return chosen


def optimize_cart(
    products: list[Product],
    all_listings: dict[str, list[Listing]],
) -> list[Assignment]:
    """
    Full optimisation pipeline:
      1. Build per-seller cheapest-price inventory.
      2. Greedy set cover to select minimum sellers.
      3. Local search to remove any now-redundant sellers.
      4. Assign each card to whichever chosen seller offers it cheapest.
    """
    log("[Phase 3] Building seller inventory …")
    seller_inv, uncoverable = _cheapest_per_seller(all_listings, products)

    if uncoverable:
        log(f"  WARNING: {len(uncoverable)} cards have no listings:")
        for p in uncoverable:
            log(f"    #{p.card_number} {p.name} ({p.variant})")

    needed = {p.product_id for p in products} - {p.product_id for p in uncoverable}
    log(f"  Covering {len(needed)} cards across {len(seller_inv)} sellers …")

    log("[Phase 3] Running greedy set cover …")
    chosen = _greedy_set_cover(needed, seller_inv)
    log(f"  Greedy solution: {len(chosen)} sellers")

    log("[Phase 3] Running local-search refinement …")
    chosen = _local_search_remove_redundant(chosen, needed, seller_inv)
    log(f"  Refined solution: {len(chosen)} sellers")

    # ── Assignment ───────────────────────────────────────────────────────────
    log("[Phase 3] Assigning cards to cheapest seller in chosen set …")
    product_map = {p.product_id: p for p in products}
    assignments: list[Assignment] = []

    for pid in needed:
        product = product_map[pid]
        best: Optional[Listing] = None
        for seller in chosen:
            listing = seller_inv[seller].get(pid)
            if listing is None:
                continue
            if best is None or listing.price < best.price:
                best = listing

        if best is None:
            # No chosen seller covers this card – use globally cheapest
            all_for_card = all_listings.get(pid, [])
            if all_for_card:
                best = min(all_for_card, key=lambda l: l.price)
                log(f"  FALLBACK #{product.card_number} → cheapest global: '{best.seller}'")

        if best:
            assignments.append(Assignment(
                card_number=product.card_number,
                card_name=product.name,
                variant=product.variant,
                product_id=pid,
                seller=best.seller,
                price=best.price,
                shipping=best.shipping,
                condition=best.condition,
                tcgplayer_url=product.url,
            ))

    # ── Uncoverable cards (placeholder rows) ─────────────────────────────────
    for p in uncoverable:
        assignments.append(Assignment(
            card_number=p.card_number,
            card_name=p.name,
            variant=p.variant,
            product_id=p.product_id,
            seller="❌ NO LISTINGS FOUND",
            price=0.0,
            shipping=0.0,
            condition="N/A",
            tcgplayer_url=p.url,
        ))

    # ── Sort by numeric card number, then variant ─────────────────────────────
    def sort_key(a: Assignment):
        try:
            n = int(a.card_number)
        except ValueError:
            n = 9999
        return (n, a.variant)

    assignments.sort(key=sort_key)
    return assignments


# ==============================================================================
# OUTPUT
# ==============================================================================

def write_output(assignments: list[Assignment]):
    """Write optimized_cart.csv and summary.txt, and print the summary."""

    # ── CSV ───────────────────────────────────────────────────────────────────
    fieldnames = [
        "card_number", "card_name", "variant",
        "seller", "price_usd", "shipping_usd", "condition", "tcgplayer_url",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for a in assignments:
            writer.writerow({
                "card_number":   a.card_number,
                "card_name":     a.card_name,
                "variant":       a.variant,
                "seller":        a.seller,
                "price_usd":     f"{a.price:.2f}" if a.price else "N/A",
                "shipping_usd":  f"{a.shipping:.2f}" if a.shipping else "FREE",
                "condition":     a.condition,
                "tcgplayer_url": a.tcgplayer_url,
            })

    # ── Statistics ────────────────────────────────────────────────────────────
    valid = [a for a in assignments if a.seller != "❌ NO LISTINGS FOUND"]
    unavailable = [a for a in assignments if a.seller == "❌ NO LISTINGS FOUND"]

    # Per-seller: collect cards and record shipping once (flat rate per order)
    seller_stats: dict[str, dict] = {}
    for a in valid:
        if a.seller not in seller_stats:
            seller_stats[a.seller] = {"cards": [], "shipping": a.shipping}
        seller_stats[a.seller]["cards"].append(a)

    total_card_cost = sum(a.price for a in valid)
    total_shipping  = sum(v["shipping"] for v in seller_stats.values())
    grand_total     = total_card_cost + total_shipping

    lines = [
        "=" * 70,
        "  VSTAR UNIVERSE (S12a)  –  OPTIMISED CART SUMMARY",
        "=" * 70,
        f"  Cards to purchase   : {len(valid)}",
        f"  Unique sellers      : {len(seller_stats)}",
        f"  Total card cost     : ${total_card_cost:,.2f}",
        f"  Total shipping      : ${total_shipping:,.2f}",
        f"  Estimated grand total: ${grand_total:,.2f}",
        "",
        "  PER-SELLER BREAKDOWN  (sorted by cards held descending)",
        "  " + "-" * 66,
        f"  {'Seller':<35} {'Cards':>6}  {'Card $':>9}  {'Ship':>6}  {'Subtotal':>9}",
        "  " + "-" * 66,
    ]

    for seller, info in sorted(seller_stats.items(), key=lambda x: -len(x[1]["cards"])):
        card_sum = sum(a.price for a in info["cards"])
        ship     = info["shipping"]
        lines.append(
            f"  {seller:<35} {len(info['cards']):>6}  "
            f"${card_sum:>8.2f}  ${ship:>5.2f}  ${card_sum + ship:>8.2f}"
        )

    if unavailable:
        lines += [
            "",
            f"  ⚠  {len(unavailable)} card(s) had no qualifying listings on TCGPlayer:",
            "  " + "-" * 66,
        ]
        for a in unavailable:
            lines.append(f"    #{a.card_number}  {a.card_name}  ({a.variant})")
        lines.append(
            "  These may need to be purchased elsewhere or sourced at a later date."
        )

    lines += [
        "",
        f"  Detailed cart: {OUTPUT_CSV}",
        "=" * 70,
    ]

    summary_text = "\n".join(lines)
    print("\n" + summary_text)

    with SUMMARY_FILE.open("w", encoding="utf-8") as fh:
        fh.write(summary_text + "\n")

    log(f"\nDone!  Full cart written to {OUTPUT_CSV}")
    log(f"Summary written to {SUMMARY_FILE}")


# ==============================================================================
# BROWSER SET-UP
# ==============================================================================

async def build_context(pw):
    """Launch Chromium with anti-detection settings and return a context."""
    browser = await pw.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    # Hide the webdriver flag that sites use to detect automation
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


# ==============================================================================
# ENTRY POINT
# ==============================================================================

async def main():
    log("=" * 70)
    log("  TCGPlayer VSTAR Universe (S12a) Cart Optimizer")
    log("=" * 70)
    log(f"  Excluded card numbers : {sorted(EXCLUDED_CARD_NUMBERS, key=int)}")
    log(f"  Accepted conditions   : {ACCEPTED_CONDITIONS}")
    log(f"  Headless browser      : {HEADLESS}")
    log(f"  Delay range           : {MIN_DELAY}–{MAX_DELAY}s")
    log("")

    async with async_playwright() as pw:
        browser, ctx = await build_context(pw)
        try:
            # Phase 1 – discover products
            products = await discover_products(ctx)
            log(f"\nTotal products to scrape: {len(products)}\n")

            # Phase 2 – scrape listings
            all_listings = await scrape_all_listings(ctx, products)
        finally:
            await browser.close()

    # Phase 3 – optimise + output (no browser needed)
    assignments = optimize_cart(products, all_listings)
    write_output(assignments)


if __name__ == "__main__":
    asyncio.run(main())
