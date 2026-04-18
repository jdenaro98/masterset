"""Debug script to inspect card page structure."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from scraper import TCGPlayerScraper

async def debug_card_extraction():
    """Debug the card link extraction."""
    
    print("\n" + "="*80)
    print("DEBUG - Card Link Extraction")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    
    try:
        await scraper.setup()
        
        # Navigate to Pokemon Base Set URL
        url = "https://www.tcgplayer.com/search/pokemon/base-set/product?view=grid"
        print(f"\nNavigating to: {url}")
        await scraper.page.goto(url, wait_until="domcontentloaded")
        await scraper.page.wait_for_load_state("networkidle")
        
        # First, get page title and basic info
        title = await scraper.page.title()
        print(f"Page title: {title}")
        
        # Try different selectors to find products
        selectors = [
            'a[href*="/product/"]',
            'a[href*="/products/"]',
            'div[class*="product"]',
            'div[class*="card"]',
            '.productListing',
            '[data-test*="product"]',
        ]
        
        print("\nTrying different selectors:")
        for selector in selectors:
            count = await scraper.page.evaluate(f"""
                () => {{
                    return document.querySelectorAll('{selector}').length;
                }}
            """)
            print(f"  {selector}: {count} elements")
        
        # Get the full inner text to see what's on the page
        page_text = await scraper.page.evaluate("""
            () => {
                return document.body.innerText.substring(0, 2000);
            }
        """)
        
        print("\nFirst 2000 chars of page content:")
        print(page_text)
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.teardown()

if __name__ == "__main__":
    asyncio.run(debug_card_extraction())
