"""Inspector to analyze TCGPlayer product/card page structure and seller listings."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TCGPLAYER_BASE_URL


async def inspect_card_product_page():
    """Inspect a card product page to understand seller listing structure."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        results = {
            "status": "in_progress",
            "page_url": "",
            "page_title": "",
            "card_info": {},
            "seller_structure": {},
            "seller_listings_found": 0,
            "pagination_info": {},
            "sample_sellers": [],
            "page_elements": {},
            "errors": []
        }
        
        try:
            # Use a real card product URL from our test data
            card_url = "https://www.tcgplayer.com/product/686601/magic-secrets-of-strixhaven-emeritus-of-ideation"
            print(f"🔍 Navigating to: {card_url}")
            results["page_url"] = card_url
            
            await page.goto(card_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            # Save a screenshot
            await page.screenshot(path="card_product_page.png")
            print("📸 Screenshot saved: card_product_page.png")
            results["screenshot"] = "card_product_page.png"
            
            # Analyze the page structure
            print("\n🔎 Analyzing card product page structure...")
            analysis = await page.evaluate("""
                () => {
                    const results = {
                        page_title: document.title,
                        card_name: null,
                        card_info: {},
                        seller_listings: [],
                        seller_table_selectors: [],
                        price_elements: [],
                        condition_elements: [],
                        shipping_elements: [],
                        pagination: null,
                        all_tables: [],
                        all_lists: []
                    };
                    
                    // Get card name from page
                    const h1 = document.querySelector('h1');
                    if (h1) {
                        results.card_name = h1.innerText?.trim();
                    }
                    
                    // Look for seller table/listing container
                    const tables = document.querySelectorAll('table');
                    console.log('Found', tables.length, 'tables');
                    tables.forEach((table, idx) => {
                        results.all_tables.push({
                            index: idx,
                            rows: table.querySelectorAll('tr').length,
                            cols: table.querySelectorAll('th').length,
                            text_preview: table.innerText?.substring(0, 300)
                        });
                    });
                    
                    // Look for list structures
                    const lists = document.querySelectorAll('ul, ol');
                    console.log('Found', lists.length, 'lists');
                    
                    // Look for any container that might hold sellers
                    const containers = document.querySelectorAll('[class*="seller"], [class*="listing"], [class*="offer"], [class*="price"]');
                    console.log('Found', containers.length, 'seller-related elements');
                    
                    // Look for specific data fields
                    const priceSpans = document.querySelectorAll('[class*="price"], [class*="cost"], span');
                    console.log('Found', priceSpans.length, 'price-related elements');
                    
                    // Search for condition text
                    const pageText = document.body.innerText;
                    const conditionMatches = pageText.match(/(?:near mint|lightly played|moderately played|heavily played|damaged|psa \\d+)/gi) || [];
                    results.conditions_found = [...new Set(conditionMatches)];
                    
                    // Get all visible text to understand structure
                    const lines = pageText.split('\\n').filter(line => line.trim().length > 5 && line.trim().length < 200);
                    results.visible_text_sample = lines.slice(0, 100);
                    
                    // Look for key headers/labels
                    results.headers = [];
                    document.querySelectorAll('h1, h2, h3, h4, [class*="header"], [class*="title"]').forEach(el => {
                        const text = el.innerText?.trim();
                        if (text && text.length > 0 && text.length < 100) {
                            results.headers.push(text);
                        }
                    });
                    
                    return results;
                }
            """)
            
            print(f"\n📊 Analysis Results:")
            print(f"Page Title: {analysis.get('page_title')}")
            print(f"Card Name: {analysis.get('card_name')}")
            print(f"Tables found: {len(analysis.get('all_tables', []))}")
            if analysis.get('all_tables'):
                print(f"  First table: {analysis['all_tables'][0]['rows']} rows, {analysis['all_tables'][0]['cols']} cols")
            print(f"Conditions found: {analysis.get('conditions_found', [])}")
            print(f"Headers detected:")
            for header in analysis.get('headers', [])[:15]:
                print(f"  - {header}")
            
            print(f"\nFirst 40 visible text lines:")
            for i, line in enumerate(analysis.get('visible_text_sample', [])[:40], 1):
                print(f"  {i:2d}. {line}")
            
            results["analysis"] = analysis
            
            # Now test selector patterns to find seller rows
            print("\n🔍 Testing selector patterns for seller listings...")
            selector_results = await page.evaluate("""
                () => {
                    const results = {};
                    
                    const selectors = [
                        'tr',
                        'tbody tr',
                        '[class*="row"]',
                        '[class*="seller"]',
                        '[class*="offer"]',
                        '[class*="listing"]',
                        'div[class*="card"]',
                        '[data-testid*="seller"]',
                        '[data-testid*="offer"]',
                        'li',
                        'article'
                    ];
                    
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            const samples = [];
                            for (let i = 0; i < Math.min(2, elements.length); i++) {
                                samples.push({
                                    text: elements[i].innerText?.substring(0, 300),
                                    html_classes: elements[i].className?.substring(0, 200),
                                    html_tag: elements[i].tagName
                                });
                            }
                            results[selector] = {
                                count: elements.length,
                                samples: samples
                            };
                        }
                    });
                    
                    return results;
                }
            """)
            
            print("\nSelector Test Results:")
            for selector, result in selector_results.items():
                if result.get('count', 0) > 0:
                    print(f"  ✅ {selector}: {result['count']} elements")
                    if result['samples']:
                        print(f"     Sample text: {result['samples'][0]['text'][:100]}...")
            
            results["selector_results"] = selector_results
            
            # Save full HTML
            html = await page.content()
            with open("card_product_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n💾 Full page HTML saved: card_product_page.html")
            
            results["status"] = "success"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results["status"] = "error"
            results["errors"].append(str(e))
        finally:
            await browser.close()
        
        # Save results
        with open("card_product_analysis.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print("\n✅ Results saved to card_product_analysis.json")


if __name__ == "__main__":
    asyncio.run(inspect_card_product_page())
