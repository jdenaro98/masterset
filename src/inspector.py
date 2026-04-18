"""Inspector script to analyze TCGPlayer's structure and find selectors."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_homepage():
    """Inspect the TCGPlayer homepage to find games and structure."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Headless for automation
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        results = {
            "status": "in_progress",
            "homepage": {},
            "games": [],
            "errors": []
        }
        
        try:
            print("🔍 Navigating to TCGPlayer homepage...")
            results["log"] = "Navigating to TCGPlayer..."
            
            await page.goto(TCGPLAYER_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="tcgplayer_homepage.png")
            print("📸 Screenshot saved: tcgplayer_homepage.png")
            results["screenshot"] = "tcgplayer_homepage.png"
            
            # Comprehensive JavaScript analysis
            print("\n🔎 Analyzing page structure...")
            analysis = await page.evaluate("""
                () => {
                    const results = {
                        page_title: document.title,
                        url: window.location.href,
                        games: [],
                        navigation: [],
                        dropdowns: [],
                        search_elements: []
                    };
                    
                    // Method 1: Look for select elements with games
                    document.querySelectorAll('select').forEach((select, i) => {
                        const options = Array.from(select.querySelectorAll('option')).map(o => ({
                            text: o.textContent.trim(),
                            value: o.value
                        }));
                        if (options.length > 5) { // Likely a game selector
                            results.dropdowns.push({
                                selector: `select:nth-of-type(${i+1})`,
                                options: options.slice(0, 10),
                                total_options: options.length
                            });
                        }
                    });
                    
                    // Method 2: Look for any element mentioning games
                    const gameKeywords = ['pokemon', 'magic', 'yugioh', 'digimon', 'one piece', 'flesh and blood', 'lorcana'];
                    const bodyText = document.body.innerText.toLowerCase();
                    
                    gameKeywords.forEach(game => {
                        if (bodyText.includes(game)) {
                            results.games.push(game);
                        }
                    });
                    
                    // Method 3: Look for nav elements
                    document.querySelectorAll('header, nav, [role="navigation"]').forEach(el => {
                        if (el.innerText.length < 500) {
                            results.navigation.push({
                                tag: el.tagName,
                                class: el.className.substring(0, 100),
                                innerText: el.innerText.substring(0, 200)
                            });
                        }
                    });
                    
                    // Method 4: Look for search/filter inputs
                    document.querySelectorAll('input, button').forEach((el, i) => {
                        if (el.getAttribute('placeholder')?.toLowerCase().includes('search') ||
                            el.getAttribute('aria-label')?.toLowerCase().includes('game') ||
                            el.textContent?.toLowerCase().includes('game')) {
                            results.search_elements.push({
                                type: el.tagName,
                                id: el.id,
                                name: el.name,
                                placeholder: el.getAttribute('placeholder'),
                                class: el.className.substring(0, 100)
                            });
                        }
                    });
                    
                    return results;
                }
            """)
            
            print("\n📊 Analysis Results:")
            print(json.dumps(analysis, indent=2))
            results["analysis"] = analysis
            
            # Save the full page HTML
            html = await page.content()
            with open("tcgplayer_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: tcgplayer_page.html")
            results["html_saved"] = "tcgplayer_page.html"
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results to JSON
        with open("inspection_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to inspection_results.json")
        
        return results


if __name__ == "__main__":
    asyncio.run(inspect_homepage())
