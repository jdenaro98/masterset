"""Inspector script to analyze price guide structure."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_price_guide():
    """Inspect how cards and sellers are displayed on a price guide page."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        results = {
            "status": "in_progress",
            "page_url": "",
            "errors": []
        }
        
        try:
            # Try a Pokemon set price guide - ME03: Perfect Order
            url = f"{TCGPLAYER_BASE_URL}/search/pokemon/me03-perfect-order?productLineName=pokemon"
            print(f"🔍 Navigating to: {url}")
            results["page_url"] = url
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="pokemon_price_guide.png")
            print("📸 Screenshot saved: pokemon_price_guide.png")
            
            # Analyze the page structure
            print("\n🔎 Analyzing price guide structure...")
            analysis = await page.evaluate("""
                () => {
                    const results = {
                        page_title: document.title,
                        cards_found: 0,
                        card_structure: {},
                        seller_structure: {},
                        pagination_info: {},
                        sample_cards: []
                    };
                    
                    // Find card entries
                    const cards = document.querySelectorAll('[class*="product"], [class*="card"], [data-testid*="product"]');
                    results.cards_found = cards.length;
                    
                    // Sample first card to understand structure
                    if (cards.length > 0) {
                        const firstCard = cards[0];
                        results.card_structure = {
                            tag: firstCard.tagName,
                            classes: firstCard.className.substring(0, 150),
                            innerHTML_preview: firstCard.innerHTML.substring(0, 300)
                        };
                        
                        // Try to extract card info from first few cards
                        cards.forEach((card, idx) => {
                            if (idx < 3) {
                                results.sample_cards.push({
                                    text: card.innerText?.substring(0, 300),
                                    innerHTML_preview: card.innerHTML.substring(0, 200)
                                });
                            }
                        });
                    }
                    
                    // Look for seller/market data structures
                    const rows = document.querySelectorAll('[class*="row"], [class*="listing"], [class*="seller"], tr');
                    console.log('Found', rows.length, 'row elements');
                    
                    if (rows.length > 0) {
                        const firstRow = rows[0];
                        results.seller_structure = {
                            tag: firstRow.tagName,
                            classes: firstRow.className.substring(0, 150),
                            text_preview: firstRow.innerText?.substring(0, 200)
                        };
                    }
                    
                    // Look for pagination
                    const paginationElements = document.querySelectorAll('[class*="paginat"], [class*="page"]');
                    if (paginationElements.length > 0) {
                        results.pagination_info = {
                            elements_found: paginationElements.length,
                            text_preview: paginationElements[0].innerText?.substring(0, 100)
                        };
                    }
                    
                    // Look for price/condition/shipping information
                    const priceElements = document.querySelectorAll('[class*="price"], [class*="cost"], [class*="condition"]');
                    console.log('Found', priceElements.length, 'price-related elements');
                    
                    // Extract visible text to understand what data is on the page
                    const bodyText = document.body.innerText;
                    const lines = bodyText.split('\\n').filter(line => line.trim().length > 0);
                    
                    results.visible_text_sample = lines.slice(0, 50);
                    
                    return results;
                }
            """)
            
            print("\n📊 Analysis Results:")
            print(f"Page Title: {analysis.get('page_title')}")
            print(f"Cards found: {analysis.get('cards_found')}")
            print(f"Card structure: {analysis.get('card_structure', {}).get('classes', 'Not found')}")
            print(f"Seller structure: {analysis.get('seller_structure', {}).get('classes', 'Not found')}")
            print("\nFirst 30 visible text lines:")
            for line in analysis.get('visible_text_sample', [])[:30]:
                print(f"  {line}")
            
            results["analysis"] = analysis
            
            # Save full HTML
            html = await page.content()
            with open("pokemon_price_guide.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: pokemon_price_guide.html")
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results
        with open("price_guide_analysis.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to price_guide_analysis.json")


if __name__ == "__main__":
    asyncio.run(inspect_price_guide())
