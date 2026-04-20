from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth

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
        # page.screenshot(path="debug.png")

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
        # print(url_rq)
        print("You chose game {}, {}. Great choice!".format(game_rqn, game_rq))
        print("Visiting the 'Price Guide' page for {}!".format(game_rq))
        PG_URL = f"https://www.tcgplayer.com{url_rq}/price-guides"
        # print(PG_URL)
        # print("The updated url to be used is: {}".format(PG_URL))     # Debug

        # ======================================================================
        # Stage 2: Navigate to Price guide page and collect set list
        # ======================================================================
        page.goto(PG_URL)
        page.wait_for_load_state("networkidle")

        dd = page.get_by_placeholder("Select a Set")
        dd_list = dd.get_attribute("aria-controls")
        set_labels = [item.get_attribute("aria-label") for item in page.locator(f"#{dd_list} li").all()]

        # Printing resulting numerical set list
        i = 1
        for item in set_labels:
            print("{}. {}".format(i, item))
            i+=1         

        set_rqn = int(input("Please choose which set you'd like to scrape: "))
        set_rq = set_labels[set_rqn-1]
        print("You chose set {}, {}. Great choice!".format(set_rqn, set_rq))
        print("Visiting the 'Price Guide' page for set {}!".format(set_rq))
        set_rqf = set_rq
        set_rqf = set_rqf.replace(":", "")
        set_rqf = set_rqf.replace(" ", "-")
        set_rqf = set_rqf.lower()
        SET_URL = f"https://www.tcgplayer.com{url_rq}/price-guides/{set_rqf}"

        # ======================================================================
        # Stage 3: Navigate to Price guide page for set and scrape card url data
        # ======================================================================
        page.goto(SET_URL)
        page.wait_for_load_state("networkidle")
        page.pause()

        browser.close()

if __name__ == "__main__":
    main()