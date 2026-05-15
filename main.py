from playwright.sync_api import sync_playwright, expect
from playwright_stealth.stealth import Stealth
import questionary, re, time, sys, os, subprocess
from urllib.parse import parse_qs, urlparse
import crossfiledialog
import optimizer
import cart_create
from rich.progress import track
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def main():
    while True:
        print("==================================")
        print("Welcome to the TCGPlayer Scraper!")
        print("==================================")
        print(".\n.\n.\n")
        print("Gathering a list of TCG Games...")

        # ======================================================================
        # Stage 1: Navigate to Categories Page and collect Games list
        # ======================================================================
        game_data = {}
        categories_data = fetch_categories()

        # Cleaning to just game name, id
        for item in categories_data:
            game_data[item.get("productLineName")] = item.get("productLineId")
        game_data = dict(sorted(game_data.items()))
        # Printing output
        for item, i in zip(game_data, range(len(game_data))):
            print(f"{i+1}. {item}")

        # User input for requested game
        game_rq = {}
        game_rq = usr_game_input(game_data, "Please choose which game you'd like to scrape: \
                               \n You can type 'restart' to go back to the beginning. \
                               \n Please type 'exit' to leave TCGScraper!")
        if game_rq == "restart":
            continue
        elif game_rq == "exit":
            break

        print(f"\n\nYou chose game {next(iter(game_rq))}, Id #: {next(iter(game_rq.values()))}. Great choice!\n\n")

        # ======================================================================
        # Stage 2: Navigate to Price guide page and collect set list
        # ======================================================================
        set_data = {}
        set_data_clean = {}
        set_data = fetch_sets(next(iter(game_rq.values())))
        if isinstance(set_data, dict):
            set_data = set_data.get("results", [])
        for item in set_data:
            set_data_clean[item.get("name")] = item.get("setNameId")
        print(f"Visiting the 'Price Guide' page for {next(iter(game_rq))}!")
        # ======================================================================
        # Stage 3: Ask user if they want to see the list or type for autocomplete
        # Once selected, fix URL and ask what scraping type they want
        # ======================================================================
        # Forces user to choose, list or restart. Prevents bad input
        set_rq = usr_set_input(set_data_clean, "Please choose which set you'd like to scrape: \
                               \n You can type 'list to see the full list or 'restart' to go back to the beginning. \
                               \n Please type 'exit' to leave TCGScraper!")
        if set_rq == "restart":
            continue
        elif set_rq == "exit":
            break
        print(f"You chose set: {next(iter(set_rq))}, ID #: {next(iter(set_rq.values()))}. Great choice!")

        # ======================================================================
        # Stage 4: Navigate to Price guide page for set and scrape card, url data
        # ======================================================================
        print("Gathering all cards and their product pages in your desired set \n \
            This might take a minute!")
        
        card_data = {}
        card_data_clean = {}
        card_names = []
        product_ids = []

        card_data = fetch_cards(next(iter(set_rq.values())))
        if isinstance(card_data, dict):
            card_data = card_data.get("results", [])
        for item in card_data:
            card_data_clean[item.get("productName")] = item.get("productID")
        # print(card_data_clean)    # Debug
        card_names = list(card_data_clean)
        product_ids = list(card_data_clean.values())
        
        if not card_names:
            print("No cards found in this set. Please choose another set.")
            continue
        # Stage 5: Do logic and some more user input based on previous selection
        # ======================================================================
        # Initial ask on scraping method
        opts = ["1. Inclusive (type a list of card numbers you want data on)", "2. Exclusive (you want the whole set except a few card numbers)", "3. All Cards Please!"]
        scrape_choice = questionary.select(
            "Please Choose an option for how you'd like to scrape your card data",
            choices = opts
        ).ask()

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
            product_id_list = product_ids
            
            # Creating proper list of card names/urls/ids
            for card in cards_exclude:
                i = card_names.index(card)
                card_list.pop(i)
                product_id_list.pop(i)
        # Basically do nothing beceause user wants whole list    
        else:
            card_list = card_names
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
        max_workers = min(8, len(product_id_list)) if product_id_list else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_card = {
                executor.submit(fetch_listings, product_id, max_listings): (product_id, card_name)
                for product_id, card_name in zip(product_id_list, card_list)
            }

            for future in track(as_completed(future_to_card), description="Scraping cards...", total=len(future_to_card)):
                product_id, card_name = future_to_card[future]
                print(f"Processing: {card_name} (ID: {product_id})...")
                try:
                    raw_listings = future.result()
                except Exception as exc:
                    print(f"Error fetching listings for {card_name} ({product_id}): {exc}")
                    raw_listings = []

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

# Fetches list of games (product lines) from the Search API
def fetch_categories():
    url = "https://mp-search-api.tcgplayer.com/v1/search/productLines"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }

    with sync_playwright() as p:
        request_context = p.request.new_context()
        
        response = request_context.get(url, headers=headers)
        
        if not response.ok:
            print(f"Failed to fetch categories: {response.status}")
            return []

        # The API returns a list of objects: [{"productLineId": 1, "productLineName": "Magic...", ...}]
        return response.json()

# Fetches list of active sets from the Search API 
def fetch_sets(gameID):
    url = f"https://mpapi.tcgplayer.com/v2/Catalog/SetNames?categoryId={gameID}&active=true&mpfev=5154"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }

    with sync_playwright() as p:
        request_context = p.request.new_context()
        
        response = request_context.get(url, headers=headers)
        
        if not response.ok:
            print(f"Failed to fetch sets: {response.status}")
            return []

        data = response.json()
        if isinstance(data, dict):
            return data.get("results", [])
        return data

# Fetches list of cards from set requested over API
def fetch_cards(setID):
    url = f"https://infinite-api.tcgplayer.com/priceguide/set/{setID}/cards/?rows=5000"
    print(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }

    with sync_playwright() as p:
        request_context = p.request.new_context()
        
        response = request_context.get(url, headers=headers)
        
        if not response.ok:
            print(f"Failed to fetch cards: {response.status}")
            return []

        data = response.json()
        if isinstance(data, dict):
            return data.get("result", data.get("results", []))
        return data

# New API call version of getting card listing data
def fetch_listings(product_id, max_listings=None, session=None):
    # The API endpoint identified in the HAR file
    url = f"https://mp-search-api.tcgplayer.com/v1/product/{product_id}/listings"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0"
    }

    all_listings = []
    offset = 0
    size = 50 if not max_listings else min(50, max_listings)

    if session is None:
        session = requests.Session()
        close_session = True
    else:
        close_session = False

    try:
        while True:
            if max_listings and len(all_listings) >= max_listings:
                break

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

            print(f"Fetching listings {offset} to {offset + size} for product {product_id}...")
            response = session.post(url, headers=headers, json=payload, timeout=15)

            if not response.ok:
                print(f"Failed to fetch: {response.status_code} {response.text}")
                break

            data = response.json()
            if "results" not in data or not data["results"]:
                break

            result_set = data["results"][0]
            listings = result_set.get("results", [])
            if not listings:
                break

            if max_listings:
                listings_to_add = listings[: max_listings - len(all_listings)]
                all_listings.extend(listings_to_add)
            else:
                all_listings.extend(listings)

            if len(listings) < size:
                break

            offset += size
    finally:
        if close_session:
            session.close()

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

# Function to display a passed list and prompt and return user input
def usr_game_input(game_labels, prompt):    
    while True:
        game_rq = questionary.autocomplete(
            prompt,
            choices = list(game_labels)
        ).ask()

        # Gives option to restart (i.e. select another game)
        if game_rq.lower() == "restart":
            return "restart"
        # Gives option to exit
        elif game_rq.lower() == "exit":
            return "exit"
        # Prevents bad/empty input
        elif game_rq == "" or (game_rq not in game_labels):
            print("You must choose a game, please type your desired game or type restart to start over")
        elif game_rq in list(game_labels):
            out = {}
            out[game_rq] = game_labels[game_rq]
            return out

# Function to display passed list and allow user to continue to add to it until 'done'
def usr_card_input(card_names, prompt):
    done = 0
    cardlist = []
    while not done:
        if card_names:
            temp = questionary.autocomplete(
                prompt,
                choices = card_names
            ).ask()
        else:
            temp = questionary.text(prompt).ask()
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
def usr_set_input(set_data_clean, prompt):    
    while True:
        set_rq = questionary.autocomplete(
            prompt,
            choices = list(set_data_clean)
        ).ask()

        # Gives option to list all sets
        if set_rq.lower() == "list":
        # Printing resulting numerical set list
            for key, i in zip(set_data_clean, range(len(set_data_clean))):
                print(f"{i+1}. {key}")
            continue
        # Gives option to restart (i.e. select another game)
        elif set_rq.lower() == "restart":
            return "restart"
        # Gives option to exit
        elif set_rq.lower() == "exit":
            return "exit"
        # Prevents bad/empty input
        elif set_rq == "" or (set_rq not in set_data_clean):
            print("You must choose a set, please type your desired set or type restart to start over")
        elif set_rq in list(set_data_clean):
            out = {}
            out[set_rq] = set_data_clean[set_rq]
            return out

if __name__ == "__main__":
    main()