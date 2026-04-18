"""Inspector to deeply analyze price guide page structure."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_price_guide_detailed():
    """Deeply analyze price guide structure to find correct selectors."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        results = {
            "status": "in_progress",
            "page_url": "",
            "selectors_tested": [],
            "cards_found_by_selector": {},
            "page_structure": {},
            "errors": []
        }
        
        try:
            # Navigate to a specific set's category page
            url = f"{TCGPLAYER_BASE_URL}/categories/trading-and-collectible-card-games/magic-the-gathering/secrets-of-strixhaven"
            print(f"🔍 Navigating to: {url}")
            results["page_url"] = url
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="price_guide_detailed.png")
            print("📸 Screenshot saved: price_guide_detailed.png")
            
            # Try many different selectors
            print("\n🔎 Testing different selectors to find cards...")
            selectors_to_test = [
                # By class patterns
                "[class*='product-line']",
                "[class*='product']",
                "[class*='card']",
                "[class*='listing']",
                "div[class*='grid']",
                "li[class*='product']",
                "article[class*='product']",
                
                # By data attributes
                "[data-testid*='product']",
                "[data-id]",
                "[data-product]",
                
                # By role
                "[role='row']",
                "[role='article']",
                
                # Generic
                "tbody > tr",
                ".product-card",
                "[id*='product']",
            ]
            
            analysis = await page.evaluate("""
                (selectorsToTest) => {
                    const results = {};
                    
                    // Test each selector
                    selectorsToTest.forEach(selector => {
                        try {
                            const elements = document.querySelectorAll(selector);
                            results[selector] = {
                                count: elements.length,
                                samples: []
                            };
                            
                            // Get samples
                            for (let i = 0; i < Math.min(2, elements.length); i++) {
                                const el = elements[i];
                                results[selector].samples.push({
                                    tagName: el.tagName,
                                    class: el.className.substring(0, 100),
                                    text: el.innerText?.substring(0, 200) || el.textContent?.substring(0, 200),
                                    html: el.outerHTML.substring(0, 300)
                                });
                            }
                        } catch (e) {
                            results[selector] = { error: e.message };
                        }
                    });
                    
                    return results;
                }
            """, selectors_to_test)
            
            # Filter results showing which selectors found elements
            print("\n📊 Selector Test Results:")
            for selector, result in analysis.items():
                if result.get('count', 0) > 0:
                    print(f"  ✅ {selector}: Found {result['count']} elements")
                    results["cards_found_by_selector"][selector] = result['count']
            
            # Get full page structure
            print("\n📋 Analyzing full page structure...")
            structure = await page.evaluate("""
                () => {
                    const analysis = {
                        title: document.title,
                        totalElements: document.querySelectorAll('*').length,
                        mainContainers: [],
                        allClasses: []
                    };
                    
                    // Find main content containers
                    const containers = document.querySelectorAll('[class*="container"], [class*="main"], [class*="content"], section, main');
                    containers.forEach(container => {
                        if (container.innerText?.length > 100 && container.innerText?.length < 5000) {
                            analysis.mainContainers.push({
                                tag: container.tagName,
                                class: container.className.substring(0, 80),
                                childCount: container.children.length,
                                textLength: container.innerText?.length
                            });
                        }
                    });
                    
                    // Get all unique classes on the page
                    document.querySelectorAll('[class]').forEach(el => {
                        el.className.split(' ').forEach(cls => {
                            if (cls.length > 3 && !analysis.allClasses.includes(cls)) {
                                analysis.allClasses.push(cls);
                            }
                        });
                    });
                    
                    // Find pagination
                    const pagination = document.querySelector('[class*="pagina"]');
                    analysis.pagination = pagination ? pagination.innerText?.substring(0, 100) : null;
                    
                    // Find price/cost elements
                    const prices = document.querySelectorAll('[class*="price"], [class*="cost"], [class*="$"]');
                    analysis.priceElements = prices.length;
                    
                    // Sample visible text
                    const bodyText = document.body.innerText;
                    const lines = bodyText.split('\\n').filter(line => line.trim().length > 10 && line.trim().length < 150);
                    analysis.sampleLines = lines.slice(10, 40);
                    
                    return analysis;
                }
            """)
            
            print(f"  Page Title: {structure.get('title')}")
            print(f"  Total Elements: {structure.get('totalElements')}")
            print(f"  Main Containers Found: {len(structure.get('mainContainers', []))}")
            print(f"  Price Elements Found: {structure.get('priceElements')}")
            print(f"  Unique Classes: {len(structure.get('allClasses', []))}")
            
            results["page_structure"] = structure
            results["selectors_tested"] = analysis
            
            # Save full HTML
            html = await page.content()
            with open("price_guide_detailed.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: price_guide_detailed.html")
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results
        with open("price_guide_detailed_analysis.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to price_guide_detailed_analysis.json")


if __name__ == "__main__":
    asyncio.run(inspect_price_guide_detailed())
