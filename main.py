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

        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        stealth_config = Stealth()
        stealth_config.apply_stealth_sync(page)

        page.goto(URL)
        page.wait_for_load_state("networkidle")
        page.screenshot(path="debug.png")

        # 1. Target the first grouping container specifically
        # This specifically targets "Trading/Collectible Card Games"
        # first_group = page.locator(".grouping").first
        games = page.locator(".site-map.grouping > .grouping").first

        # 2. Find all titles/links within the desired group
        for link in games.get_by_test_id("base-link").all():
            titles.append(link.inner_text())
            # titles.sort() # unnecessary for now
            urls.append(link.get_attribute("href"))
            # print(data)   # Debug

        # Printing resulting game list
        i = 1
        for title in titles:
            print("{}. {}".format(i, title))
            i+=1 

        # User input for requested game
        game_rqn = int(input("Please choose which game you'd like to scrape: "))
        game_rq = titles[game_rqn-1]
        print("You chose game {}, {}. Great choice!".format(game_rqn, game_rq))
        print("Visiting the 'Price Guide' page for {}!".format(game_rq))

        game_rqf = game_rq  # Formatted game name for URL
        game_rqf = game_rqf.replace(":", "")
        game_rqf = game_rqf.replace(" ", "-")
        PG_URL = f"https://www.tcgplayer.com/categories/trading-and-collectible-card-games/{game_rqf}/price-guides"
        print("The updated url to be used is: {}".format(PG_URL))

        browser.close()

if __name__ == "__main__":
    main()