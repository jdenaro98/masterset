import json
import os
import sys
import time

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', os.path.join(_BASE_DIR, 'ms-playwright'))
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from playwright.sync_api import sync_playwright


def _log(msg):
    sys.stderr.write(f"[cart] {msg}\n")
    sys.stderr.flush()


def create_cart(optimized_cart, progress_callback=None):
    """
    Build an anonymous TCGPlayer cart using headless Playwright.

    Returns (cart_key, failed_items).  The cart_key can be passed back to the
    frontend so the user can view their cart at https://www.tcgplayer.com/cart.
    """
    if not optimized_cart:
        _log("No items provided to create a cart.")
        return None, []

    user_data_dir = os.path.join(
        os.environ.get('MASTERSET_USER_DATA') or _BASE_DIR, 'user_data'
    )
    os.makedirs(user_data_dir, exist_ok=True)

    _log("Building cart (headless)...")
    _pw = sync_playwright().start()
    try:
        context = _pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-notifications",
                "--disable-logging",
                "--log-level=3",
                "--disable-crash-reporter",
                "--disable-component-update",
                "--disable-background-networking",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_navigation_timeout(60000)

        _log("Initializing TCGPlayer session...")
        page.goto("https://www.tcgplayer.com/", wait_until="domcontentloaded")
        time.sleep(2)

        _log("Creating cart...")
        create_result = page.evaluate("""
            async () => {
                const r = await fetch(
                    'https://mpgateway.tcgplayer.com/v1/cart/create/anonymouscart?mpfev=5143',
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json, text/plain, */*'
                        }
                    }
                );
                return { ok: r.ok, status: r.status, text: await r.text() };
            }
        """)

        if not create_result["ok"]:
            _log(
                f"Failed to create cart: HTTP {create_result['status']}:"
                f" {create_result['text']}"
            )
            return None, []

        cart_data = json.loads(create_result["text"])
        cart_key = cart_data["results"][0]["cartKey"]
        _log(f"Cart initialized: {cart_key}")

        context.add_cookies([{
            "name": "StoreCart_PRODUCTION",
            "value": f"CK={cart_key}&Ignore=false",
            "domain": ".tcgplayer.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
        }])

        failed_items = []
        total = len(optimized_cart)

        requests_to_make = []
        for item in optimized_cart:
            sku = item.get("sku")
            custom_listing_key = item.get("custom_listing_key")
            card_name = item.get("card", "unknown card")
            price = item.get("price", 0)

            if not sku and custom_listing_key in (None, "No Picture Linked", "N/A"):
                failed_items.append({
                    "card": card_name,
                    "sku": None,
                    "reason": "No listing found during optimization",
                })
                continue

            if custom_listing_key and custom_listing_key not in ("No Picture Linked", "N/A"):
                add_url = (
                    f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}"
                    "/listo/add?mpfev=5143"
                )
                payload = {
                    "customListingKey": custom_listing_key,
                    "priceAtAdd": price,
                    "quantityToBuy": 1,
                    "channelId": 0,
                    "countryCode": "US",
                }
            else:
                add_url = (
                    f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}"
                    "/item/add?mpfev=5143"
                )
                payload = {
                    "sku": sku,
                    "sellerKey": item.get("sellerKey"),
                    "channelId": 0,
                    "requestedQuantity": 1,
                    "price": price,
                    "isDirect": False,
                    "countryCode": "US",
                }

            requests_to_make.append({
                "url": add_url,
                "payload": payload,
                "card": card_name,
                "sku": sku,
            })

        if requests_to_make:
            batch_js = """
            async (items) => {
                const results = await Promise.allSettled(
                    items.map(item =>
                        fetch(item.url, {
                            method: 'POST',
                            credentials: 'include',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json, text/plain, */*'
                            },
                            body: JSON.stringify(item.payload)
                        }).then(async r => ({
                            ok: r.ok,
                            status: r.status,
                            card: item.card,
                            sku: item.sku,
                        }))
                    )
                );
                return results.map((r, i) =>
                    r.status === 'fulfilled'
                        ? r.value
                        : { ok: false, status: 0, card: items[i].card, sku: items[i].sku, error: String(r.reason) }
                );
            }
            """
            try:
                results = page.evaluate(batch_js, requests_to_make)
            except Exception as e:
                _log(f"Batch add failed: {e}")
                results = [{"ok": False, "status": 0, "card": r["card"], "sku": r["sku"], "error": str(e)} for r in requests_to_make]

            for i, result in enumerate(results):
                card_name = result["card"]
                sku = result["sku"]
                if not result["ok"]:
                    reason = result.get("error") or f"HTTP {result['status']} (dead listing or out of stock)"
                    _log(f"Failed to add {card_name}: {reason}")
                    failed_items.append({"card": card_name, "sku": sku, "reason": reason})
                if progress_callback:
                    progress_callback(len(failed_items) + (i + 1), total, card_name)

        if failed_items:
            _log(f"{len(failed_items)} item(s) could not be added automatically.")
        else:
            _log("All items added successfully.")

        context.close()
        _pw.stop()
        return cart_key, failed_items

    except Exception:
        try:
            _pw.stop()
        except Exception:
            pass
        raise
