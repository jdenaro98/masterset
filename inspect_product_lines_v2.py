"""Inspect the TCGPlayer search page to find main product line categories."""

import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_product_lines():
    """Inspect the TCGPlayer search page for main product line categories."""
    
    url = "https://www.tcgplayer.com/search/all/product?view=grid"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle")
        
        print("Page loaded. Extracting product lines...")
        
        # Extract main game categories by looking at the page structure
        product_lines = await page.evaluate("""
            () => {
                const lines = new Map();
                
                // Look for all links in the page
                const allLinks = document.querySelectorAll('a[href*="/categories/trading-and-collectible-card-games/"]');
                
                console.log(`Found ${allLinks.length} category links`);
                
                allLinks.forEach(link => {
                    const href = link.getAttribute('href') || '';
                    const text = link.innerText?.trim();
                    
                    // Extract the game name from the URL
                    // Pattern: /categories/trading-and-collectible-card-games/{game-name}
                    // or: /categories/trading-and-collectible-card-games/{game-name}/{set-name}
                    
                    const parts = href.split('/').filter(p => p);
                    
                    // The game name is 5 positions in (0: 'categories', 1: 'trading-and-collectible-card-games', 2: game-name)
                    if (parts.length >= 3) {
                        const gameName = parts[2];
                        const setName = parts[3];
                        
                        // Only store if this is a main game category (no set name in URL)
                        // Or if we don't have it yet
                        if (!lines.has(gameName)) {
                            lines.set(gameName, {
                                name: text || gameName,
                                url: href,
                                gameSlug: gameName
                            });
                        }
                    }
                });
                
                return Array.from(lines.values());
            }
        """)
        
        print(f"\nFound {len(product_lines)} unique product lines")
        
        for idx, line in enumerate(product_lines[:50], 1):
            print(f"{idx}. {line['name']}")
            print(f"   Game Slug: {line['gameSlug']}")
            print(f"   URL: {line['url']}")
        
        # Save results
        with open("product_lines_main.json", "w") as f:
            json.dump({
                "url": url,
                "total_found": len(product_lines),
                "product_lines": product_lines
            }, f, indent=2)
        
        print(f"\nResults saved to product_lines_main.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_product_lines())
