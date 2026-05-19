import json
import time
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth
from rich.progress import track


def create_cart(optimized_cart):
    if not optimized_cart:
        print("No items provided to create a cart.")
        return

    print("Launching browser...")
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
                "--disable-features=TranslateUI",
                # "--force-devices-scale-factor=1",
                "--disable-gpu"     # Helps with laggy rendering on mac
            ]
        )
        context = browser.new_context()
        stealth.apply_stealth_sync(context)
        context.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        page = context.new_page()
        page.set_default_navigation_timeout(60000)

        # 1. Visit homepage to establish TCG_VisitorKey and other session cookies
        print("Initializing TCGPlayer session...")
        page.goto("https://www.tcgplayer.com/", wait_until="domcontentloaded")
        time.sleep(2)

        # 2. Create an anonymous cart — no login required
        print("Creating cart...")
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

        if not create_result['ok']:
            print(f"❌ Failed to create cart: HTTP {create_result['status']}: {create_result['text']}")
            return

        cart_data = json.loads(create_result['text'])
        cart_key = cart_data['results'][0]['cartKey']
        print(f"✅ Cart initialized: {cart_key}")

        # 3. Set StoreCart_PRODUCTION cookie so the cart page renders this cart
        #    TCGPlayer's SPA sets this client-side after cart creation; we do it explicitly.
        context.add_cookies([{
            "name": "StoreCart_PRODUCTION",
            "value": f"CK={cart_key}&Ignore=false",
            "domain": ".tcgplayer.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax"
        }])

        # 4. Add all items to the cart
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

        for item in track(optimized_cart, description="Adding items to cart...", total=len(optimized_cart)):
            sku = item.get('sku')
            seller_key = item.get('sellerKey')
            custom_listing_key = item.get('custom_listing_key')
            card_name = item.get('card', 'unknown card')
            price = item.get('price', 0)

            # Items with no valid listing (optimizer couldn't find one) are skipped
            if not sku and custom_listing_key in (None, "No Picture Linked", "N/A"):
                failed_items.append({
                    "card": card_name,
                    "sku": None,
                    "reason": "No listing found during optimization"
                })
                continue

            if custom_listing_key and custom_listing_key not in ("No Picture Linked", "N/A"):
                add_url = f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}/listo/add?mpfev=5143"
                payload = {
                    "customListingKey": custom_listing_key,
                    "priceAtAdd": price,
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
                    "price": price,
                    "isDirect": False,
                    "countryCode": "US"
                }

            try:
                result = page.evaluate(browser_fetch_js, {"url": add_url, "payload": payload})
                if not result['ok']:
                    print(f"\n⚠️  Failed to add {card_name}: HTTP {result['status']}")
                    failed_items.append({
                        "card": card_name,
                        "sku": sku,
                        "reason": f"HTTP {result['status']} (dead listing or out of stock)"
                    })
            except Exception as e:
                print(f"\n❌ Error adding {card_name}: {e}")
                failed_items.append({
                    "card": card_name,
                    "sku": sku,
                    "reason": f"Script error: {e}"
                })

        # 5. Navigate to cart page — cookie is already set, items will render immediately
        print("\nOpening cart...")
        page.goto("https://www.tcgplayer.com/cart", wait_until="load")
        time.sleep(1)
        page.reload(wait_until="load")

        # 6. Print summary
        print("\n" + "=" * 60)
        print("📊 EXECUTION SUMMARY")
        print("=" * 60)

        if failed_items:
            print(f"⚠️  {len(failed_items)} item(s) could not be added automatically.")
            print("Please search and add the following cards manually:")
            print("-" * 60)
            for idx, f in enumerate(failed_items, 1):
                print(f"  [{idx}] Card: {f['card']}")
                if f['sku']:
                    print(f"       SKU: {f['sku']}")
                print(f"       Reason: {f['reason']}")
                print("-" * 60)
        else:
            print("✅ Perfect run! All items added successfully.")

        print("=" * 60)
        print("\n👉 Your cart is ready in the browser above.")
        print("   Log in to your TCGPlayer account to save the cart, then proceed to checkout.")
        print("   The cart will be preserved through the login — no items will be lost.")
        print()
        input("Press [ENTER] when you are done...")

        try:
            context.storage_state(path="tcgplayer_cookies.json")
            print("💾 Session saved to tcgplayer_cookies.json")
        except Exception as e:
            print(f"⚠️  Could not save cookies: {e}")

        return "tcgplayer_cookies.json"
