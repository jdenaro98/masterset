from playwright.sync_api import sync_playwright, expect
from playwright_stealth.stealth import Stealth
import questionary, re, time, sys, os
import optimizer
import cart_create
import requests

def main():
    with sync_playwright() as pw:
        URL = "https://www.tcgplayer.com/categories"
        titles = []
        urls = []

        print("==================================")
        print("Welcome to the TCGPlayer Scraper!")
        print("=================================")
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
    while set_rq == "" or (set_rq not in set_labels):
        set_rq = usr_set_input(set_labels, "Please choose which set you'd like to scrape: \n You can also type 'list to see the full list or 'restart' to go back to the beginning!")
        # Need to fix, not working right now
        # if set_rq == "restart":
        #     os.execl(sys.executable, sys.executable, *sys.argv)
        # Gives user full list if desired
        if set_rq == "list":
            # Printing resulting numerical set list
            for i in range(len(set_labels)):
                print("{}. {}".format(i+1, set_labels[i]))
        elif set_rq == "" or (set_rq not in set_labels):
            print("You must choose a set, please type your desired set or type restart to start over")
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
            card_urls.append(link.get_attribute("href"))
            # print(data)   # Debug

        # page.pause()      # Debug
        browser.close()

    # ======================================================================
    # Stage 5: Do logic and some more user input based on previous selection
    # ======================================================================
    # Inital ask on scraping method
    opts = ["1. Inclusive (type a list of card numbers you want data on)", "2. Exclusive (you want the whole set except a few card numbers)", "3. All Cards Please!"]
    scrape_choice = questionary.select(
        "Please Choose an option for how you'd like to scrape your card data",
        choices = opts
    ).ask()

    url_list = []
    # Prompt which cards and create short list of desired cards
    # Eventaully make it even fanci and allow file uploading (don't know what format)
    if scrape_choice == opts[0]:
        prompt = "Please search for and enter the cards you'd like to scrape. \n Type 'done' to complete your list. \n Type 'list' to show your current list \n Type 'full' to see the full card list"
        cards_include = usr_card_input(card_names, prompt)
        card_list = cards_include

        # Creating proper list of card names/urls
        for card in card_list:
            i = card_names.index(card)
            url_list.append(card_urls[i])

    # Prompt which cards and create short(er) list with prompted cards removed
    # Eventually make fancy as above
    elif scrape_choice == opts[1]:
        prompt = "Please search for and enter the cards you'd like to exclude from the full set scrape. \n Type 'done' to complete your list. \n Type 'list' to show your current list \n Type 'full' to see the full card list"
        cards_exclude = usr_card_input(card_names, prompt)
        card_list = card_names
        url_list = card_urls
        
        # Creating proper list of card names/urls
        for card in cards_exclude:
            i = card_names.index(card)
            card_list.pop(i)
            url_list.pop(i)
    # Basically do nothing beceause user wants whole list    
    else:
        card_list = card_names
        url_list = card_urls

    # Final display, need to add option to restart back at the card choosing
    print("Your final card list looks like:")
    for card in card_list:
        print(card)
    
    # ======================================================================
    # Stage 6: Remake web browser, scrape data from card list, card urls
    # ======================================================================
    with sync_playwright() as pw:
        all_card_data = {}
        browser = pw.chromium.launch(headless=False, args=["--window-size=640,640"])
        page = browser.new_page()
        stealth_config = Stealth()
        stealth_config.apply_stealth_sync(page)

        # Need to add logic/loop here to handle various urls
        for i in range(len(url_list)):
            # print(url_list[i])   # Debug
            C_URL = f"https://www.tcgplayer.com{url_list[i]}?Language=all&Condition=Lightly+Played|Near+Mint&page=1"
            page.goto(C_URL)
            page.wait_for_load_state("networkidle")
            
            # A survey may appear; dismiss if present
            try:
                dismiss_survey(page)
            except Exception:
                pass
            
            # Load 50 per page (max allowed)
            dropdown_container = page.locator(".tcg-input-field", has_text="Listings / Page")
            trigger = dropdown_container.get_by_role("combobox")
            trigger.scroll_into_view_if_needed()
            trigger.wait_for(state="visible")
            trigger.click()
            page.get_by_role("option", name="50").click()
            page.wait_for_load_state("networkidle")

            # After saving filters a survey may appear; dismiss if present
            try:
                dismiss_survey(page)
            except Exception:
                pass

            # ======================================================================
            # Stage 6: Add all seller data to nested list/dict structure for each card
            # ======================================================================
            # Call scraping logic
            all_card_data[card_list[i]] = scrape_listings(page, game_rq)

        browser.close()

# Debug print of all scraped data, can be removed later
    print("Scraped listings:")
    for card, listings in all_card_data.items():
        print(card)
        if not listings:
            print("  (no listings)")
        else:
            for s in listings:
                seller = s.get("seller", "")
                condition = s.get("condition", "")
                price = s.get("price", "")
                shipping = s.get("shipping", "")
                total = s.get("total", "")
                print(f"  - {seller} | {condition} | ${price:.2f} | ${shipping:.2f} | ${total:.2f}")
        print("")

    optimized_cart = optimizer.optimize(all_card_data)

    print("Optimized cart:")
    sellers = {item['seller'] for item in optimized_cart if item.get('seller')}
    total_cost = sum(item['total'] for item in optimized_cart if item.get('total') is not None)
    print(f"  Unique sellers: {len(sellers)}")
    print(f"  Estimated total: ${total_cost:.2f}\n")
    for item in optimized_cart:
        seller = item.get('seller') or 'N/A'
        condition = item.get('condition') or 'N/A'
        price = item.get('price') if item.get('price') is not None else 0.0
        shipping = item.get('shipping') if item.get('shipping') is not None else 0.0
        total = item.get('total') if item.get('total') is not None else 0.0
        print(f"  - {item['card']} | {seller} | {condition} | ${price:.2f} | ${shipping:.2f} | ${total:.2f}")

    if questionary.confirm("Open browser and add the optimized items to cart using Playwright?").ask():
        cookie_export_path = cart_create.create_cart(optimized_cart)
        if cookie_export_path:
            print(f"Cart cookies exported to: {cookie_export_path}")
        else:
            print("Cart creation finished, but cookie export was not completed.")

###############################################################################

# Scrape from page
def scrape_listings(page, game):
    listings_data = []
    # Identify all listing rows
    listings = page.locator(".listing-item")

    # Wait briefly for listings to appear (some pages load dynamically)
    try:
        page.wait_for_selector(".listing-item", timeout=10000)
    except Exception:
        return listings_data

    for i in range(listings.count()):
        item = listings.nth(i)
        
        # Skip non-English/Japanese listings for Pokemon sets by checking the listing title
        if game == "Pokemon Japan" or game == "Pokemon":
            title_locator = item.locator(".listing-item__listing-data__listo__title")
            if title_locator.count() > 0:
                title = title_locator.first.text_content(timeout=1000) or ""
                if re.search(r'(Chinese|Korean|Spanish|French|German|Italian|Portuguese|Thai|Indonesian|Dutch|Russian|Polish)', title, re.I):
                    print("Skipping non-English/Japanese listing")
                    continue
        
        # Scrape raw strings
        seller = item.locator(".seller-info__name").inner_text().strip()
        condition = item.locator(".listing-item__listing-data__info__condition").inner_text().strip()
        price = item.locator(".listing-item__listing-data__info__price").inner_text().strip()
        raw_shipping = item.locator(".listing-item__listing-data__info span").inner_text().strip()
        # Handle "Included" vs numerical
        shipping_clean = "$0.00" if "Included" in raw_shipping else \
                         raw_shipping.replace("+", "").replace("Shipping", "").strip()
            
        # Add this seller's dict to the list
        listings_data.append({
            "seller": seller,
            "condition": condition,
            "price": parse_money(price),
            "shipping": parse_money(shipping_clean),
            "total": parse_money(price) + parse_money(shipping_clean),
            "card_url": page.url,
        })
    return listings_data


def parse_money(s):
    return round(float(re.sub(r'[^0-9.]', '', s) or 0), 2)

# Dismiss survey overlay (e.g., QSI web survey) if it appears
SURVEY_NO_THANKS_TEXT = None
def dismiss_survey(page):
    """Detect QSI survey overlay, find the nearest 'No' button, cache its exact
    label and click it. Returns True if a dismissal was attempted.
    """
    global SURVEY_NO_THANKS_TEXT

    # Fast path: if we previously discovered the exact label, try that first
    if SURVEY_NO_THANKS_TEXT:
        try:
            btn = page.get_by_text(SURVEY_NO_THANKS_TEXT, exact=True)
            if btn.count() > 0:
                btn.first.click()
                page.wait_for_selector(".QSIWebResponsiveShadowBox", state="detached", timeout=500)
                return True
        except Exception:
            pass

    # Wait briefly for the overlay to appear; if it doesn't, nothing to do
    try:
        overlay = page.locator(".QSIWebResponsiveShadowBox").first
        page.wait_for_selector(".QSIWebResponsiveShadowBox", timeout=500)
        overlay_box = overlay.bounding_box()
        if not overlay_box:
            return False
    except Exception:
        return False

    # Look for visible actionable elements that include the word 'no'
    candidates = page.locator('button, a, [role="button"], input[type="button"]')
    best_idx = None
    best_dist = None
    found_text = None

    ox = overlay_box["x"] + overlay_box["width"] / 2
    oy = overlay_box["y"] + overlay_box["height"] / 2

    for i in range(candidates.count()):
        cand = candidates.nth(i)
        try:
            txt = cand.inner_text().strip()
            if not txt:
                continue
            if re.search(r"\bno\b", txt, re.I):
                bb = cand.bounding_box()
                if not bb:
                    continue
                cx = bb["x"] + bb["width"] / 2
                cy = bb["y"] + bb["height"] / 2
                dist = (ox - cx) ** 2 + (oy - cy) ** 2
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_idx = i
                    found_text = txt
        except Exception:
            continue

    if best_idx is not None:
        try:
            target = candidates.nth(best_idx)
            target.click()
            page.wait_for_selector(".QSIWebResponsiveShadowBox", state="detached", timeout=500)
            SURVEY_NO_THANKS_TEXT = found_text
            return True
        except Exception:
            return False

    return False

# Function to display passed list and allow user to continue to add to it until 'done'
def usr_card_input(card_names, prompt):
    done = 0
    cardlist = []
    while not done:
        temp = questionary.autocomplete(
            prompt,
            choices = card_names
        ).ask()
        if temp == 'done':
            done = 1
        elif temp == 'list':
            print("=============================")
            for card in cardlist:
                print(card)
            print("=============================")
        elif temp == 'full':
            print("=============================")
            for card in card_names:
                print(card)
            print("=============================")
        elif temp in card_names:
            cardlist.append(temp)
        else:
            pass
    return cardlist

# Function to display a passed list and prompt and return user input
def usr_set_input(set_labels, prompt):
    set_rq = questionary.autocomplete(
        prompt,
        choices = set_labels
    ).ask()
    return set_rq

if __name__ == "__main__":
    main()