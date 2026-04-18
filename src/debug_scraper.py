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
        
        # Get debug info about elements on page
        result = await scraper.page.evaluate("""
            () => {
                const debug = {
                    total_elements: document.querySelectorAll('[class*="card"]').length,
                    elements_details: []
                };
                
                document.querySelectorAll('[class*="card"]').forEach((el, idx) => {
                    if (idx < 10) {  // First 10 elements
                        const text = el.innerText?.trim() || '';
                        const classes = el.className;
                        const link = el.querySelector('a');
                        const href = link?.getAttribute('href') || '';
                        
                        debug.elements_details.push({
                            index: idx,
                            classes: classes.substring(0, 100),
                            text_length: text.length,
                            text: text.substring(0, 100),
                            has_link: !!link,
                            href: href.substring(0, 100)
                        });
                    }
                });
                
                // Also check for other potential card containers
                debug.divs_with_product = document.querySelectorAll('[href*="/product/"]').length;
                
                return debug;
            }
        """)
        
        print(json.dumps(result, indent=2))
        
    finally:
        await scraper.teardown()

asyncio.run(debug_scrape())
