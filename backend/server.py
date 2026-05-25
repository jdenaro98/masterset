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
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed


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

# Make imports work when run from any cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cart_create
import optimizer

# ── stdout helpers ────────────────────────────────────────────────────────────


def _send(obj):
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

# ── API handlers ──────────────────────────────────────────────────────────────


def handle_get_theme(params):
    """Pick a random pokemon art file, extract dominant colors, return art + RGB theme."""
    art_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "art", "ascii", "pokemon",
    )
    files = [f for f in os.listdir(art_dir) if f.endswith("_color.txt")]
    chosen = random.choice(files)
    path = os.path.join(art_dir, chosen)
    with open(path) as f:
        content = f.read()

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
        "artContent": content,
        "primary":    list(primary),
        "secondary":  list(secondary),
        "accent":     list(accent),
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
        games[item.get("productLineName")] = item.get("productLineId")
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


def handle_fetch_cards(params):
    set_id, game_id = params["setId"], params["gameId"]
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
            return []
        url = (
            f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}"
            f"/cards/?rows=5000&productTypeID={pd_id}"
        )
        r = ctx.get(url, headers=_HEADERS)
        if not r.ok:
            return []
        data = r.json()
        results = data.get("result", data.get("results", data)) if isinstance(data, dict) else data
    out = {}
    for item in results:
        out[item.get("productName")] = item.get("productID")
    return out


def _fetch_one(product_id, max_listings):
    url = f"https://mp-search-api.tcgplayer.com/v1/product/{product_id}/listings"
    hdrs = {**_HEADERS, "Content-Type": "application/json"}
    all_listings, offset, size = [], 0, min(50, max_listings or 50)
    session = requests.Session()
    try:
        while True:
            if max_listings and len(all_listings) >= max_listings:
                break
            payload = {
                "filters": {
                    "term": {"sellerStatus": "Live", "channelId": 0},
                    "range": {"quantity": {"gte": 1}},
                    "exclude": {"channelExclusion": 0},
                },
                "from": offset, "size": size,
                "sort": {"field": "price+shipping", "order": "asc"},
                "context": {"shippingCountry": "US", "cart": {"packages": {}}},
                "aggregations": ["listingType"],
            }
            r = session.post(url, headers=hdrs, json=payload, timeout=15)
            if not r.ok:
                break
            data = r.json()
            if "results" not in data or not data["results"]:
                break
            listings = data["results"][0].get("results", [])
            if not listings:
                break
            cap = listings[:max_listings - len(all_listings)] if max_listings else listings
            all_listings.extend(cap)
            if len(listings) < size:
                break
            offset += size
    finally:
        session.close()
    return all_listings


_LANG_OTHERS = (
    r"(Japanese|Chinese|Korean|Spanish|French|German|Italian"
    r"|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)"
)


def _clean_listings(raw):
    cleaned = []
    for item in raw:
        if not (item.get("verifiedSeller") or item.get("goldSeller")):
            continue
        if item.get("condition") not in ("Near Mint", "Lightly Played"):
            continue
        title = item.get("customData", {}).get("title", "")
        if title:
            lang = item.get("language", "English")
            others = _LANG_OTHERS.replace(lang + "|", "").replace("|" + lang, "")
            if re.search(others, title, re.I):
                continue
        sd = item.get("sellerShippingPrice") == 0 and item.get("shippingPrice", 0) > 0
        with contextlib.suppress(Exception):
            cleaned.append({
                "price":         item.get("price"),
                "shipping":      item.get("shippingPrice"),
                "total":         (item.get("price") or 0) + (item.get("shippingPrice") or 0),
                "shipping_deal": sd,
                "seller":        item.get("sellerName"),
                "verifiedSeller": item.get("verifiedSeller"),
                "goldSeller":    item.get("goldSeller"),
                "condition":     item.get("condition"),
                "sku":           int(item.get("productConditionId") or 0),
                "sellerKey":     item.get("sellerKey"),
                "title":         title or "No Picture Linked",
                "custom_listing_key": item.get("customData", {}).get("linkId", "No Picture Linked"),
            })
    return cleaned


def handle_fetch_listings(params):
    """Fetch listings for all tasks, emitting progress events as each card finishes."""
    tasks = params["tasks"]
    max_listings = params.get("maxListings", 50)
    max_workers = min(8, len(tasks))

    all_card_data = {}
    total = len(tasks)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {
            ex.submit(_fetch_one, t["productId"], max_listings): t
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
            cleaned = _clean_listings(raw)
            all_card_data[str(pid)] = {
                "card_info": {"name": name, "total_active_listings": len(cleaned)},
                "market_listings": cleaned,
            }
            done += 1
            _progress(done=done, total=total, card=name)

    return all_card_data


def handle_optimize(params):
    all_card_data = params["allCardData"]
    return optimizer.optimize(all_card_data)


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


# ── dispatch table ────────────────────────────────────────────────────────────

HANDLERS = {
    "get_theme":        handle_get_theme,
    "fetch_categories": handle_fetch_categories,
    "fetch_sets":       handle_fetch_sets,
    "fetch_cards":      handle_fetch_cards,
    "fetch_listings":   handle_fetch_listings,
    "optimize":         handle_optimize,
    "create_cart":      handle_create_cart,
    "close_browser":    handle_close_browser,
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
