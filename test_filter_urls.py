"""Test URL structure for filtering by product line."""

import asyncio
from playwright.async_api import async_playwright

async def test_filter_urls():
    """Test different URLs to find the right filter structure."""
    
    test_urls = [
        "https://www.tcgplayer.com/search/pokemon/product?view=grid",
        "https://www.tcgplayer.com/search/all/product?view=grid&productLineFilter=Pokemon",
        "https://www.tcgplayer.com/search/all/product?view=grid&productLine=Pokemon",
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        for url in test_urls:
            print(f"\n{'='*80}")
            print(f"Testing URL: {url}")
            print('='*80)
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=5000)
                
                # Get page text to see if Set filter is visible
                page_text = await page.evaluate("() => document.body.innerText")
                lines = page_text.split('\n')
                
                # Find Set filter section
                for i, line in enumerate(lines):
                    if 'Set' in line and i < 50:  # Look in first 50 lines
                        print(f"\nFound 'Set' at line {i}:")
                        print("Context:")
                        for j in range(max(0, i-2), min(len(lines), i+15)):
                            print(f"  {j}: {lines[j][:100]}")
                        break
                else:
                    print("\nNo 'Set' filter found in first 50 lines")
                
                # Check current URL
                current_url = page.url
                print(f"\nFinal URL: {current_url}")
                
            except Exception as e:
                print(f"Error: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_filter_urls())
