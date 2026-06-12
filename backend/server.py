"""
JSON-RPC-style IPC server.

Node.js sends one JSON request per line on stdin:
  {"id": 1, "method": "fetch_categories", "params": {}}

This server writes one JSON response per line on stdout:
  {"id": 1, "result": [...]}

Progress events (no id) are also written to stdout:
  {"type": "progress", "done": 3, "total": 10, "card": "Lightning Bolt [...]"}

All logging / debug output goes to stderr so it never corrupts the protocol.
"""

import contextlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Resolve the root directory for bundled assets (art/, etc.).
# When frozen by PyInstaller, sys._MEIPASS is the extraction dir and
# PLAYWRIGHT_BROWSERS_PATH must be set before playwright is imported.
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', os.path.join(_BASE_DIR, 'ms-playwright'))
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _BASE_DIR)


def _platform_ua():
    if sys.platform == "darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0)"
            " Gecko/20100101 Firefox/150.0"
        )
    if sys.platform == "win32":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0)"
            " Gecko/20100101 Firefox/150.0"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64; rv:150.0)"
        " Gecko/20100101 Firefox/150.0"
    )

import requests
from playwright.sync_api import sync_playwright

# _BASE_DIR and sys.path already set at module top

import cart_create
import optimizer

# ── stdout helpers ────────────────────────────────────────────────────────────


_stdout_lock = threading.Lock()


def _send(obj):
    with _stdout_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def _ok(req_id, result):
    _send({"id": req_id, "result": result})


def _err(req_id, msg):
    _send({"id": req_id, "error": str(msg)})


def _progress(**kwargs):
    _send({"type": "progress", **kwargs})


def _log(msg):
    sys.stderr.write(f"[backend] {msg}\n")
    sys.stderr.flush()


# ── color helpers (used by handle_get_theme) ──────────────────────────────────


def _brightness(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def _boost(c, target=160):
    b = _brightness(c)
    if b < target:
        s = target / max(b, 1)
        return tuple(min(255, int(v * s)) for v in c)
    return c


# ── API headers ───────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": _platform_ua(),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.tcgplayer.com",
    "Referer": "https://www.tcgplayer.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# ── full listing cache (populated by handle_fetch_listings) ───────────────────

_cached_card_data = {}

# ── pre-query disk+memory cache ───────────────────────────────────────────────

_CACHE_TTL = 7 * 24 * 3600  # 7 days in seconds
_mem_cache: dict = {}


def _cache_dir():
    d = os.path.join(os.path.expanduser('~'), '.pokescraper', 'cache')
    os.makedirs(d, exist_ok=True)
    return d


def _cache_file(key):
    safe = key.replace(':', '__')
    return os.path.join(_cache_dir(), f'{safe}.json')


def _cache_get(key):
    if key in _mem_cache:
        return _mem_cache[key]
    try:
        with open(_cache_file(key), encoding='utf-8') as f:
            entry = json.load(f)
        if time.time() - entry['ts'] < _CACHE_TTL:
            _mem_cache[key] = entry['val']
            return entry['val']
    except Exception:
        pass
    return None


def _cache_set(key, value):
    _mem_cache[key] = value
    try:
        with open(_cache_file(key), 'w', encoding='utf-8') as f:
            json.dump({'ts': time.time(), 'val': value}, f)
    except Exception:
        pass


def _cache_del(key):
    _mem_cache.pop(key, None)
    try:
        os.remove(_cache_file(key))
    except Exception:
        pass

# ── API handlers ──────────────────────────────────────────────────────────────


def _load_pokemon_names():
    names_path = os.path.join(_BASE_DIR, "art", "ascii", "pokemon", "pokemon_names.json")
    with open(names_path, encoding="utf-8") as f:
        return json.load(f)

_pokemon_names = None


def handle_get_theme(params):
    """Pick a random pokemon art file, extract dominant colors, return art + RGB theme."""
    global _pokemon_names
    if _pokemon_names is None:
        _pokemon_names = _load_pokemon_names()

    art_dir = os.path.join(_BASE_DIR, "art", "ascii", "pokemon")
    files = [f for f in os.listdir(art_dir) if f.endswith("_color.txt")]
    chosen = random.choice(files)
    path = os.path.join(art_dir, chosen)
    with open(path) as f:
        content = f.read()

    num = int(chosen.replace("_color.txt", ""))
    pokemon_name = _pokemon_names.get(str(num), f"#{num}")

    raw = re.findall(r"\x1b\[38;2;(\d+);(\d+);(\d+)m", content)
    colors = [(int(r), int(g), int(b)) for r, g, b in raw]

    usable = [c for c in colors if 50 < _brightness(c) < 230 and max(c) - min(c) > 25]
    pool = usable or colors or [(180, 180, 200)]

    counter = Counter(pool)
    clusters = []
    for color, count in counter.most_common():
        merged = False
        for cluster in clusters:
            if _dist(color, cluster[0]) < 45:
                cluster[1] += count
                merged = True
                break
        if not merged:
            clusters.append([color, count])
    clusters.sort(key=lambda x: x[1], reverse=True)
    dom = [c[0] for c in clusters[:3]]
    while len(dom) < 3:
        dom.append(dom[-1])

    primary, secondary, accent = _boost(dom[0]), _boost(dom[1]), _boost(dom[2])
    return {
        "artContent":   content,
        "pokemonName":  pokemon_name,
        "primary":      list(primary),
        "secondary":    list(secondary),
        "accent":       list(accent),
    }


_EXCLUDED_CATEGORIES = {
    "Books",
    "Bulk Lots",
    "Chrono Clash System",
    "Funko",
    "Card Sleeves",
    "Card Storage Tins",
    "Collectible Storage",
    "Deck Boxes",
    "Life Counters",
    "Playmats",
    "Protective Pages",
    "Storage Albums",
    "Supply Bundles",
    "TCGplayer Supplies",
}


def handle_fetch_categories(params):
    url = "https://mp-search-api.tcgplayer.com/v1/search/productLines"
    with sync_playwright() as p:
        ctx = p.request.new_context()
        r = ctx.get(url, headers=_HEADERS)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status}")
        data = r.json()
    games = {}
    for item in data:
        name = item.get("productLineName")
        if name not in _EXCLUDED_CATEGORIES:
            games[name] = item.get("productLineId")
    return dict(sorted(games.items()))


def handle_fetch_sets(params):
    game_id = params["gameId"]
    url = (
        f"https://mpapi.tcgplayer.com/v2/Catalog/SetNames"
        f"?categoryId={game_id}&active=true&mpfev=5154"
    )
    for attempt in range(3):
        try:
            with sync_playwright() as p:
                ctx = p.request.new_context()
                r = ctx.get(url, headers=_HEADERS)
                if not r.ok:
                    raise RuntimeError(f"HTTP {r.status}")
                data = r.json()
                results = data.get("results", data) if isinstance(data, dict) else data
            out = {}
            for item in results:
                out[item.get("name")] = item.get("setNameId")
            return out
        except Exception:
            if attempt < 2:
                time.sleep(2)
            else:
                raise


def _probe_set_has_cards(set_id, pd_id):
    """Return True if the priceguide endpoint returns at least one card for the set."""
    url = (
        f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}"
        f"/cards/?rows=1&productTypeID={pd_id}"
    )
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        if not r.ok:
            return False
        data = r.json()
        results = data.get("result", data.get("results", data)) if isinstance(data, dict) else data
        return bool(results) if isinstance(results, list) else False
    except Exception:
        return False


def handle_check_filter_cache(params):
    """Return whether a valid filter_sets cache entry exists for this game."""
    game_id = params["gameId"]
    cached = _cache_get(f"filter_sets:{game_id}")
    return {"cached": cached is not None}


def handle_filter_sets(params):
    """
    Probe each set in parallel (rows=1) to check for price guide data.
    Returns {sets: {...}, from_cache: bool}; falls back to all sets
    if the Cards product type ID cannot be determined or no sets pass.
    Accepts force=True to bypass and refresh the cache.
    """
    game_id = params["gameId"]
    sets    = params["sets"]   # {name: setId}
    force   = params.get("force", False)

    if not sets:
        return {"sets": sets, "from_cache": False}

    cache_key = f"filter_sets:{game_id}"

    if not force:
        cached = _cache_get(cache_key)
        if cached is not None:
            _log(f"filter_sets: cache hit for game {game_id}")
            return {"sets": cached, "from_cache": True}
    else:
        _cache_del(cache_key)

    pdurl = f"https://mpapi.tcgplayer.com/v2/Product/ProductTypes/{game_id}/?mpfev=5154"
    pd_id = None
    with sync_playwright() as p:
        ctx = p.request.new_context()
        r = ctx.get(pdurl, headers=_HEADERS)
        data = r.json()
        if isinstance(data, dict):
            pd_id = next(
                (i.get("productTypeId") for i in data.get("results", [])
                 if i.get("productName") == "Cards"),
                None,
            )

    if pd_id is None:
        return {"sets": sets, "from_cache": False}

    total = len(sets)
    _log(f"Probing {total} sets for game {game_id} (pd_id={pd_id})…")

    filtered = {}
    done = 0
    max_workers = min(50, total)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_probe_set_has_cards, sid, pd_id): name for name, sid in sets.items()}
        for future in as_completed(futures):
            name = futures[future]
            has_cards = future.result()
            done += 1
            _send({"type": "probe_progress", "done": done, "total": total, "set": name})
            if has_cards:
                filtered[name] = sets[name]

    result = filtered if filtered else sets
    _log(f"  {len(result)}/{total} sets have price data")
    _cache_set(cache_key, result)
    return {"sets": result, "from_cache": False}


def handle_fetch_cards(params):
    set_id, game_id = params["setId"], params["gameId"]

    cache_key = f"fetch_cards:{game_id}:{set_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        _log(f"fetch_cards: cache hit for set {set_id}")
        return {"cards": cached, "from_cache": True}

    pdurl = f"https://mpapi.tcgplayer.com/v2/Product/ProductTypes/{game_id}/?mpfev=5154"
    with sync_playwright() as p:
        ctx = p.request.new_context()
        r = ctx.get(pdurl, headers=_HEADERS)
        data = r.json()
        pd_id = None
        if isinstance(data, dict):
            pd_id = next(
                (i.get("productTypeId") for i in data.get("results", [])
                 if i.get("productName") == "Cards"),
                None,
            )
        if pd_id is None:
            return {"cards": {}, "from_cache": False}
        url = (
            f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}"
            f"/cards/?rows=5000&productTypeID={pd_id}"
        )
        r = ctx.get(url, headers=_HEADERS)
        if not r.ok:
            return {"cards": {}, "from_cache": False}
        data = r.json()
        results = data.get("result", data.get("results", data)) if isinstance(data, dict) else data

    # Collect printings per productID so we can detect multi-printing products.
    pid_to_info = {}
    for item in results:
        name = item.get("productName") or ""
        if name.startswith("Code Card"):
            continue
        pid      = item.get("productID")
        printing = item.get("printing") or None
        number   = item.get("number") or None
        if pid not in pid_to_info:
            pid_to_info[pid] = {"name": name, "printings": set(), "number": number}
        if printing:
            pid_to_info[pid]["printings"].add(printing)

    # When a single productID covers multiple printings, expose each printing as
    # its own selectable entry so users can request a specific variant.
    out = {}
    for pid, info in pid_to_info.items():
        name      = info["name"]
        printings = info["printings"]
        number    = info["number"]
        if len(printings) > 1:
            for printing in sorted(printings):
                out[f"{name} ({printing})"] = {"productId": pid, "printing": printing, "number": number}
        else:
            out[name] = {"productId": pid, "printing": next(iter(printings), None), "number": number}

    _cache_set(cache_key, out)
    return {"cards": out, "from_cache": False}


_MAX_RETRIES = 4
_RETRY_BACKOFF = [2, 5, 10, 20]  # seconds between attempts


def _fetch_one(product_id, printing=None, page_cb=None):
    """Fetch ALL listings for a product, paginating until exhausted.

    page_cb(count) is called after each full page (count = total fetched so far).
    Each page request retries up to _MAX_RETRIES times on timeout/connection errors
    and 5xx responses, with increasing backoff between attempts.
    """
    url = f"https://mp-search-api.tcgplayer.com/v1/product/{product_id}/listings"
    hdrs = {**_HEADERS, "Content-Type": "application/json"}
    all_listings, offset = [], 0
    size = 50
    session = requests.Session()
    try:
        while True:
            term_filter = {"sellerStatus": "Live", "channelId": 0}
            if printing:
                term_filter["printing"] = [printing]
            payload = {
                "filters": {
                    "term": term_filter,
                    "range": {"quantity": {"gte": 1}},
                    "exclude": {"channelExclusion": 0},
                },
                "from": offset, "size": size,
                "sort": {"field": "price+shipping", "order": "asc"},
                "context": {"shippingCountry": "US", "cart": {"packages": {}}},
                "aggregations": ["listingType"],
            }

            r = None
            last_exc = None
            for attempt in range(_MAX_RETRIES):
                try:
                    r = session.post(url, headers=hdrs, json=payload, timeout=15)
                    if r.status_code == 429 or r.status_code >= 500:
                        # Retryable server-side error
                        raise requests.exceptions.RequestException(
                            f"HTTP {r.status_code}"
                        )
                    last_exc = None
                    break
                except (
                    requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.RequestException,
                ) as e:
                    last_exc = e
                    if attempt < _MAX_RETRIES - 1:
                        _log(
                            f"page fetch failed (attempt {attempt + 1}/{_MAX_RETRIES},"
                            f" offset {offset}): {e} — retrying in"
                            f" {_RETRY_BACKOFF[attempt]}s"
                        )
                        time.sleep(_RETRY_BACKOFF[attempt])
                    else:
                        _log(
                            f"page fetch failed after {_MAX_RETRIES} attempts"
                            f" (offset {offset}): {e}"
                        )

            if last_exc is not None or r is None or not r.ok:
                break

            data = r.json()
            if "results" not in data or not data["results"]:
                break
            listings = data["results"][0].get("results", [])
            if not listings:
                break
            all_listings.extend(listings)
            if len(listings) < size:
                break
            if page_cb:
                page_cb(len(all_listings))
            offset += size
    finally:
        session.close()
    return all_listings


_LANG_OTHERS = (
    r"(Japanese|Chinese|Korean|Spanish|French|German|Italian"
    r"|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)"
)


def _normalize_listings(raw):
    """
    Language-filter and normalize raw API listings.
    Keeps all conditions and seller types — filtering happens later via _apply_filters.
    """
    normalized = []
    for item in raw:
        title = item.get("customData", {}).get("title", "")
        if title:
            lang = item.get("language", "English")
            others = _LANG_OTHERS.replace(lang + "|", "").replace("|" + lang, "")
            if re.search(others, title, re.I):
                continue
        raw_seller_ship = item.get("sellerShippingPrice")
        raw_buyer_ship  = item.get("shippingPrice")
        sd = raw_seller_ship == 0 and (raw_buyer_ship or 0) > 0
        with contextlib.suppress(Exception):
            progs = item.get("sellerPrograms") or []
            normalized.append({
                "price":                item.get("price"),
                "shipping":             raw_buyer_ship,
                "total":                (item.get("price") or 0) + (raw_buyer_ship or 0),
                "shipping_deal":        sd,
                "seller":               item.get("sellerName"),
                "seller_id":            item.get("sellerId"),
                "goldSeller":           item.get("goldSeller", False),
                "directSeller":         bool(item.get("directSeller") or item.get("directListing") or "Direct" in progs),
                "sellerPrograms":       progs,
                "condition":            item.get("condition"),
                "sku":                  int(item.get("productConditionId") or 0),
                "sellerKey":            item.get("sellerKey"),
                "title":                title or "No Picture Linked",
                "custom_listing_key":   item.get("customData", {}).get("linkId", "No Picture Linked"),
                "_raw_seller_shipping": raw_seller_ship,
                "_raw_buyer_shipping":  raw_buyer_ship,
            })
    return normalized


# Maps the qualifier keys the frontend sends to listing field checks.
# "Verified" on TCGPlayer's website = goldSeller:true in the API (verifiedSeller is unrelated).
_QUAL_CHECKS = {
    "Verified": lambda l: l.get("goldSeller", False),
    "Direct":   lambda l: l.get("directSeller", False),
    "WPN":      lambda l: "WizardsPlayNetwork" in (l.get("sellerPrograms") or []),
}


def _apply_filters(listings, conditions, seller_quals):
    """
    Conditions: OR (e.g. Near Mint OR Damaged → either is acceptable).
    Seller quals: AND (e.g. Gold Star AND WPN → seller must hold both).
    Across the two categories: AND.
    Empty list for a category = no filter on that category (all listings pass).
    """
    cond_set = set(conditions) if conditions else None
    active_quals = [q for q in (seller_quals or []) if q in _QUAL_CHECKS]

    result = []
    for listing in listings:
        if cond_set and listing.get("condition") not in cond_set:
            continue
        if active_quals and not all(_QUAL_CHECKS[q](listing) for q in active_quals):
            continue
        result.append(listing)
    return result


def handle_fetch_listings(params):
    """Fetch all listings for every task, emitting progress events as each card finishes."""
    global _cached_card_data

    tasks = params["tasks"]
    max_workers = min(16, len(tasks))

    all_card_data = {}
    total = len(tasks)
    done = 0

    def _make_page_cb(card_name):
        def cb(count):
            _send({"type": "card_page_progress", "card": card_name, "fetched": count})
        return cb

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {
            ex.submit(_fetch_one, t["productId"], t.get("printing"), _make_page_cb(t["displayName"])): t
            for t in tasks
        }
        for future in as_completed(future_map):
            t = future_map[future]
            pid, name = t["productId"], t["displayName"]
            try:
                raw = future.result()
            except Exception as e:
                _log(f"Error fetching {name}: {e}")
                raw = []
            normalized = _normalize_listings(raw)
            all_card_data[str(pid)] = {
                "card_info": {"name": name, "total_active_listings": len(normalized)},
                "market_listings": normalized,
            }
            done += 1
            _progress(done=done, total=total, card=name)

    _cached_card_data = all_card_data
    return all_card_data


def handle_optimize(params):
    all_card_data = params["allCardData"]
    return optimizer.optimize(all_card_data)


def _apply_filters_with_fallback(card_data_map, conditions, seller_quals):
    """
    Apply filters to each card, falling back progressively when no listings match.
    Fallback order: full → drop condition → drop sellerQual → all listings.
    Returns (filtered_data, overrides) where overrides is a list of
    {"name": str, "applied": str} for cards whose filter was relaxed.
    """
    filtered_data = {}
    overrides     = []
    has_cond  = bool(conditions)
    has_qual  = bool(seller_quals)

    cond_str = " / ".join(conditions) if conditions else ""
    qual_str  = " / ".join(seller_quals) if seller_quals else ""

    for pid, card_data in card_data_map.items():
        raw  = card_data["market_listings"]
        name = card_data["card_info"]["name"]

        # Cards with no listings at all: flag unconditionally, skip filter tiers
        if not raw:
            filtered_data[pid] = {**card_data, "market_listings": []}
            overrides.append({"name": name, "applied": "no listings found"})
            continue

        # Tier 1: full filter
        result = _apply_filters(raw, conditions, seller_quals)
        if result or (not has_cond and not has_qual):
            filtered_data[pid] = {**card_data, "market_listings": result if result else raw}
            continue

        # Tier 2: keep seller qual, drop condition
        if has_cond and has_qual:
            result = _apply_filters(raw, [], seller_quals)
            if result:
                filtered_data[pid] = {**card_data, "market_listings": result}
                overrides.append({"name": name, "applied": f"no {cond_str} listings from {qual_str} sellers"})
                continue

        # Tier 3: keep condition, drop seller qual
        if has_qual:
            result = _apply_filters(raw, conditions, [])
            if result:
                filtered_data[pid] = {**card_data, "market_listings": result}
                reason = (f"no {qual_str} seller listings in {cond_str}"
                          if has_cond else f"no {qual_str} seller listings")
                overrides.append({"name": name, "applied": reason})
                continue

        # Tier 4: no filter
        filtered_data[pid] = {**card_data, "market_listings": raw}
        if has_cond and has_qual:
            reason = f"no listings match {cond_str} or {qual_str} sellers"
        else:
            reason = f"no {cond_str} listings"
        overrides.append({"name": name, "applied": reason})

    return filtered_data, overrides


def handle_optimize_filtered(params):
    """Run optimizer against cached listings with dynamic filter criteria applied."""
    conditions   = params.get("conditions") or []
    seller_quals = params.get("sellerQuals") or []

    filtered_data, overrides = _apply_filters_with_fallback(
        _cached_card_data, conditions, seller_quals
    )

    if overrides:
        preview = ", ".join(o["name"] for o in overrides[:5])
        suffix  = f" + {len(overrides) - 5} more" if len(overrides) > 5 else ""
        _log(f"filter relaxed for {len(overrides)} card(s): {preview}{suffix}")

    return {"cart": optimizer.optimize(filtered_data), "overrides": overrides}


def handle_get_filter_options(params):
    """
    Return the conditions and seller qualifications actually present in the cached data,
    ordered canonically.
    """
    CONDITION_ORDER = ["Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"]
    QUAL_ORDER      = ["Verified", "Direct", "WPN"]

    conditions_seen = set()
    quals_seen      = set()

    for card_data in _cached_card_data.values():
        for listing in card_data.get("market_listings", []):
            cond = listing.get("condition")
            if cond:
                conditions_seen.add(cond)
            if listing.get("goldSeller"):
                quals_seen.add("Verified")
            if listing.get("directSeller"):
                quals_seen.add("Direct")
            for prog in (listing.get("sellerPrograms") or []):
                if prog == "WizardsPlayNetwork":
                    quals_seen.add("WPN")

    ordered_conditions = [c for c in CONDITION_ORDER if c in conditions_seen]
    ordered_conditions += sorted(c for c in conditions_seen if c not in CONDITION_ORDER)

    ordered_quals = [q for q in QUAL_ORDER if q in quals_seen]
    ordered_quals += sorted(q for q in quals_seen if q not in QUAL_ORDER)

    return {"conditions": ordered_conditions, "sellerQuals": ordered_quals}


_active_pw = None


def handle_create_cart(params):
    global _active_pw
    optimized_cart = params["optimizedCart"]

    def on_progress(done, total, card):
        _send({"type": "cart_progress", "done": done, "total": total, "card": card})

    cookie_path, failed_items, pw = cart_create.create_cart(
        optimized_cart, progress_callback=on_progress
    )
    _active_pw = pw  # keep Playwright alive so the browser stays open
    return {"cookiePath": cookie_path, "failedItems": failed_items}


def handle_close_browser(params):
    global _active_pw
    if _active_pw:
        try:
            _active_pw.stop()
        except Exception as e:
            _log(f"Error closing browser: {e}")
        finally:
            _active_pw = None
    return {"ok": True}


def handle_dump_listings(params):
    """Write the cached listings to a JSON file for optimizer debugging."""
    out_path = params.get("path") or os.path.join(os.getcwd(), "listings_debug.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_cached_card_data, f, indent=2)
    _log(f"listings dumped to {out_path}")
    return {"path": out_path, "cards": len(_cached_card_data)}


# ── dispatch table ────────────────────────────────────────────────────────────

HANDLERS = {
    "get_theme":              handle_get_theme,
    "fetch_categories":       handle_fetch_categories,
    "fetch_sets":             handle_fetch_sets,
    "check_filter_cache":     handle_check_filter_cache,
    "filter_sets":            handle_filter_sets,
    "fetch_cards":            handle_fetch_cards,
    "fetch_listings":         handle_fetch_listings,
    "optimize":               handle_optimize,
    "optimize_filtered":      handle_optimize_filtered,
    "get_filter_options":     handle_get_filter_options,
    "create_cart":            handle_create_cart,
    "close_browser":          handle_close_browser,
    "dump_listings":          handle_dump_listings,
}

# ── main loop ─────────────────────────────────────────────────────────────────


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"bad JSON: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        handler = HANDLERS.get(method)
        if handler is None:
            _err(req_id, f"unknown method: {method}")
            continue

        try:
            result = handler(params)
            _ok(req_id, result)
        except Exception as e:
            _log(traceback.format_exc())
            _err(req_id, str(e))


if __name__ == "__main__":
    main()
