"""Debug seller extraction from product page - FIXED VERSION."""

import asyncio
from playwright.async_api import async_playwright
from config import TCGPLAYER_BASE_URL, DELAY_BETWEEN_REQUESTS
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_seller_extraction_fixed():
    """Extract sellers with fixed logic."""

    card_url = "https://www.tcgplayer.com/product/686601/magic-secrets-of-strixhaven-emeritus-of-ideation"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        print(f"Navigating to {card_url}...")
        await page.goto(card_url, wait_until="domcontentloaded", timeout=30000) 
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

        sellers = await page.evaluate("""
            () => {
                const sellers = [];
                const pageText = document.body.innerText;
                const lines = pageText.split('\\n').map(line => line.trim()).filter(line => line.length > 0);

                console.log('Total lines:', lines.length);

                let inSellerSection = false;
                let currentSeller = {};

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];

                    if (line === 'Listings / Page' && i + 1 < lines.length && lines[i + 1].match(/^\\d+$/)) {
                        console.log('Found listings section at line', i);
                        inSellerSection = true;
                        i += 1;
                        continue;
                    }

                    if (!inSellerSection) continue;

                    if (line.includes('Customers Also Purchased')) {
                        console.log('Ending seller section at line', i);        
                        break;
                    }

                    if (line && !line.includes('$') && !line.includes('%') && 
                        !line.includes('Add to Cart') && !line.includes('Sales') &&
                        !line.includes('Mint') && !line.includes('Played') &&   
                        !line.includes('Shipping') && !line.includes('of') &&
                        !line.match(/^\\d+$/) && line.length > 2 && line.length < 50) {

                        if (i + 1 < lines.length && lines[i + 1].includes('%')) {
                            console.log('Found seller at line', i, ':', line);
                            if (currentSeller.name) {
                                sellers.push({...currentSeller});
                            }
                            currentSeller = { name: line };
                            
                            i++;
                            const repLine = lines[i];
                            currentSeller.reputation_percentage = repLine;
                            console.log('  Reputation:', repLine);
                        }
                    }

                    if (line.match(/\\(\\d+[\\w\\s]*\\)/)) {
                        const match = line.match(/\\((\\d+)/);
                        if (match) {
                            console.log('Found sales at line', i, ':', match[1]);
                            currentSeller.sales = parseInt(match[1]);
                        }
                    }

                    if (line.match(/Mint|Played|Damaged/) && !line.includes('%')) {
                        console.log('Found condition at line', i, ':', line);   
                        currentSeller.condition = line;
                    }

                    if (line.match(/^\\$\\d+\\.\\d{2}$/) && !currentSeller.price) {
                        console.log('Found price at line', i, ':', line);       
                        currentSeller.price = line;
                    }

                    if (line.includes('Shipping') || line.match(/^\\+ \\$\\d+\\.\\d{2}/)) {
                        console.log('Found shipping at line', i, ':', line);    
                        currentSeller.shipping = line;
                    }
                }

                if (currentSeller.name) {
                    sellers.push(currentSeller);
                }

                console.log('Total sellers found:', sellers.length);
                return sellers;
            }
        """)

        print(f"\n=== EXTRACTED SELLERS ===")
        print(f"Total sellers found: {len(sellers)}")
        print(json.dumps(sellers, indent=2))

        with open("debug_sellers.json", "w", encoding="utf-8") as f:
            json.dump(sellers, f, indent=2)
        print("\nDebug sellers saved to debug_sellers.json")

        if sellers:
            print(f"\n=== SELLER SUMMARY ===")
            for i, seller in enumerate(sellers[:10], 1):
                print(f"\nSeller {i}:")
                print(f"  Name: {seller.get('name', 'N/A')}")
                print(f"  Sales: {seller.get('sales', 'N/A')}")
                print(f"  Reputation: {seller.get('reputation_percentage', 'N/A')}")
                print(f"  Condition: {seller.get('condition', 'N/A')}")
                print(f"  Price: {seller.get('price', 'N/A')}")
                print(f"  Shipping: {seller.get('shipping', 'N/A')}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_seller_extraction_fixed())
