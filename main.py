from playwright.sync_api import sync_playwright, expect
from playwright_stealth.stealth import Stealth
import questionary, re, time, sys, os, subprocess, curses
from urllib.parse import parse_qs, urlparse
import crossfiledialog
import optimizer
import cart_create
import theme
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def main():

    theme.initialize()

    theme.header("================================================================================")
    theme.header("Welcome to the TCGScraper!")
    theme.header("================================================================================")
    theme.muted(".\n.\n.\n")
    theme.info("Gathering a list of TCG Games...")

    game_data = {}
    categories_data = fetch_categories()
    for item in categories_data:
        game_data[item.get("productLineName")] = item.get("productLineId")
    game_data = dict(sorted(game_data.items()))

    pending_selections = []

    while True:
        selection = _collect_selection(game_data, has_prior=bool(pending_selections))
        if selection == "exit":
            return
        if selection == "restart":
            pending_selections.clear()
            continue
        if selection == "done":
            break

        pending_selections.append(selection)

        if not questionary.confirm("Add cards from another set to optimize together?", style=theme.qs_style()).ask():
            break

    # Build flat task list: (product_id, "Card Name [Set Name]")
    tasks = [
        (product_id, f"{card_name} [{selection['set_name']}]")
        for selection in pending_selections
        for product_id, card_name in zip(selection["product_id_list"], selection["card_list"])
    ]

    if not tasks:
        theme.muted("No cards selected. Exiting.")
        return

    all_card_data = {}
    first_listing_data = []
    max_listings = 50
    max_workers = min(8, len(tasks))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_card = {
            executor.submit(fetch_listings, product_id, max_listings): (product_id, display_name)
            for product_id, display_name in tasks
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=theme.console,
        ) as progress:
            task_id = progress.add_task("Scraping cards...", total=len(future_to_card))
            for future in as_completed(future_to_card):
                product_id, display_name = future_to_card[future]
                theme.info(f"Processing: {display_name} (ID: {product_id})...")
                try:
                    raw_listings = future.result()
                except Exception as exc:
                    theme.muted(f"Error fetching listings for {display_name} ({product_id}): {exc}")
                    raw_listings = []

                cleaned_listings = _extract_key_chars(raw_listings)
                all_card_data[product_id] = {
                    "card_info": {
                        "name": display_name,
                        "total_active_listings": len(cleaned_listings)
                    },
                    "market_listings": cleaned_listings
                }
                progress.advance(task_id)

    # Gathering first listing of each card data
    for product_id, card_data in all_card_data.items():
        card_name = card_data["card_info"]["name"]
        listings = card_data["market_listings"]
        if listings:
            first_entry = listings[0].copy()
            first_entry['card'] = card_name
            first_listing_data.append(first_entry)
        else:
            theme.muted(f"Note: No listings found for {card_name}, skipping in first_listing_data.")

    # TODO: Eventually run multiple permutations so the user can live see
    # changes in total/shipping cost if they don't care about condition, or
    # having verified sellers
    optimized_cart = optimizer.optimize(all_card_data)
    _print_carts_side_by_side(first_listing_data, "\nFirst Listings:\n", optimized_cart, "\nOptimized Cart:\n")

    if questionary.confirm("Open browser and add the optimized items to cart using Playwright?", style=theme.qs_style()).ask():
        cookie_export_path = cart_create.create_cart(optimized_cart)
        if cookie_export_path:
            theme.info(f"Cart cookies exported to: {cookie_export_path}")
        else:
            theme.muted("Cart creation finished, but cookie export was not completed.")

################################################################################
# Helper Functions
def _collect_selection(game_data, has_prior=False):
    """Runs game→set→card selection for one set slot.
    Returns {"set_name", "card_list", "product_id_list"}, "exit", or "done".
    """
    while True:
        done_hint = "\n You can type 'done' to skip to optimization with your current selections." if has_prior else ""
        game_rq = _usr_game_input(
            game_data,
            "Please choose which game you'd like to scrape: "
            "\n You can type 'restart' to go back to the beginning. "
            "\n Please type 'exit' to leave TCGScraper!"
            + done_hint,
            has_prior=has_prior
        )
        if game_rq == "restart":
            return "restart"
        elif game_rq == "exit":
            return "exit"
        elif game_rq == "done":
            return "done"

        theme.info(f"\nYou chose game {next(iter(game_rq))}, Id #: {next(iter(game_rq.values()))}. Great choice!\n")

        set_data_clean = {}
        set_data = fetch_sets(next(iter(game_rq.values())))
        if isinstance(set_data, dict):
            set_data = set_data.get("results", [])
        for item in set_data:
            set_data_clean[item.get("name")] = item.get("setNameId")
        theme.info(f"Visiting the 'Price Guide' page for {next(iter(game_rq))}!")

        set_rq = _usr_set_input(
            set_data_clean,
            "Please choose which set you'd like to scrape: "
            "\n You can type 'list' to see the full list or 'restart' to go back to the beginning. "
            "\n Please type 'exit' to leave TCGScraper!"
        )
        if set_rq == "restart":
            continue
        elif set_rq == "exit":
            return "exit"

        set_name = next(iter(set_rq))
        theme.info(f"You chose set: {set_name}, ID #: {next(iter(set_rq.values()))}. Great choice!")

        theme.info("Gathering all cards and their product pages in your desired set\n    This might take a minute!")

        card_data_clean = {}
        card_data = fetch_cards(next(iter(set_rq.values())), next(iter(game_rq.values())))
        if isinstance(card_data, dict):
            card_data = card_data.get("results", [])
        for item in card_data:
            card_data_clean[item.get("productName")] = item.get("productID")

        card_names = list(card_data_clean)
        product_ids = list(card_data_clean.values())

        if not card_names:
            theme.muted("No cards found in this set. Please choose another set.")
            continue

        opts = [
            "1. Inclusive (type a list of card numbers you want data on)",
            "2. Exclusive (you want the whole set except a few card numbers)",
            "3. All Cards Please!"
        ]
        scrape_choice = questionary.select(
            "Please Choose an option for how you'd like to scrape your card data",
            choices=opts,
            style=theme.qs_style()
        ).ask()

        card_list = []
        product_id_list = []

        if scrape_choice == opts[0]:
            prompt = (
                "Please search for and enter the cards you'd like to scrape."
                "\n Type 'done' to complete your list."
                "\n Type 'list' to show your current list"
                "\n Type 'full' to see the full card list"
                "\n Type 'load' to load a file of cards you've already selected"
                "\n Type 'save' to save a file of cards you've already selected"
            )
            card_list = _usr_card_input(card_names, prompt)
            for card in card_list:
                i = card_names.index(card)
                product_id_list.append(product_ids[i])

        elif scrape_choice == opts[1]:
            prompt = (
                "Please search for and enter the cards you'd like to exclude from the full set scrape."
                "\n Type 'done' to complete your list."
                "\n Type 'list' to show your current list"
                "\n Type 'full' to see the full card list"
                "\n Type 'load' to load a file of cards you've already selected"
                "\n Type 'save' to save a file of cards you've already selected"
            )
            cards_exclude = _usr_card_input(card_names, prompt)
            card_list = list(card_names)
            product_id_list = list(product_ids)
            for card in cards_exclude:
                i = card_list.index(card)
                card_list.pop(i)
                product_id_list.pop(i)

        else:
            card_list = list(card_names)
            product_id_list = list(product_ids)

        theme.header(f"\nYour final card list for [{set_name}]:")
        for card in card_list:
            theme.detail(f"  {card}")

        return {"set_name": set_name, "card_list": card_list, "product_id_list": product_id_list}

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
            theme.muted(f"Failed to fetch categories: {response.status}")
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

    for attempt in range(3):
        try:
            with sync_playwright() as p:
                request_context = p.request.new_context()
                response = request_context.get(url, headers=headers)

                if not response.ok:
                    theme.muted(f"Failed to fetch sets: {response.status}")
                    return []

                data = response.json()
                if isinstance(data, dict):
                    return data.get("results", [])
                return data
        except Exception as e:
            if attempt < 2:
                theme.muted(f"Connection error fetching sets, retrying... ({e})")
                time.sleep(2)
            else:
                theme.muted(f"Failed to fetch sets after 3 attempts: {e}")
                return []

# Fetches list of cards from set requested over API
def fetch_cards(setID, gameID):

    pdurl = f"https://mpapi.tcgplayer.com/v2/Product/ProductTypes/{gameID}/?mpfev=5154"

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
        # First get product ID types for set
        request_context = p.request.new_context()

        response = request_context.get(pdurl, headers=headers)

        data = response.json()
        pdID = None
        if isinstance(data, dict):
            results = data.get("results", [])
            pdID = next(
                (item.get("productTypeId") for item in results
                if item.get("productName") == "Cards"),
                None
            )

        if pdID is None:
            theme.muted(f"Failed to fetch productTypeId for set {setID}")
            return []

        # Then construct actual price guide url with that info
        url = f"https://infinite-api.tcgplayer.com/priceguide/set/{setID}/cards/?rows=5000&productTypeID={pdID}"

        response = request_context.get(url, headers=headers)

        if not response.ok:
            theme.muted(f"Failed to fetch cards: {response.status}")
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

            response = session.post(url, headers=headers, json=payload, timeout=15)

            if not response.ok:
                theme.muted(f"Failed to fetch: {response.status_code} {response.text}")
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
def _extract_key_chars(raw_listings):
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
                    theme.muted("Skipping non-English listing")
                    continue
            elif item.get("language") == "Japanese":
                if re.search(r'(English|Chinese|Korean|Spanish|French|German|Italian|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)', titledata, re.I):
                    theme.muted("Skipping non-Japanese listing")
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
            theme.muted(f"Missing expected field in listing: {e}")
            continue
        cleaned_listings.append(parsed_seller)
    return cleaned_listings

# Prints sructured dictionary that's sent to it (pre vs post optimization cart)
def _print_cart(cart, title):
    theme.header(title)
    sellers = {item['seller'] for item in cart if item.get('seller')}
    total_price = sum(item.get('price') or 0.0 for item in cart if \
        item.get('price') is not None)
    total_shipping = _shipping_calc(cart)
    total_cost = total_price + total_shipping
    theme.info(f"  Unique sellers: {len(sellers)}")
    theme.info(f"  Raw card cost: ${total_price:.2f}")
    theme.info(f"  Shipping Cost: ${total_shipping:.2f}")
    theme.info(f"  Estimated subtotal: ${total_cost:.2f}\n")
    # for item in cart:
    #     seller = item.get('seller') or 'N/A'
    #     condition = item.get('condition') or 'N/A'
    #     price = item.get('price') if item.get('price') is not None else 0.0
    #     shipping = item.get('shipping') if item.get('shipping') is not None else 0.0
    #     shipping_deal = item.get('shipping_deal') or 'N/A'
    #     total = item.get('total') if item.get('total') is not None else 0.0
    #     url = item.get('card_url') or 'N/A'
    #     card = item.get('card') or 'N/A'
    #     theme.detail(f"  - {card} | {seller} | {condition} | ${price:.2f} | \
    #         ${shipping:.2f} | {shipping_deal} | ${total:.2f} | {url}")

def _print_carts_side_by_side(cart1, title1, cart2, title2):
    import io
    from rich.console import Console

    ansi_re = re.compile(r'\x1b\[[^m]*m')

    def capture(cart, title):
        buf = io.StringIO()
        tmp = Console(file=buf, force_terminal=True, width=70)
        old = theme.console
        theme.console = tmp
        _print_cart(cart, title)
        theme.console = old
        return buf.getvalue().splitlines()

    lines1 = capture(cart1, title1)
    lines2 = capture(cart2, title2)

    col_w = max((len(ansi_re.sub('', l)) for l in lines1), default=0)
    n = max(len(lines1), len(lines2))
    lines1 += [''] * (n - len(lines1))
    lines2 += [''] * (n - len(lines2))

    for l1, l2 in zip(lines1, lines2):
        pad = col_w - len(ansi_re.sub('', l1))
        print(f"{l1}{' ' * pad} | {l2}")

# Shipping price logic on per-seller basis
def _shipping_calc(cart):
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

def _game_select_columns(game_labels, prompt, has_prior=False):
    games = list(game_labels.keys())
    n = len(games)
    NUM_COLS = 3
    # rows_per_col is fixed; never recomputed on resize so cursor math stays consistent
    rows_per_col = (n + NUM_COLS - 1) // NUM_COLS
    result_holder = []

    def _ui(stdscr):
        cursor = 0
        scroll_offset = 0

        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # cursor highlight

        while True:
            h, w = stdscr.getmaxyx()
            col_width = max(1, w // NUM_COLS)
            visible_rows = max(1, h - 3)

            # cursor is a flat column-major index: col = cursor // rows_per_col, row = cursor % rows_per_col
            cursor_row = cursor % rows_per_col
            if cursor_row < scroll_offset:
                scroll_offset = cursor_row
            elif cursor_row >= scroll_offset + visible_rows:
                scroll_offset = cursor_row - visible_rows + 1

            stdscr.clear()

            # Use only the first line of the prompt so \n doesn't bleed into game rows
            header = f" {prompt.splitlines()[0]}"[:w - 1]
            stdscr.addstr(0, 0, header, curses.A_BOLD)

            for row in range(visible_rows):
                actual_row = row + scroll_offset
                if actual_row >= rows_per_col:
                    break  # no items exist past the last row in any column
                for col in range(NUM_COLS):
                    idx = col * rows_per_col + actual_row
                    if idx >= n:
                        continue
                    text = games[idx]
                    max_text = col_width - 2
                    if len(text) > max_text:
                        text = text[:max_text - 1] + "~"
                    text = text.ljust(col_width - 1)
                    try:
                        if idx == cursor:
                            stdscr.addstr(row + 1, col * col_width, text, curses.color_pair(1) | curses.A_BOLD)
                        else:
                            stdscr.addstr(row + 1, col * col_width, text)
                    except curses.error:
                        pass

            scroll_hint = f"  (row {scroll_offset + 1}/{rows_per_col})" if rows_per_col > visible_rows else ""
            extra = "  R: restart  D: done" if has_prior else ""
            footer = f" Arrows: navigate  ENTER: select{extra}  ESC: exit{scroll_hint}"[:w - 1]
            try:
                stdscr.addstr(h - 1, 0, footer, curses.A_REVERSE)
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            cur_col = cursor // rows_per_col
            cur_row = cursor % rows_per_col

            if key == curses.KEY_UP:
                if cur_row > 0:
                    cursor -= 1
            elif key == curses.KEY_DOWN:
                new = cursor + 1
                if cur_row + 1 < rows_per_col and new < n:
                    cursor = new
            elif key == curses.KEY_LEFT:
                if cur_col > 0:
                    cursor -= rows_per_col
            elif key == curses.KEY_RIGHT:
                new = cursor + rows_per_col
                if cur_col + 1 < NUM_COLS and new < n:
                    cursor = new
            elif key in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                result_holder.append(games[cursor])
                break
            elif key in (ord('r'), ord('R')) and has_prior:
                confirm_msg = " Confirm restart? ENTER to confirm, ESC to cancel"[:w - 1]
                try:
                    stdscr.addstr(h - 1, 0, " " * (w - 1), curses.A_REVERSE)
                    stdscr.addstr(h - 1, 0, confirm_msg, curses.A_REVERSE | curses.A_BOLD)
                except curses.error:
                    pass
                stdscr.refresh()
                if stdscr.getch() in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                    result_holder.append('__restart__')
                    break
            elif key in (ord('d'), ord('D')) and has_prior:
                confirm_msg = " Done adding sets? ENTER to confirm, ESC to cancel"[:w - 1]
                try:
                    stdscr.addstr(h - 1, 0, " " * (w - 1), curses.A_REVERSE)
                    stdscr.addstr(h - 1, 0, confirm_msg, curses.A_REVERSE | curses.A_BOLD)
                except curses.error:
                    pass
                stdscr.refresh()
                if stdscr.getch() in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                    result_holder.append('__done__')
                    break
            elif key == 27:  # ESC — exit
                break
            elif key == curses.KEY_RESIZE:
                curses.update_lines_cols()
                stdscr.clear()

    curses.wrapper(_ui)
    return result_holder[0] if result_holder else None


# Function to display a passed list and prompt and return user input
def _usr_game_input(game_labels, prompt, has_prior=False):
    while True:
        game_rq = _game_select_columns(game_labels, prompt, has_prior=has_prior)

        if game_rq is None:
            return "exit"
        elif game_rq == '__restart__':
            subprocess.run('cls' if os.name == 'nt' else 'clear', shell=True)
            theme.header("================================================================================")
            theme.header("Restarting TCGScraper...")
            theme.header("================================================================================")
            time.sleep(1)
            return "restart"
        elif game_rq == '__done__':
            return "done"
        elif game_rq in game_labels:
            return {game_rq: game_labels[game_rq]}

def _card_select_columns(card_names, prompt):
    cards = list(card_names)
    n = len(cards)
    NUM_COLS = 3
    rows_per_col = (n + NUM_COLS - 1) // NUM_COLS
    result_holder = []

    def _ui(stdscr):
        selected = set()
        cursor = 0
        scroll_offset = 0

        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # cursor highlight
        curses.init_pair(2, curses.COLOR_GREEN, -1)                   # selected item

        while True:
            h, w = stdscr.getmaxyx()
            col_width = max(1, w // NUM_COLS)
            visible_rows = max(1, h - 3)

            # cursor is a flat column-major index: col = cursor // rows_per_col, row = cursor % rows_per_col
            cursor_row = cursor % rows_per_col
            if cursor_row < scroll_offset:
                scroll_offset = cursor_row
            elif cursor_row >= scroll_offset + visible_rows:
                scroll_offset = cursor_row - visible_rows + 1

            stdscr.clear()

            header = f" {prompt}  [{len(selected)} selected]"[:w - 1]
            stdscr.addstr(0, 0, header, curses.A_BOLD)

            for row in range(visible_rows):
                actual_row = row + scroll_offset
                if actual_row >= rows_per_col:
                    break
                for col in range(NUM_COLS):
                    idx = col * rows_per_col + actual_row
                    if idx >= n:
                        continue
                    marker = "[x]" if idx in selected else "[ ]"
                    text = f"{marker} {cards[idx]}"
                    max_text = col_width - 2
                    if len(text) > max_text:
                        text = text[:max_text - 1] + "~"
                    text = text.ljust(col_width - 1)
                    try:
                        if idx == cursor:
                            stdscr.addstr(row + 1, col * col_width, text, curses.color_pair(1) | curses.A_BOLD)
                        elif idx in selected:
                            stdscr.addstr(row + 1, col * col_width, text, curses.color_pair(2) | curses.A_BOLD)
                        else:
                            stdscr.addstr(row + 1, col * col_width, text)
                    except curses.error:
                        pass

            scroll_hint = f"  (row {scroll_offset + 1}/{rows_per_col})" if rows_per_col > visible_rows else ""
            footer = f" Arrows: navigate  SPACE: select  ENTER: confirm  ESC: cancel{scroll_hint}"[:w - 1]
            try:
                stdscr.addstr(h - 1, 0, footer, curses.A_REVERSE)
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            cur_col = cursor // rows_per_col
            cur_row = cursor % rows_per_col

            if key == curses.KEY_UP:
                if cur_row > 0:
                    cursor -= 1
            elif key == curses.KEY_DOWN:
                new = cursor + 1
                if cur_row + 1 < rows_per_col and new < n:
                    cursor = new
            elif key == curses.KEY_LEFT:
                if cur_col > 0:
                    cursor -= rows_per_col
            elif key == curses.KEY_RIGHT:
                new = cursor + rows_per_col
                if cur_col + 1 < NUM_COLS and new < n:
                    cursor = new
            elif key == ord(' '):
                selected.discard(cursor) if cursor in selected else selected.add(cursor)
            elif key in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                if not selected:
                    msg = " Select at least one card to continue. Press any key."[:w - 1]
                    try:
                        stdscr.addstr(h - 1, 0, " " * (w - 1), curses.A_REVERSE)
                        stdscr.addstr(h - 1, 0, msg, curses.A_REVERSE | curses.A_BOLD)
                    except curses.error:
                        pass
                    stdscr.refresh()
                    stdscr.getch()
                else:
                    sub_footer = f" [{len(selected)} cards selected]  ENTER: confirm  S: save  L: load  ESC: back"[:w - 1]
                    try:
                        stdscr.addstr(h - 1, 0, " " * (w - 1), curses.A_REVERSE)
                        stdscr.addstr(h - 1, 0, sub_footer, curses.A_REVERSE | curses.A_BOLD)
                    except curses.error:
                        pass
                    stdscr.refresh()
                    sub_key = stdscr.getch()
                    if sub_key in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                        result_holder.extend(cards[i] for i in sorted(selected))
                        break
                    elif sub_key in (ord('s'), ord('S')):
                        curses.endwin()
                        file_path = _centered_file_dialog('save')
                        if file_path:
                            with open(file_path, 'w') as f:
                                for i in sorted(selected):
                                    f.write(f"{cards[i]}\n")
                        stdscr.refresh()
                    elif sub_key in (ord('l'), ord('L')):
                        curses.endwin()
                        file_path = _centered_file_dialog('open')
                        if file_path:
                            with open(file_path, 'r') as f:
                                loaded = {line.strip() for line in f if line.strip()}
                            card_index = {name: i for i, name in enumerate(cards)}
                            selected = {card_index[name] for name in loaded if name in card_index}
                        stdscr.refresh()
                    # ESC or any other key: loop back, footer redraws on next iteration
            elif key == 27:  # ESC — cancel with no selection
                break
            elif key == curses.KEY_RESIZE:
                curses.update_lines_cols()
                stdscr.clear()

    curses.wrapper(_ui)
    return result_holder


# Function to display passed list and allow user to continue to add to it until 'done'
def _usr_card_input(card_names, prompt):
    return _card_select_columns(card_names, prompt)

# Function to display a passed list and prompt and return user input
def _usr_set_input(set_data_clean, prompt):
    while True:
        set_rq = questionary.autocomplete(
            prompt,
            choices=list(set_data_clean),
            style=theme.qs_style()
        ).ask()

        # Gives option to list all sets
        if set_rq.lower() == "list":
        # Printing resulting numerical set list
            for key, i in zip(set_data_clean, range(len(set_data_clean))):
                theme.info(f"{i+1}. {key}")
            continue
        # Gives option to restart (i.e. select another game)
        elif set_rq.lower() == "restart":
            return "restart"
        # Gives option to exit
        elif set_rq.lower() == "exit":
            return "exit"
        # Prevents bad/empty input
        elif set_rq == "" or (set_rq not in set_data_clean):
            theme.muted("You must choose a set, please type your desired set or type restart to start over")
        elif set_rq in list(set_data_clean):
            out = {}
            out[set_rq] = set_data_clean[set_rq]
            return out

if __name__ == "__main__":
    main()
