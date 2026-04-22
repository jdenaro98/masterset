from playwright.sync_api import sync_playwright, expect
from playwright_stealth.stealth import Stealth
import questionary
import sys, os

def main():
    # Step 1: Scrape Games List
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
        browser = pw.chromium.launch(headless=False, args=["--window-size=640,640"])
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
        browser = pw.chromium.launch(headless=False, args=["--window-size=640,640"])
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
            card_names.append(link.inner_text())
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
        pass

    # Final display, need to add option to restart back at the card choosing
    print("Your final card list looks like:")
    for card in card_list:
        print(card)
    
    # ======================================================================
    # Stage 6: Remake web browser, scrape data from card list, card urls
    # ======================================================================
    with sync_playwright() as pw:
        card_names = []
        card_urls = []
        browser = pw.chromium.launch(headless=False, args=["--window-size=640,640"])
        page = browser.new_page()
        stealth_config = Stealth()
        stealth_config.apply_stealth_sync(page)

        # Need to add logic/loop here to handle various urls
        for url in url_list:
            C_URL = f"https://www.tcgplayer.com{url}"
            page.goto(C_URL)
            page.wait_for_load_state("networkidle")
            
            page.get_by_test_id("showFilters").click()
            drawer = page.locator(".tcg-drawer__sheet")
            drawer.wait_for(state="visible")        
            
            # Scrolling and selecting 'lightly played' which will also select 'near mint'
            # FUTURE: Add user input to decide what conditions they're ok with

            # FIX!!: Not waiting after selecting LP to select NM, only getting one as a result
            lp_filter = page.locator("#Condition-LightlyPlayed-filter")
            lp_filter.scroll_into_view_if_needed()
            lp_filter.click(force=True)
            expect(lp_filter).to_be_checked()
            nm_filter = page.locator("#Condition-NearMint-filter")
            nm_filter.scroll_into_view_if_needed()
            nm_filter.click(force=True)
            expect(nm_filter).to_be_checked()
            page.locator(".filter-drawer-footer__button-save").click()
            page.wait_for_load_state("networkidle")

            # Load 50 per page (max allowed)
            dropdown_container = page.locator(".tcg-input-field", has_text="Listings / Page")
            trigger = dropdown_container.get_by_role("combobox")
            trigger.scroll_into_view_if_needed()
            trigger.wait_for(state="visible")
            trigger.click()
            page.get_by_role("option", name="50").click()
            page.wait_for_load_state("networkidle")
            page.pause()

            # Scraping and data export logic

        browser.close()

###############################################################################

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