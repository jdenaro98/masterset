from playwright.sync_api import sync_playwright, expect
from playwright_stealth.stealth import Stealth
import questionary, re, time, sys, os, subprocess
from urllib.parse import parse_qs, urlparse
import crossfiledialog
import optimizer
import cart_create
from rich.progress import track
import time

def main():
    while True:
        with sync_playwright() as pw:
            URL = "https://www.tcgplayer.com/categories"
            titles = []
            urls = []

            print("==================================")
            print("Welcome to the TCGPlayer Scraper!")
            print("==================================")
            print(".\n.\n.\n")
            print("Gathering a list of TCG Games...")

            # ======================================================================
            # Stage 1: Navigate to Categories Page and collect Games list
            # ======================================================================
            browser = pw.chromium.launch(headless=True, args=["--window-size=640,640"])
            page = browser.new_page()
            stealth_config = Stealth()
            stealth_config.apply_stealth_sync(page)
            page.goto(URL)
            page.wait_for_load_state("networkidle")

            # Searching for only the games list container
            games = page.locator(".site-map.grouping > .grouping").first
            for link in games.get_by_test_id("base-link").all():
                titles.append(link.inner_text())
                # titles.sort() # unnecessary for now
                urls.append(link.get_attribute("href"))
                # print(data)   # Debug

            # Printing resulting numerical game list
            i = 1
            for title in titles:
                print("{}. {}".format(i, title))
                i+=1 

            # User input for requested game
            game_rqn = int(input("Please choose which game you'd like to scrape: "))
            game_rq = titles[game_rqn-1]
            url_rq = urls[game_rqn-1]
            url_rq = url_rq.lower()
            print("You chose game {}, {}. Great choice!".format(game_rqn, game_rq))
            print("Visiting the 'Price Guide' page for {}!".format(game_rq))
            PG_URL = f"https://www.tcgplayer.com{url_rq}/price-guides"

            # ======================================================================
            # Stage 2: Navigate to Price guide page and collect set list
            # ======================================================================
            page.goto(PG_URL)
            page.wait_for_load_state("networkidle")

            dd = page.get_by_placeholder("Select a Set")
            dd_list = dd.get_attribute("aria-controls")
            set_labels = [item.get_attribute("aria-label") for item in page.locator(f"#{dd_list} li").all()]   

            browser.close()

        # ======================================================================
        # Stage 3: Ask user if they want to see the list or type for autocomplete
        # Once selected, fix URL and ask what scraping type they want
        # ======================================================================
    
        # Forces user to choose, list or restart. Prevents bad input
        set_rq = ""
        set_rq = usr_set_input(set_labels, "Please choose which set you'd like to scrape: \
                               \n You can type 'list to see the full list or 'restart' to go back to the beginning. \
                               \n Please type 'exit' to leave TCGScraper!")
        if set_rq == "restart":
            continue
        elif set_rq == "exit":
            break
        print("You chose set: {}. Great choice!".format(set_rq))
            
        # print("Visiting the 'Price Guide' page for set {}!".format(set_rq))
        set_rqf = set_rq
        set_rqf = set_rqf.replace(":", "")
        set_rqf = set_rqf.replace(" ", "-")
        set_rqf = set_rqf.lower()
        SET_URL = f"https://www.tcgplayer.com{url_rq}/price-guides/{set_rqf}"

        # ======================================================================
        # Stage 4: Navigate to Price guide page for set and scrape card, url data
        # ======================================================================
        with sync_playwright() as pw:
            card_names = []
            card_urls = []
            product_ids = []
            browser = pw.chromium.launch(headless=True, args=["--window-size=640,640"])
            page = browser.new_page()
            stealth_config = Stealth()
            stealth_config.apply_stealth_sync(page)
            page.goto(SET_URL)
            page.wait_for_load_state("networkidle")

            page.get_by_label("Sort Number column by ascending").click()
            page.wait_for_load_state("networkidle")

            print("Gathering all cards and their product pages in your desired set \n \
                This might take a minute!")
            
            product_links = page.locator("tbody.tcg-table-body a.pdp-url")
            for i in range(product_links.count()):
                link = product_links.nth(i)
                card_names.append(link.inner_text().strip())
                # titles.sort() # unnecessary for now
                url = link.get_attribute("href")
                match = re.search(r'/product/(\d+)', url)
                if match:
                    product_ids.append(int(match.group(1)))
                card_urls.append(url)
                # print(data)   # Debug

            # page.pause()      # Debug
            browser.close()

        # ======================================================================
        # Stage 5: Do logic and some more user input based on previous selection
        # ======================================================================
        # Initial ask on scraping method
        opts = ["1. Inclusive (type a list of card numbers you want data on)", "2. Exclusive (you want the whole set except a few card numbers)", "3. All Cards Please!"]
        scrape_choice = questionary.select(
            "Please Choose an option for how you'd like to scrape your card data",
            choices = opts
        ).ask()

        url_list = []
        card_list = []
        product_id_list = []
        # Prompt which cards and create short list of desired cards
        # Eventaully make it even fanci and allow file uploading (don't know what format)
        if scrape_choice == opts[0]:
            prompt = "Please search for and enter the cards you'd like to scrape. \
                \n Type 'done' to complete your list. \
                \n Type 'list' to show your current list \
                \n Type 'full' to see the full card list \
                \n Type 'load' to load a file of cards you've already selected \
                \n Type 'save' to save a file of cards you've already selected"
            card_list = usr_card_input(card_names, prompt)

            # Creating proper list of card names/urls/ids
            for card in card_list:
                i = card_names.index(card)
                url_list.append(card_urls[i])
                product_id_list.append(product_ids[i])

        # Prompt which cards and create short(er) list with prompted cards removed
        # Eventually make fancy as above
        elif scrape_choice == opts[1]:
            prompt = "Please search for and enter the cards you'd like to exclude from the full set scrape \
                \n Type 'done' to complete your list. \
                \n Type 'list' to show your current list \
                \n Type 'full' to see the full card list \
                \n Type 'load' to load a file of cards you've already selected \
                \n Type 'save' to save a file of cards you've already selected"
            cards_exclude = usr_card_input(card_names, prompt)
            card_list = card_names
            url_list = card_urls
            product_id_list = product_ids
            
            # Creating proper list of card names/urls/ids
            for card in cards_exclude:
                i = card_names.index(card)
                card_list.pop(i)
                url_list.pop(i)
                product_id_list.pop(i)
        # Basically do nothing beceause user wants whole list    
        else:
            card_list = card_names
            url_list = card_urls
            product_id_list = product_ids

        # Final display, need to add option to restart back at the card choosing
        print("Your final card list looks like:")
        for card in card_list:
            print(card)

        # ======================================================================
        # Stage 6: Scrape data from card list
        # ======================================================================
        all_card_data = {}
        first_listing_data = []
        max_listings = 50
        for product_id, card_name in track(
            zip(product_id_list, card_list),
            description="Scraping cards...",
            total=len(card_list)
            ):
            
            print(f"Processing: {card_name} (ID: {product_id})...")
            
            raw_listings = fetch_listings(product_id, max_listings)
            cleaned_listings = extract_key_chars(raw_listings)

            all_card_data[product_id] = {
                "card_info": {
                    "name": card_name,
                    "total_active_listings": len(cleaned_listings)
                },
                "market_listings": cleaned_listings
            }

        # Create listing of just first listing for each card to show user before optimization
        for product_id, card_data in all_card_data.items():
            card_name = card_data["card_info"]["name"]
            listings = card_data["market_listings"]
            if listings:  # Check if there are any listings at all
                # Create a copy or a new dict with the card name included for reference
                first_entry = listings[0].copy()
                first_entry['card'] = card_name
                first_listing_data.append(first_entry)
            else:
                # Optional: Handle cards with no listings
                print(f"Note: No listings found for {card_name}, skipping in first_listing_data.")

        print_cart(first_listing_data, "\nFirst Listings:\n")

        optimized_cart = optimizer.optimize(all_card_data)

        print_cart(optimized_cart, "\nOptimized Cart:\n")
        
        if questionary.confirm("Open browser and add the optimized items to cart using Playwright?").ask():
            cookie_export_path = cart_create.create_cart(optimized_cart)
            if cookie_export_path:
                print(f"Cart cookies exported to: {cookie_export_path}")
            else:
                print("Cart creation finished, but cookie export was not completed.")

        break

###############################################################################

# New API call version of getting card listing data
def fetch_listings(product_id, max_listings=None):
    # The API endpoint identified in the HAR file
    url = f"https://mp-search-api.tcgplayer.com/v1/product/{product_id}/listings"
    
    # Headers mimicking the browser request from the HAR file
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0"
    }
    
    all_listings = []
    offset = 0
    size = 50 # Fetching 50 listings per request
    
    with sync_playwright() as p:
        # We use an APIRequestContext for direct HTTP requests without loading a full browser page
        request_context = p.request.new_context()
        
        while True:
            # Check if we've already fetched enough listings
            if max_listings and len(all_listings) >= max_listings:
                break
            
            # Payload replicated from the HAR file, dynamically updating 'from' and 'size'
            payload = {
                "filters": {
                    "term": {"sellerStatus": "Live", "channelId": 0},
                    "range": {"quantity": {"gte": 1}},
                    "exclude": {"channelExclusion": 0}
                },
                "from": offset,
                "size": size,
                "sort": {"field": "price+shipping", "order": "asc"},
                "context": {"shippingCountry": "US", "cart": {"packages": {}}},
                "aggregations": ["listingType"]
            }
            
            print(f"Fetching listings {offset} to {offset + size}...")
            response = request_context.post(url, headers=headers, data=payload)
            
            if not response.ok:
                print(f"Failed to fetch: {response.status} {response.status_text}")
                break
                
            data = response.json()
            
            # Defensive check to ensure the expected JSON structure exists
            if "results" not in data or not data["results"]:
                break
                
            # The listings are nested inside the first result object
            result_set = data["results"][0]
            listings = result_set.get("results", [])
            
            if not listings:
                break
            
            # Only add listings up to the max_listings limit
            if max_listings:
                listings_to_add = listings[:max_listings - len(all_listings)]
                all_listings.extend(listings_to_add)
            else:
                all_listings.extend(listings)
            
            # If the API returns fewer listings than our size limit, we've reached the last page
            if len(listings) < size:
                break
                
            # Increment the offset for the next page
            offset += size
            
    return all_listings

# Extracts key (needed) characteristics from each listing on cards
def extract_key_chars(raw_listings):
    """Extracts and formats the relevant fields from the raw API response.
        Can always come back and add more fields as desired when implementing settings"""
    cleaned_listings = []
    for item in raw_listings:
        # Hard coded filters that I want but should be changed in the future
        # Force verified seller/gold seller
        if not (item.get("verifiedSeller") or item.get("goldSeller")):
            continue
        # Force NM/LP
        if not (item.get("condition") == "Near Mint" or item.get("condition") == "Lightly Played"):
            continue
        # Skip listings that have alternate language listed
        if item.get("customData", {}).get("title"):
            titledata = ""
            titledata = item.get("customData", {}).get("title")

            if item.get("language") == "English":
                if re.search(r'(Japanese|Chinese|Korean|Spanish|French|German|Italian|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)', titledata, re.I):
                    print("Skipping non-English listing")
                    continue
            elif item.get("language") == "Japanese":
                if re.search(r'(English|Chinese|Korean|Spanish|French|German|Italian|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)', titledata, re.I):
                    print("Skipping non-Japanese listing")
                    continue
            else: pass

        if (item.get("sellerShippingPrice") == 0 and item.get("shippingPrice") > 0):
            sd = True
        else:
            sd = False

        try:
            parsed_seller = {
                "price": item.get("price"),
                "shipping": item.get("shippingPrice"),
                "total": item.get("price", 0) + item.get("shippingPrice", 0),
                "shipping_deal": sd,
                "seller": item.get("sellerName"),
                "verifiedSeller": item.get("verifiedSeller"),
                "goldSeller": item.get("goldSeller"),
                "condition": item.get("condition"),
                "sku": int(item.get("productConditionId")),
                "sellerKey": item.get("sellerKey"),
                "title": item.get("customData", {}).get("title", "No Picture Linked"),
                "custom_listing_key": item.get("customData", {}).get("linkId", "No Picture Linked")
            }
        except KeyError as e:
            print(f"Missing expected field in listing: {e}")
            continue
        cleaned_listings.append(parsed_seller)
    return cleaned_listings

# Prints sructured dictionary that's sent to it (pre vs post optimization cart)
def print_cart(cart, title):
    print(title)
    sellers = {item['seller'] for item in cart if item.get('seller')}
    total_price = sum(item.get('price') or 0.0 for item in cart if item.get('price') is not None)
    total_shipping = shipping_calc(cart)
    total_cost = total_price + total_shipping
    print(f"  Unique sellers: {len(sellers)}")
    print(f"  Raw card cost: ${total_price:.2f}")
    print(f"  Shipping Cost: ${total_shipping:.2f}")
    print(f"  Estimated subtotal: ${total_cost:.2f}\n")
    for item in cart:
        seller = item.get('seller') or 'N/A'
        condition = item.get('condition') or 'N/A'
        price = item.get('price') if item.get('price') is not None else 0.0
        shipping = item.get('shipping') if item.get('shipping') is not None else 0.0
        shipping_deal = item.get('shipping_deal') or 'N/A'
        total = item.get('total') if item.get('total') is not None else 0.0
        url = item.get('card_url') or 'N/A'
        card = item.get('card') or 'N/A'
        # seller_id = item.get('seller_id') or 'N/A'
        print(f"  - {card} | {seller} | {condition} | ${price:.2f} | ${shipping:.2f} | {shipping_deal} | ${total:.2f} | {url}")

# Shipping price logic on per-seller basis
def shipping_calc(cart):
    """
    Calculates total shipping cost based on seller-specific thresholds.
    If 'shipping_deal' is True and the sum of card prices from a specific 
    seller is >= $5.00, shipping for that seller becomes $0.00.
    """
    seller_totals = {}
    total_shipping = 0.0
    FREE_SHIPPING_THRESHOLD = 5.00

    # 1. Aggregate card prices and shipping per seller
    # We use seller_id as the primary key to ensure we don't mix up 
    # different sellers with the same/similar names.
    for item in cart:
        sid = item.get('seller_id') or item.get('seller')
        if sid not in seller_totals:
            seller_totals[sid] = {
                'items_price': 0.0,
                'shipping_cost': 0.0,
                'has_deal': False
            }
        
        price_val = item.get('price')
        seller_totals[sid]['items_price'] += price_val if price_val is not None else 0.0
        
        # We assume the shipping cost is consistent across items from the same seller 
        # for a single order, so we track the highest shipping fee encountered for that seller.
        ship_val = item.get('shipping') or 0.0
        if ship_val > seller_totals[sid]['shipping_cost']:
            seller_totals[sid]['shipping_cost'] = ship_val
            
        # If any item from this seller indicates a shipping deal exists
        if item.get('shipping_deal') or False:
            seller_totals[sid]['has_deal'] = True

    # 2. Calculate the final shipping cost based on the $5 threshold
    for sid, data in seller_totals.items():
        if data['has_deal'] and data['items_price'] >= FREE_SHIPPING_THRESHOLD:
            # Threshold met, shipping is free for this seller
            continue
        else:
            # Threshold not met or no deal offered, add the seller's shipping fee
            total_shipping += data['shipping_cost']

    return round(total_shipping, 2)

# Prompts user with standard load/save dialog
def _centered_file_dialog(dialog_type, **options):
    """Cross-platform native file picker wrapper."""
    if dialog_type == 'open':
        return crossfiledialog.open_file(title=options.get('title', 'Select a File'))
    else:
        return crossfiledialog.save_file(title=options.get('title', 'Choose where to save your list'))

# Function to display passed list and allow user to continue to add to it until 'done'
def usr_card_input(card_names, prompt):
    done = 0
    cardlist = []
    while not done:
        temp = questionary.autocomplete(
            prompt,
            choices = card_names
        ).ask()
        if temp.lower() == 'done':
            done = 1
        elif temp.lower() == 'list':
            print("=============================")
            for card in cardlist:
                print(card)
            print("=============================")
        elif temp.lower() == 'full':
            print("=============================")
            for card in card_names:
                print(card)
            print("=============================")
        elif temp.lower() == 'load':
            # Zeroes the list in case user previously added some
            cardlist = []
            file_path = _centered_file_dialog(
                'open',
                title="Select a File",
                filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
            )

            # Open the file and read lines into a list
            if file_path:
                with open(file_path, 'r') as file:
                    cardlist = [line.strip() for line in file.readlines()]
        elif temp.lower() == 'save':
            file_path = _centered_file_dialog(
                'save',
                defaultextension=".txt",
                filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
                title="Choose where to save your list"
            )

            # Only proceed if user doesn't hit cancel
            if file_path:
                with open(file_path, 'w') as file:
                    for item in cardlist:
                        file.write(f"{item}\n")
                    print(f"Successfully saved to: {file_path}")
        # elif temp.lower() == 'exit':
        #     return "exit"
        # elif temp.lower() == 'restart':
        #     return "restart"
        elif temp in card_names:
            cardlist.append(temp)
        else:
            pass
    return cardlist

# Function to display a passed list and prompt and return user input
def usr_set_input(set_labels, prompt):    
    while True:
        set_rq = questionary.autocomplete(
            prompt,
            choices = set_labels
        ).ask()

        # Gives option to list all sets
        if set_rq.lower() == "list":
        # Printing resulting numerical set list
            for i in range(len(set_labels)):
                print("{}. {}".format(i+1, set_labels[i]))
            continue
        # Gives option to restart (i.e. select another game)
        elif set_rq.lower() == "restart":
            return "restart"
        # Gives option to exit
        elif set_rq.lower() == "exit":
            return "exit"
        # Prevents bad/empty input
        elif set_rq == "" or (set_rq not in set_labels):
            print("You must choose a set, please type your desired set or type restart to start over")
        elif set_rq in set_labels:
            return set_rq

if __name__ == "__main__":
    main()