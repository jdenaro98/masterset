import json
import os
import sys
import time

from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


def _log(msg):
    sys.stderr.write(f"[cart] {msg}\n")
    sys.stderr.flush()


def create_cart(optimized_cart, progress_callback=None):
    """
    Add items to a TCGPlayer anonymous cart via Playwright.

    progress_callback(done, total, card_name) is called after each item attempt.

    Returns (cookie_path, failed_items, pw) where pw is the live Playwright
    instance.  The caller must call pw.stop() when it is ready to close the
    browser.
    """
    if not optimized_cart:
        _log("No items provided to create a cart.")
        return None, [], None

    _log("Launching browser...")
    _pw = sync_playwright().start()
    try:
        stealth = Stealth()
        stealth.use_sync(_pw)
        stealth.hook_playwright_context(_pw)

        user_data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "user_data",
        )
        context = _pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=[
                "--window-size=1280,720",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-features=TranslateUI",
                "--disable-gpu",
            ],
        )
        stealth.apply_stealth_sync(context)
        context.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
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
            return None, [], _pw

        cart_data = json.loads(create_result["text"])
        cart_key  = cart_data["results"][0]["cartKey"]
        _log(f"Cart initialized: {cart_key}")

        context.add_cookies([{
            "name":     "StoreCart_PRODUCTION",
            "value":    f"CK={cart_key}&Ignore=false",
            "domain":   ".tcgplayer.com",
            "path":     "/",
            "httpOnly": False,
            "secure":   True,
            "sameSite": "Lax",
        }])

        failed_items = []
        browser_fetch_js = """
        async (args) => {
            const r = await fetch(args.url, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/plain, */*'
                },
                body: JSON.stringify(args.payload)
            });
            return { ok: r.ok, status: r.status, text: await r.text() };
        }
        """

        total = len(optimized_cart)
        for done_count, item in enumerate(optimized_cart, start=1):
            sku                = item.get("sku")
            seller_key         = item.get("sellerKey")
            custom_listing_key = item.get("custom_listing_key")
            card_name          = item.get("card", "unknown card")
            price              = item.get("price", 0)

            if not sku and custom_listing_key in (None, "No Picture Linked", "N/A"):
                failed_items.append({
                    "card":   card_name,
                    "sku":    None,
                    "reason": "No listing found during optimization",
                })
                if progress_callback:
                    progress_callback(done_count, total, card_name)
                continue

            if custom_listing_key and custom_listing_key not in ("No Picture Linked", "N/A"):
                add_url = (
                    f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}"
                    "/listo/add?mpfev=5143"
                )
                payload = {
                    "customListingKey": custom_listing_key,
                    "priceAtAdd":       price,
                    "quantityToBuy":    1,
                    "channelId":        0,
                    "countryCode":      "US",
                }
            else:
                add_url = (
                    f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}"
                    "/item/add?mpfev=5143"
                )
                payload = {
                    "sku":               sku,
                    "sellerKey":         seller_key,
                    "channelId":         0,
                    "requestedQuantity": 1,
                    "price":             price,
                    "isDirect":          False,
                    "countryCode":       "US",
                }

            try:
                result = page.evaluate(browser_fetch_js, {"url": add_url, "payload": payload})
                if not result["ok"]:
                    _log(f"Failed to add {card_name}: HTTP {result['status']}")
                    failed_items.append({
                        "card":   card_name,
                        "sku":    sku,
                        "reason": f"HTTP {result['status']} (dead listing or out of stock)",
                    })
            except Exception as e:
                _log(f"Error adding {card_name}: {e}")
                failed_items.append({
                    "card":   card_name,
                    "sku":    sku,
                    "reason": f"Script error: {e}",
                })

            if progress_callback:
                progress_callback(done_count, total, card_name)

        # Navigate to cart so it's visible when the user looks at the browser
        _log("Opening cart...")
        page.goto("https://www.tcgplayer.com/cart", wait_until="load")

        if failed_items:
            _log(f"{len(failed_items)} item(s) could not be added automatically.")
            for idx, f in enumerate(failed_items, 1):
                _log(f"  [{idx}] {f['card']}: {f['reason']}")
        else:
            _log("All items added successfully.")

        cookie_path = None
        try:
            context.storage_state(path="tcgplayer_cookies.json")
            cookie_path = "tcgplayer_cookies.json"
            _log("Session saved to tcgplayer_cookies.json")
        except Exception as e:
            _log(f"Could not save cookies: {e}")

        # Return the live Playwright instance — the caller keeps it alive until
        # the user is done, then calls pw.stop() to close the browser.
        return cookie_path, failed_items, _pw

    except Exception:
        try:
            _pw.stop()
        except Exception:
            pass
        raise
