from playwright.sync_api import sync_playwright
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
    # Calling User set input function to reduce redundant code
    set_rq = usr_set_input(set_labels, "Please type in desired set or press Enter for full set list")

    # Gives user full list if desired
    if set_rq == "":
        # Printing resulting numerical set list
        for i in range(len(set_labels)):
            print("{}. {}".format(i+1, set_labels[i]))
        # Requests user input with same function again after seeing list
        set_rq = usr_set_input(set_labels, "Please choose which set you'd like to scrape:")
   
    # Forces user to choose or exit
    while set_rq == "":
        print("You must choose a set, please type your desired set or type restart to start over")
        set_rq = usr_set_input(set_labels, "Please choose which set you'd like to scrape:")
        if set_rq == "restart":
            os.execl(sys.executable, sys.executable, *sys.argv)
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
    # Stage 5: Do logic and some more user input based on previous selec
    # ======================================================================
    # Inital ask on scraping method
    opts = ["1. Inclusive (type a list of card numbers you want data on)", "2. Exclusive (you want the whole set except a few card numbers)", "3. All Cards Please!"]
    scrape_choice = questionary.select(
        "Please Choose an option for how you'd like to scrape your card data",
        choices = opts
    ).ask()

    # Prompt which cards and create short list of desired cards
    # Eventually make this fancy and use autocomplete to add one card at a time and update the user with a list as they add the cards
    # Eventaully make it even fancier and allow file uploading (don't know what format)
    if scrape_choice == opts[0]:
        cards_include = questionary.text("Please input your desired list of cards to scrape by number separated by a commma (e.g. 1,7,37,94)").ask()
        cards_include = strip_string(cards_include)
    # Prompt which cards and create short(er) list with prompted cards removed
    # Eventually make fancy as above
    elif scrape_choice == opts[1]:
        cards_exclude = questionary.text("Please input your desired list of cards (by card number) to exclude from the full set (e.g. 1,7,37,94)").ask()
        cards_exclude = strip_string(cards_exclude)
    # Basically do nothing beceause user wants whole list    
    else:
        pass
        
# Function to display a passed list and prompt and return user input
def usr_set_input(set_labels, prompt):
    set_rq = questionary.autocomplete(
        prompt,
        choices = set_labels
    ).ask()
    return set_rq

# Function to strip all numbers from passed string
def strip_string(reqst):
    return [int(x.strip()) for x in reqst.split(',')]

if __name__ == "__main__":
    main()