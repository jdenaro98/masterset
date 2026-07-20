---
name: backend
description: Working on the masterset Python backend — the FastAPI WebSocket server, TCGPlayer scraping/caching, the seller-bundling optimizer, and Playwright cart creation. Use when editing backend/*.py, optimizer.py, or cart_create.py, adding a WebSocket method, or debugging scraping/optimization/cart flows.
---

# masterset backend

Python backend that scrapes live TCGPlayer seller listings, optimizes them to minimize seller count (shipping cost), and drives an anonymous cart via headless Playwright. Single-user: one optimizer session at a time.

## Stack & tools
- **FastAPI + uvicorn** — one WebSocket endpoint (`/ws`), plus a static mount for `/art`.
- **requests** — the primary HTTP client for TCGPlayer JSON APIs (listings, price guide probes).
- **Playwright (sync API, Chromium)** — used two ways: `p.request.new_context()` for API calls that need a browser-origin request context (categories/sets/product types), and a full headless persistent context in `cart_create.py` to execute `fetch()` calls with TCGPlayer cookies for cart building.
- **ruff** — lint (`ruff check .`), config in `pyproject.toml`, rules `F` + `E9` only, target py311. CI runs it on every PR (`.github/workflows/ci.yml`).
- No test suite. No formal typing. Python 3.11.

## Files
- [backend/api.py](../../../backend/api.py) — FastAPI app + WebSocket dispatch. Bridges async socket ↔ sync handlers: each request runs a handler on a `threading.Thread`, and `_send`/progress output is pushed back through an `asyncio.Queue` drained to the socket. Monkeypatches `server._send` to route to the active connection (`_active_send`). Also self-signs a local dev TLS cert (see TLS note below).
- [backend/server.py](../../../backend/server.py) — all request handlers + the `HANDLERS` dispatch table. This is where nearly all backend logic lives: scraping, the 7-day disk+memory cache, language/condition filtering, and the dynamic-filter fallback tiers.
- [optimizer.py](../../../optimizer.py) — pure function `optimize(all_card_data)`. Greedy seller-bundling; no I/O, no deps beyond `math`.
- [cart_create.py](../../../cart_create.py) — `create_cart(optimized_cart, progress_callback)`. Headless Playwright builds an anonymous cart by POSTing to TCGPlayer's cart API from within a real browser session.

## WebSocket protocol
JSON-RPC-ish over one socket (mirrors an older stdin/stdout pipe protocol — keep it identical):
```
Client → Server  {"id": 1, "method": "fetch_categories", "params": {}}
Server → Client  {"id": 1, "result": [...]}              # or {"id":1,"error":"..."}
Server → Client  {"type": "progress", "done": 3, "total": 10, "card": "..."}  # pushed events
```
Handlers return a value (becomes `result`) and may call `_send(...)`/`_progress(...)`/`_log(...)` to push typed events (`progress`, `probe_progress`, `card_page_progress`, `cart_progress`, `backend_log`). To add a method: write `handle_x(params)` in `server.py` and register it in `HANDLERS`.

## Data flow (the happy path)
1. `fetch_categories` → product lines (games), minus `_EXCLUDED_CATEGORIES`.
2. `fetch_sets` → set names/ids for a game.
3. `filter_sets` → probes each set in parallel (ThreadPoolExecutor, ≤50 workers, `rows=1`) for price-guide data; result cached 7 days. `check_filter_cache` gates whether the frontend streams probe progress.
4. `fetch_cards` → all cards in a set; multi-printing products are split into one entry per printing. Cached.
5. `fetch_listings` → for each requested card, `_fetch_one` paginates ALL live US listings (size 50, retries w/ backoff on 429/5xx). `_normalize_listings` language-filters and flattens. Result stored in module-global `_cached_card_data`, keyed by **`cardId` = `f"{productId}:{printing or ''}"`** (`_card_id`, matches the frontend binder id). `params["merge"]` merges into the cache (the binder scrapes only newly-added cards) instead of replacing it.
6. `optimize_filtered` → applies dynamic filters with fallback tiers, then runs `optimizer.optimize`. Returns the bundled `cart` and a baseline `firstCart` (cheapest listing per card); every entry carries both `card` (display name) and `cardId`. `params["cardIds"]` (optional) scopes optimization to a subset of the cache via `_scoped_cache` — the binder passes its current card ids, so deleted cards drop out with no eviction step. `get_filter_options` takes the same `cardIds` scope.
7. `create_cart` → Playwright builds the real cart, returns a `cartKey`.

## Optimizer logic ([optimizer.py](../../../optimizer.py))
Goal: minimize sellers to cut shipping, **without ever raising the total** vs. buying each card at its cheapest ("market floor"). Greedy: each round pick the seller whose batch saves the most dollars vs. floor; stop when no seller beats buying individually; remaining cards fall back to their floor listing. `_estimate_shipping` models TCGPlayer's rule: shipping is free when a listing has a shipping deal and the subtotal ≥ $5, else the max per-listing shipping in the batch.

**Identity is the dict key (`cardId`), not the display name.** Every map (`market_floor`, `seller_map[seller]`, `final_assignment`) is keyed by the cache/dict key so a multi-set/multi-game binder can hold two different cards that share a name (e.g. "Pikachu" from two sets) without collapsing them. Each returned entry carries `card` (name, for display) + `cardId`; `cart_create.py` adds by `sku`/`sellerKey`, so the name stays cosmetic.

## Filtering ([server.py](../../../backend/server.py))
- **Conditions** (Near Mint … Damaged) are OR'd; **seller quals** (`Verified`=`goldSeller`, `Direct`, `WPN`=`WizardsPlayNetwork` program) are AND'd; the two categories are AND'd together. Empty list = no filter.
- `_apply_filters_with_fallback` relaxes progressively when nothing matches: full → drop condition → drop seller qual → all listings, recording human-readable `overrides` per card so the UI can explain why a filter was ignored.

## Cart creation & the CSP/TLS gotcha
`cart_create.py` launches a persistent Chromium context, hits tcgplayer.com to get cookies, creates an anonymous cart, sets the `StoreCart_PRODUCTION` cookie, then batch-adds items via `Promise.allSettled` `fetch()` inside the page (reporting progress through an exposed function). Custom listing keys use the `/listo/add` endpoint; bare SKUs use `/item/add`.

The **cart bookmarklet** runs on tcgplayer.com and connects back to `/ws` over `wss://` — TCGPlayer's CSP `connect-src` blocks plain `ws:` and arbitrary `fetch()`, but allows unrestricted `wss:`. So the backend needs TLS. In production Railway terminates TLS at the edge (detected via the injected `PORT` env var). For **local dev only**, `api.py` self-signs a cert into `~/.masterset/dev-tls/` via `openssl`; you must visit `https://localhost:8000` once and click through the warning. `handle_get_pending_cart` (TTL 900s) is what the bookmarklet polls.

## Caching
Two layers keyed by string (`filter_sets:<game>`, `fetch_cards:<game>:<set>`): in-memory `_mem_cache` + JSON files under `~/.masterset/cache/`, TTL 7 days. Listings live only in the in-memory `_cached_card_data` (not disk), keyed by `cardId` (`productId:printing`), and reset on restart — `check_listings_cache` returns the cached `cardId`s so the frontend binder can diff against its localStorage contents and re-scrape only the missing delta (`fetch_listings` with `merge:true`), or fully rebuild after a restart.

## Run & deploy
- Local (both servers): `npm run dev` from repo root (concurrently runs Vite + `python3 backend/api.py`). Backend alone: `python3 backend/api.py` (serves on `:8000`, self-signed TLS).
- Prod: Railway builds `backend/Dockerfile` (python:3.11-slim + Playwright Chromium), runs `python backend/api.py`, binds the injected `PORT`.
