from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def main():
    # Step 1: Scrape Games List
    with Stealth().sync_playwright() as pw:
        URL = "https://www.tcgplayer.com/categories"

        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL)
        page.wait_for_load_state("networkidle")
        page.screenshot(path="debug.png")

        # 1. Target the first grouping container specifically
        # This specifically targets "Trading/Collectible Card Games"
        # first_group = page.locator(".grouping").first
        first_group = page.locator(".site-map.grouping > .grouping").first

        # 2. Find all titles/links within the desired group
        for link in first_group.get_by_test_id("base-link").all():
            data = {
                "title": link.inner_text(),
                "url": link.get_attribute("href")
            }
            # Debug
            print(data)

        browser.close()

if __name__ == "__main__":
    main()
