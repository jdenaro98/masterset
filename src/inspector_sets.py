"""Inspector script to analyze set listing structure."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_sets_listing():
    """Inspect how sets are listed on the Pokemon English category page."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        results = {
            "status": "in_progress",
            "page_url": "",
            "sets": [],
            "errors": []
        }
        
        try:
            # Try the Pokemon English sets category page
            url = f"{TCGPLAYER_BASE_URL}/categories/trading-and-collectible-card-games/pokemon"
            print(f"🔍 Navigating to: {url}")
            results["page_url"] = url
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="pokemon_english_sets.png")
            print("📸 Screenshot saved: pokemon_english_sets.png")
            
            # Analyze the page structure
            print("\n🔎 Analyzing sets listing structure...")
            analysis = await page.evaluate("""
                () => {
                    const results = {
                        page_title: document.title,
                        sets: [],
                        set_elements: [],
                        links_with_set: []
                    };
                    
                    // Find all section/category elements that might represent sets
                    document.querySelectorAll('section, [class*="set"], [class*="product-list"]').forEach((el, i) => {
                        if (el.innerText?.length > 0 && el.innerText?.length < 500) {
                            const text = el.innerText.trim();
                            if (i < 20) { // Limit to first 20
                                results.set_elements.push({
                                    tag: el.tagName,
                                    class: el.className.substring(0, 80),
                                    text: text.substring(0, 150)
                                });
                            }
                        }
                    });
                    
                    // Find all links that mention specific sets or have product names
                    document.querySelectorAll('a').forEach(link => {
                        const href = link.getAttribute('href') || '';
                        const text = link.textContent.trim();
                        
                        // Look for set URLs (they might have category names or set IDs)
                        if ((href.includes('/categories/') || href.includes('/search/') || href.includes('/product/')) &&
                            text.length > 2 && text.length < 200 &&
                            !text.includes('Sign In') && !text.includes('Cart') &&
                            !text.includes('Return') && !text.includes('Shipping')) {
                            
                            if (results.links_with_set.length < 100) {
                                results.links_with_set.push({
                                    text: text.substring(0, 100),
                                    href: href.substring(0, 200)
                                });
                            }
                        }
                    });
                    
                    // Look for specific text patterns that indicate sets
                    const pageText = document.body.innerText;
                    const lines = pageText.split('\\n').filter(line => line.trim().length > 0);
                    
                    lines.forEach((line, i) => {
                        // Look for lines that mention specific sets/years/expansions
                        if ((line.toLowerCase().includes('set') ||
                             line.toLowerCase().includes('collection') ||
                             line.toLowerCase().includes('box') ||
                             line.match(/20\\d{2}|booster|expansion|series|generation/i)) &&
                            line.length < 150 && 
                            !line.includes('Sign In') && 
                            results.sets.length < 50) {
                            results.sets.push(line.substring(0, 150));
                        }
                    });
                    
                    return results;
                }
            """)
            
            print("\n📊 Analysis Results:")
            print(f"Page Title: {analysis.get('page_title')}")
            print(f"Found {len(analysis.get('links_with_set', []))} links")
            print(f"Found {len(analysis.get('sets', []))} set-related text lines (first 10):")
            for set_name in analysis.get('sets', [])[:10]:
                print(f"  - {set_name}")
            
            results["analysis"] = analysis
            
            # Save full HTML
            html = await page.content()
            with open("pokemon_english_sets.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: pokemon_english_sets.html")
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results
        with open("sets_listing_analysis.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to sets_listing_analysis.json")


if __name__ == "__main__":
    asyncio.run(inspect_sets_listing())
