import json
import time
import requests
from playwright.sync_api import sync_playwright
from rich.progress import track


DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.tcgplayer.com",
    "Referer": "https://www.tcgplayer.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
}


def create_cart(optimized_cart):
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    create_cart_url = "https://mpgateway.tcgplayer.com/v1/cart/create/anonymouscart?mpfev=5143"
    print("Initializing new guest cart...")

    init_response = session.post(create_cart_url, data="", timeout=15)
    if not init_response.ok:
        print(f"Failed to create cart: {init_response.status_code} {init_response.text}")
        return

    cart_data = init_response.json()
    try:
        cart_key = cart_data['results'][0]['cartKey']
        print(f"Successfully created cart! Key: {cart_key}")
    except (KeyError, IndexError):
        print("Could not find cartKey in initialization response.")
        return

    with sync_playwright() as pw:
        user_data_dir = "./user_data" # This creates a folder to save your login/cookies
        context = pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=["--window-size=1280,720"]
        )

        page = context.pages[0] if context.pages else context.new_page()
        context.add_cookies([{
            'name': 'StoreCart_PRODUCTION',
            'value': f'CK={cart_key}&Ignore=false',
            'domain': '.tcgplayer.com',
            'path': '/'
        }])

        # Navigate after cookie injection so the cart is available immediately.
        page.goto("https://www.tcgplayer.com/", wait_until="networkidle")

        for item in track(optimized_cart, description="Adding Items to Cart ...", total=len(optimized_cart)):
            sku = item.get('sku')
            seller_key = item.get('sellerKey')
            custom_listing_key = item.get('custom_listing_key')

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

            print(f"Adding listing for {item.get('card', 'unknown card')}.")
            add_response = session.post(add_url, json=payload, timeout=15)

            if add_response.ok:
                print(f"Added {item.get('card', 'unknown card')} successfully.")
            else:
                print(f"Failed to add {item.get('card', 'unknown card')}: {add_response.status_code} {add_response.text}")

        print("\nAll items added. Redirecting to your cart...")
        time.sleep(1)
        page.goto("https://www.tcgplayer.com/cart")

        print(">>> Press Enter in the terminal to save session and close...")
        input()

        context.storage_state(path="tcgplayer_cookies.json")
        return "tcgplayer_cookies.json"

if __name__ == "__main__":
    create_cart()