import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright


def _log(msg):
    sys.stderr.write(f"[cart] {msg}\n")
    sys.stderr.flush()


def _system_chrome_path():
    """Return the installed Chrome executable path on any platform, or None."""
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                         r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                         r"Google\Chrome\Application\chrome.exe"),
        ]
        return next((p for p in candidates if p and os.path.isfile(p)), None)
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        ]
        return next((p for p in candidates if os.path.isfile(p)), None)
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                return found
        return None


class _SubprocessBrowser:
    def __init__(self, proc):
        self._proc = proc

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


def create_cart(optimized_cart, progress_callback=None):
    """
    Build an anonymous TCGPlayer cart and open it in system Chrome.

    Playwright's bundled Chromium runs headlessly to make all API calls
    (create cart, add items), then closes. System Chrome is launched with
    a fresh temp profile and remote debugging enabled; cookies are injected
    via CDP and Playwright immediately disconnects, leaving Chrome fully
    uncontrolled for the user to log in.

    Returns (cookie_path, failed_items, browser_handle) where browser_handle
    exposes a .stop() method the caller should invoke when done.
    """
    if not optimized_cart:
        _log("No items provided to create a cart.")
        return None, [], None

    user_data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "user_data",
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
            return None, [], None

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
            sku = item.get("sku")
            seller_key = item.get("sellerKey")
            custom_listing_key = item.get("custom_listing_key")
            card_name = item.get("card", "unknown card")
            price = item.get("price", 0)

            if not sku and custom_listing_key in (None, "No Picture Linked", "N/A"):
                failed_items.append({
                    "card": card_name,
                    "sku": None,
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
                    "sellerKey": seller_key,
                    "channelId": 0,
                    "requestedQuantity": 1,
                    "price": price,
                    "isDirect": False,
                    "countryCode": "US",
                }

            try:
                result = page.evaluate(browser_fetch_js, {"url": add_url, "payload": payload})
                if not result["ok"]:
                    _log(f"Failed to add {card_name}: HTTP {result['status']}")
                    failed_items.append({
                        "card": card_name,
                        "sku": sku,
                        "reason": f"HTTP {result['status']} (dead listing or out of stock)",
                    })
            except Exception as e:
                _log(f"Error adding {card_name}: {e}")
                failed_items.append({
                    "card": card_name,
                    "sku": sku,
                    "reason": f"Script error: {e}",
                })

            if progress_callback:
                progress_callback(done_count, total, card_name)

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

        all_cookies = context.cookies()
        tcg_cookies = [c for c in all_cookies if "tcgplayer" in c.get("domain", "")]
        _log(f"Collected {len(tcg_cookies)} TCGPlayer cookies to inject into Chrome")

        context.close()
        _pw.stop()

        chrome_path = _system_chrome_path()
        if not chrome_path:
            _log("System Chrome not found — please open https://www.tcgplayer.com/cart manually.")
            return cookie_path, failed_items, None

        tmp_profile = tempfile.mkdtemp(prefix="pokescraper_")
        _log("Launching Chrome with remote debugging...")
        proc = subprocess.Popen([
            chrome_path,
            f"--user-data-dir={tmp_profile}",
            "--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        cdp_ready = False
        for _ in range(30):
            try:
                urllib.request.urlopen("http://localhost:9222/json/version", timeout=1)
                cdp_ready = True
                break
            except Exception:
                time.sleep(0.5)

        if not cdp_ready:
            _log("Chrome CDP not ready after 15 s — cart URL may not have cookies.")
            return cookie_path, failed_items, _SubprocessBrowser(proc)

        _log("Injecting cookies and navigating to cart...")
        _pw2 = sync_playwright().start()
        try:
            browser = _pw2.chromium.connect_over_cdp("http://localhost:9222")
            ctx2 = browser.contexts[0] if browser.contexts else browser.new_context()
            if tcg_cookies:
                ctx2.add_cookies(tcg_cookies)
            page2 = ctx2.pages[0] if ctx2.pages else ctx2.new_page()
            page2.goto("https://www.tcgplayer.com/cart", wait_until="domcontentloaded")
        except Exception as e:
            _log(f"CDP injection failed: {e}")
        finally:
            try:
                _pw2.stop()
            except Exception:
                pass

        _log("Cart loaded in Chrome — Playwright disconnected.")

        class _ChromeBrowser:
            def stop(self_):
                if proc.poll() is None:
                    proc.terminate()
                shutil.rmtree(tmp_profile, ignore_errors=True)

        return cookie_path, failed_items, _ChromeBrowser()

    except Exception:
        try:
            _pw.stop()
        except Exception:
            pass
        raise
