import json
import time
from playwright.sync_api import sync_playwright

def create_cart(optimized_cart):
    with sync_playwright() as pw:
        user_data_dir = "./user_data" # This creates a folder to save your login/cookies
        context = pw.chromium.launch_persistent_context(
            user_data_dir, 
            headless=False, 
            args=["--window-size=1280,720"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.tcgplayer.com/", wait_until="networkidle")

        # 1: Create the Anonymous Cart
        create_cart_url = "https://mpgateway.tcgplayer.com/v1/cart/create/anonymouscart?mpfev=5143"
        print("Initializing new guest cart...")

        init_script = f"""
            fetch("{create_cart_url}", {{
                method: "POST",
                headers: {{ "Content-Length": "0" }}
            }}).then(res => res.json())
        """
        cart_data = page.evaluate(init_script)
        
        # 2: Extract the cartKey from the JSON response 
        try:
            cart_key = cart_data['results'][0]['cartKey']
            print(f"Successfully created cart! Key: {cart_key}")
        except (KeyError, IndexError):
            print("Could not find cartKey in initialization response.")
            return

        context.add_cookies([{
            'name': 'StoreCart_PRODUCTION',
            'value': f'CK={cart_key}&Ignore=false',
            'domain': '.tcgplayer.com',
            'path': '/'
        }])

        # 3: Add all items to cart using new cartKey
        for item in optimized_cart:
            listing_id = item.get('listing_id')
            seller_id = item.get('seller_id')
            if not listing_id or listing_id == "N/A":
                continue
            
            add_url = f"https://mpgateway.tcgplayer.com/v1/cart/{cart_key}/item/add?mpfev=5143"
            
            # This payload matches the successful POST in 'add to cart_2.har'
            payload = {
                "sku": int(listing_id),
                "sellerKey": seller_id or "",        # The API accepts an empty string if not specified
                "channelId": 0,         # 0 is the default channel for the main marketplace
                "requestedQuantity": 1, # Note the specific field name 'requestedQuantity'
                "price": 0,             # Can be 0; the server validates current price on the backend
                "isDirect": False,
                "countryCode": "US"
            }

            print(f"Adding listing for {item['card']}, {listing_id}.")

            add_script = f"""
                fetch("{add_url}", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({json.dumps(payload)})
                }}).then(res => res.ok)
            """
            success = page.evaluate(add_script)

            if success:
                print(f"Added {listing_id} successfully.")
            else:
                print(f"Failed to add {item['card']}, {listing_id}.")

        # 4: Final Sync and View
        print("\nAll items added. Redirecting to your cart...")
        time.sleep(1) # Brief pause for server-side processing
        page.goto("https://www.tcgplayer.com/cart")
        
        print(">>> Press Enter in the terminal to save session and close...")
        input()
        
        context.storage_state(path="tcgplayer_cookies.json")
        return "tcgplayer_cookies.json"

if __name__ == "__main__":
    create_cart()