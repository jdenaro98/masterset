import asyncio
from scraper import TCGPlayerScraper
import json

async def debug_scrape():
    scraper = TCGPlayerScraper()
    try:
        await scraper.setup()
        
        # Go to a set's price guide
        url = "https://www.tcgplayer.com/categories/trading-and-collectible-card-games/magic-the-gathering/secrets-of-strixhaven"
        await scraper.page.goto(url)
        await scraper.page.wait_for_load_state("networkidle")
        
        # Get debug info about all /product/ links
        result = await scraper.page.evaluate("""
            () => {
                const debug = {
                    total_product_links: document.querySelectorAll('[href*="/product/"]').length,
                    product_links_details: []
                };
                
                document.querySelectorAll('[href*="/product/"]').forEach((el, idx) => {
                    if (idx < 10) {  // First 10 product links
                        const text = el.innerText?.trim() || '';
                        const href = el.getAttribute('href') || '';
                        const tagName = el.tagName;
                        const parentClasses = el.parentElement?.className || '';
                        
                        debug.product_links_details.push({
                            index: idx,
                            tag: tagName,
                            text_length: text.length,
                            text: text.substring(0, 80),
                            href: href.substring(0, 80),
                            parent_classes: parentClasses.substring(0, 100)
                        });
                    }
                });
                
                return debug;
            }
        """)
        
        print(json.dumps(result, indent=2))
        
    finally:
        await scraper.teardown()

asyncio.run(debug_scrape())
