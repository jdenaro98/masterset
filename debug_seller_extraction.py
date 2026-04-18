"""Debug seller extraction from product page."""

import asyncio
from playwright.async_api import async_playwright
from config import TCGPLAYER_BASE_URL, DELAY_BETWEEN_REQUESTS
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_seller_extraction():
    """Debug why seller extraction isn't working."""
    
    # Use the same product URL as before
    card_url = "https://www.tcgplayer.com/product/686601/magic-secrets-of-strixhaven-emeritus-of-ideation"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Navigate to product page
        print(f"Navigating to {card_url}...")
        await page.goto(card_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
        
        # Get the page text
        page_text = await page.evaluate("() => document.body.innerText")
        
        # Save the full page text for inspection
        with open("debug_page_text.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        print("Full page text saved to debug_page_text.txt")
        
        # Print first 3000 chars to see structure
        print("\n=== FIRST 3000 CHARS OF PAGE TEXT ===")
        print(page_text[:3000])
        
        # Look for "Listings" keyword
        lines = page_text.split('\n')
        print(f"\n=== TOTAL LINES: {len(lines)} ===")
        
        # Find lines with "Listings"
        listings_lines = [i for i, line in enumerate(lines) if 'Listings' in line or 'as low as' in line or 'seller' in line.lower()]
        print(f"\n=== LINES WITH 'LISTINGS' OR SELLER INFO (indices): {listings_lines[:20]} ===")
        
        # Print context around first listings line
        if listings_lines:
            idx = listings_lines[0]
            start = max(0, idx - 5)
            end = min(len(lines), idx + 20)
            print(f"\n=== CONTEXT AROUND LINE {idx} (Listings) ===")
            for i in range(start, end):
                print(f"{i}: {lines[i]}")
        
        # Try the seller extraction JavaScript manually
        sellers = await page.evaluate("""
            () => {
                const sellers = [];
                const pageText = document.body.innerText;
                const lines = pageText.split('\\n').map(line => line.trim()).filter(line => line.length > 0);
                
                console.log('Total lines:', lines.length);
                
                // Find the "Listings" section and parse sellers
                let inSellerSection = false;
                let currentSeller = {};
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    
                    // Detect start of seller listings section
                    if (line.includes('Listings') && line.includes('as low as')) {
                        console.log('Found listings section at line', i, ':', line);
                        inSellerSection = true;
                        continue;
                    }
                    
                    if (!inSellerSection) continue;
                    
                    // Stop if we hit pagination controls or end of listings
                    if (line.includes('Sort By') || line.includes('Listings / Page')) {
                        console.log('Ending seller section at line', i);
                        break;
                    }
                    
                    // Detect seller name
                    if (line && !line.includes('$') && !line.includes('+') && 
                        !line.includes('Add to Cart') && !line.includes('Sales') &&
                        !line.includes('Mint') && !line.includes('Played') &&
                        !line.includes('Shipping') && line.length > 3 && line.length < 50) {
                        
                        // Check if this looks like a seller name
                        if (/^[A-Z]/.test(line) && !line.match(/^\\d/)) {
                            console.log('Found potential seller at line', i, ':', line);
                            // If we have a previous seller, save it
                            if (currentSeller.name) {
                                sellers.push({...currentSeller});
                            }
                            currentSeller = { name: line };
                        }
                    }
                    
                    // Extract sales count
                    if (line.includes('Sales') && line.match(/\\d+/)) {
                        const match = line.match(/(\\d+)\\s*(?:\\+)?\\s*Sales/);
                        if (match) {
                            console.log('Found sales at line', i, ':', match[1]);
                            currentSeller.reputation = parseInt(match[1]);
                        }
                    }
                    
                    // Extract condition
                    if (line.match(/Mint|Played|Damaged|PSA/)) {
                        console.log('Found condition at line', i, ':', line);
                        currentSeller.condition = line;
                    }
                    
                    // Extract price
                    if (line.match(/^\\$[\\d.]+/)) {
                        console.log('Found price at line', i, ':', line);
                        currentSeller.price = parseFloat(line.replace('$', ''));
                    }
                    
                    // Extract shipping
                    if (line.includes('Shipping')) {
                        console.log('Found shipping at line', i, ':', line);
                        if (line.includes('Included')) {
                            currentSeller.shipping = 0;
                        } else {
                            const match = line.match(/\\$([\\d.]+)/);
                            if (match) {
                                currentSeller.shipping = parseFloat(match[1]);
                            }
                        }
                    }
                }
                
                // Don't forget the last seller
                if (currentSeller.name) {
                    sellers.push(currentSeller);
                }
                
                console.log('Total sellers found:', sellers.length);
                return sellers;
            }
        """)
        
        print(f"\n=== EXTRACTED SELLERS ===")
        print(json.dumps(sellers, indent=2))
        
        # Save to file
        with open("debug_sellers.json", "w", encoding="utf-8") as f:
            json.dump(sellers, f, indent=2)
        print("\nDebug sellers saved to debug_sellers.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_seller_extraction())
