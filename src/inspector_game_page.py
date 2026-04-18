"""Inspector script to analyze TCGPlayer game pages and sets structure."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_pokemon_page():
    """Inspect the Pokemon game page to find sets structure."""
    
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
            "sets_structure": [],
            "errors": []
        }
        
        try:
            # Try the search page
            url = f"{TCGPLAYER_BASE_URL}/search/pokemon/product?productLineName=pokemon&page=1"
            print(f"🔍 Navigating to: {url}")
            results["page_url"] = url
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="pokemon_sets_page.png")
            print("📸 Screenshot saved: pokemon_sets_page.png")
            results["screenshot"] = "pokemon_sets_page.png"
            
            # Analyze the page structure
            print("\n🔎 Analyzing Pokemon page structure...")
            analysis = await page.evaluate("""
                () => {
                    const results = {
                        page_title: document.title,
                        sets: [],
                        filters: [],
                        products: [],
                        sidebar_elements: [],
                        language_filter: null
                    };
                    
                    // Look for set/product listings
                    // Common selectors for product listings
                    const productElements = document.querySelectorAll(
                        '[class*="product"], [class*="set"], [class*="card"], [data-testid*="product"]'
                    );
                    console.log('Found', productElements.length, 'potential product elements');
                    
                    // Look for filter/sidebar elements
                    const filters = document.querySelectorAll('[class*="filter"], [class*="sidebar"], aside');
                    filters.forEach((filter, i) => {
                        if (filter.innerText?.length < 500) {
                            results.filters.push({
                                tag: filter.tagName,
                                class: filter.className.substring(0, 100),
                                text: filter.innerText.substring(0, 200)
                            });
                        }
                    });
                    
                    // Look for select elements that might filter by language or set
                    document.querySelectorAll('select').forEach((select, i) => {
                        const options = Array.from(select.querySelectorAll('option')).map(o => o.textContent.trim());
                        if (options.length > 2) {
                            results.filters.push({
                                type: 'select',
                                name: select.name,
                                options: options.slice(0, 15)
                            });
                        }
                    });
                    
                    // Look for links that might be sets
                    document.querySelectorAll('a').forEach((link, i) => {
                        const href = link.getAttribute('href') || '';
                        const text = link.textContent.trim();
                        
                        // Look for set-related links
                        if ((href.includes('set=') || href.includes('setName=') || 
                             text.toLowerCase().includes('set') ||
                             /[0-9]{4}|expansion|booster|box/.test(text)) &&
                            text.length > 0 && text.length < 100) {
                            
                            if (results.sets.length < 50) { // Limit results
                                results.sets.push({
                                    text: text,
                                    href: href.substring(0, 200)
                                });
                            }
                        }
                    });
                    
                    // Check for pagination
                    const pagination = document.querySelector('[class*="pagination"], [class*="pager"]');
                    if (pagination) {
                        results.pagination = pagination.innerText.substring(0, 200);
                    }
                    
                    // Look for language/region selector
                    document.querySelectorAll('input[type="radio"], button[class*="toggle"]').forEach(el => {
                        if (el.value?.toLowerCase().includes('english') || 
                            el.value?.toLowerCase().includes('japanese') ||
                            el.textContent?.toLowerCase().includes('english') ||
                            el.textContent?.toLowerCase().includes('japanese')) {
                            results.language_filter = results.language_filter || [];
                            results.language_filter.push(el.value || el.textContent.trim());
                        }
                    });
                    
                    return results;
                }
            """)
            
            print("\n📊 Analysis Results:")
            print(f"Page Title: {analysis.get('page_title')}")
            print(f"Found {len(analysis.get('sets', []))} set links")
            print(f"Found {len(analysis.get('filters', []))} filter elements")
            if analysis.get('language_filter'):
                print(f"Language filter: {analysis.get('language_filter')}")
            
            results["analysis"] = analysis
            
            # Save full HTML
            html = await page.content()
            with open("pokemon_sets_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: pokemon_sets_page.html")
            results["html_saved"] = "pokemon_sets_page.html"
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results
        with open("pokemon_page_analysis.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to pokemon_page_analysis.json")


if __name__ == "__main__":
    asyncio.run(inspect_pokemon_page())
