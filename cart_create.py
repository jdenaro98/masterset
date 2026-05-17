import json
import time
import urllib.parse
from playwright.sync_api import Error, sync_playwright
from playwright_stealth.stealth import Stealth
from rich.progress import track

def create_cart(optimized_cart):
    if not optimized_cart:
        print("No items provided to create a cart.")
        return

    print("Launching browser context...")
    with sync_playwright() as pw:
        stealth = Stealth()
        stealth.use_sync(pw)
        stealth.hook_playwright_context(pw)

        browser = pw.chromium.launch(
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=[
                "--window-size=1280,720",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-features=TranslateUI"
            ]
        )
        context = browser.new_context()
        stealth.apply_stealth_sync(context)
        context.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_navigation_timeout(60000)

        # 1. Direct the user to the cart page first
        print("\nNavigating to TCGPlayer...")
        page.goto("https://www.tcgplayer.com/cart", wait_until="load")

        # 2. Halt and ensure the session is logged in and valid
        print("\n" + "="*60)
        print("👉 ACTION REQUIRED IN BROWSER WINDOW:")
        print("   1. Please sign in to your real TCGPlayer account if prompted.")
        print("   2. Ensure you are looking at the active Cart page.")
        print("="*60)
        input("\n>>> Once you are logged in and ready, press [ENTER] here to build your cart... ")

        # 3. Wait for the login flow to settle and for the cart page to be active
        try:
            page.wait_for_url("**/cart*", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=60000)
        except Error:
            print("⚠️ Warning: the browser did not automatically land on the cart page after login.")
            print("⚠️ Current URL:", page.url)
            print("⚠️ Trying a manual cart reload...")
            page.goto("https://www.tcgplayer.com/cart", wait_until="networkidle", timeout=60000)

        time.sleep(2)

        def find_cart_cookie():
            return next((c for c in context.cookies() if c['name'] == 'StoreCart_PRODUCTION'), None)

        cart_cookie = None
        for attempt in range(12):
            cart_cookie = find_cart_cookie()
            if cart_cookie:
                break
            print(f"⚠️ Waiting for StoreCart_PRODUCTION cookie... ({attempt + 1}/12)")
            time.sleep(1)

        if not cart_cookie:
            print("⚠️ Debug: current browser URL:", page.url)
            cookies = context.cookies()
            cookie_names = [c['name'] for c in cookies]
            print("⚠️ Debug: cookies present in context:", cookie_names)
            print("⚠️ Debug: store-related cookies:", [name for name in cookie_names if name.startswith('Store')])
            print("❌ Error: Could not find an active cart session. Please refresh the page in the browser and try again.")
            return

        # Parse out the actual Cart Key (CK) value safely
        parsed_cookie_value = urllib.parse.unquote(cart_cookie['value'])
        cookie_params = dict(x.split('=') for x in parsed_cookie_value.split('&') if '=' in x)
        cart_key = cookie_params.get('CK')

        if not cart_key:
            print("❌ Error: StoreCart_PRODUCTION cookie found but Cart Key (CK) is missing.")
            return

        print(f"\nConnected to secure Cart Key: {cart_key}")
        print("Injecting items using native browser context to prevent detection flags...")

        # Initialize the list to keep track of failed attempts
        failed_items = []

        # 4. Inject the optimized listings directly via internal page execution
        for item in track(optimized_cart, description="Adding Items to Cart ...", total=len(optimized_cart)):
            sku = item.get('sku')
            seller_key = item.get('sellerKey')
            custom_listing_key = item.get('custom_listing_key')
            card_name = item.get('card', 'unknown card')

            if custom_listing_key and custom_listing_key != "No Picture Linked":
                add_url = f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}/listo/add?mpfev=5143"
                payload = {
                    "customListingKey": custom_listing_key,
                    "priceAtAdd": 0,
                    "quantityToBuy": 1,
                    "channelId": 0,
                    "countryCode": "US"
                }
            else:
                add_url = f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}/item/add?mpfev=5143"
                payload = {
                    "sku": sku,
                    "sellerKey": seller_key,
                    "channelId": 0,
                    "requestedQuantity": 1,
                    "price": 0,
                    "isDirect": False,
                    "countryCode": "US"
                }

            browser_fetch_js = """
            async (args) => {
                const response = await fetch(args.url, {
                    method: 'POST',
                    mode: 'cors',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json, text/plain, */*'
                    },
                    body: JSON.stringify(args.payload)
                });
                return { ok: response.ok, status: response.status, text: await response.text() };
            }
            """
            
            try:
                result = page.evaluate(browser_fetch_js, {"url": add_url, "payload": payload})
                if not result["ok"]:
                    print(f"⚠️ Failed to add {card_name}: HTTP {result['status']}")
                    failed_items.append({
                        "card": card_name,
                        "sku": sku,
                        "reason": f"HTTP {result['status']} (Likely dead listing or out of stock)"
                    })
            except Exception as e:
                print(f"❌ Connection error while adding {card_name}: {str(e)}")
                failed_items.append({
                    "card": card_name,
                    "sku": sku,
                    "reason": f"Script Exception: {str(e)}"
                })

        print("\nAll items transferred. Refreshing your cart interface...")
        time.sleep(1)
        page.reload(wait_until="load")

        # 5. Print out the final operations summary report
        print("\n" + "="*60)
        print("📊 EXECUTION SUMMARY")
        print("="*60)
        
        if failed_items:
            print(f"⚠️ Warning: {len(failed_items)} item(s) could not be automatically added.")
            print("Please search and add the following cards manually:")
            print("-" * 60)
            for idx, failed in enumerate(failed_items, 1):
                print(f"  [{idx}] Card: {failed['card']}")
                if failed['sku']:
                    print(f"      SKU ID: {failed['sku']}")
                print(f"      Reason: {failed['reason']}")
                print("-" * 60)
        else:
            print("✅ Perfect Run! All items successfully moved to your account.")
            
        print("="*60)
        
        # 6. Save the state immediately while the browser is guaranteed to be open
        try:
            context.storage_state(path="tcgplayer_cookies.json")
            print("\n💾 Session cookies successfully exported to tcgplayer_cookies.json")
        except Exception as e:
            print(f"\n⚠️ Could not export cookies automatically: {e}")

        print("\nPress [ENTER] in this terminal when you are ready to close the program...")
        input()
        
        context.storage_state(path="tcgplayer_cookies.json")
        return "tcgplayer_cookies.json"
