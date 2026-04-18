"""Inspect TCGPlayer filters to understand Product Line and Set structure."""

import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_filters():
    """Inspect the TCGPlayer search page for filters."""
    
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
        
        print("Page loaded. Extracting filter information...")
        
        # Extract filter data
        filters_info = await page.evaluate("""
            () => {
                const filterInfo = {};
                
                // Look for filter elements (usually in sidebars or filter sections)
                const filterSections = document.querySelectorAll('[class*="filter"], [class*="Filter"], [role="group"]');
                console.log(`Found ${filterSections.length} potential filter sections`);
                
                // Try to find product line filter specifically
                const allText = document.body.innerText;
                const lines = allText.split('\\n');
                
                // Find "Product Line" section in the text
                let productLineIdx = -1;
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].includes('Product Line')) {
                        productLineIdx = i;
                        break;
                    }
                }
                
                if (productLineIdx >= 0) {
                    console.log(`Found "Product Line" at line ${productLineIdx}`);
                    // Get next 50 lines after Product Line
                    const productLineSection = lines.slice(productLineIdx, productLineIdx + 50).join('\\n');
                    filterInfo.productLineSection = productLineSection;
                }
                
                // Look for all filter labels
                const filterLabels = Array.from(document.querySelectorAll('label, [class*="label"]'))
                    .map(el => el.innerText?.trim())
                    .filter(text => text && text.length > 0 && text.length < 100)
                    .slice(0, 50);
                
                filterInfo.filterLabels = filterLabels;
                
                // Look for all option values/checkboxes
                const options = Array.from(document.querySelectorAll('input[type="checkbox"], span[class*="option"]'))
                    .map(el => ({
                        value: el.value || el.innerText?.trim(),
                        text: el.innerText?.trim() || el.getAttribute('title'),
                        type: el.tagName
                    }))
                    .filter(opt => opt.text && opt.text.length > 0 && opt.text.length < 100)
                    .slice(0, 100);
                
                filterInfo.options = options;
                
                return filterInfo;
            }
        """)
        
        print("\nFilter Information:")
        print(json.dumps(filters_info, indent=2))
        
        # Save full page text for analysis
        page_text = await page.evaluate("() => document.body.innerText")
        
        with open("filter_page_text.txt", "w") as f:
            f.write(page_text)
        
        print("\nFull page text saved to filter_page_text.txt")
        
        # Try to extract Product Line options specifically
        product_lines = await page.evaluate("""
            () => {
                const lines = [];
                const pageText = document.body.innerText;
                const textLines = pageText.split('\\n');
                
                // Find Product Line section
                let inProductLineSection = false;
                let lineCount = 0;
                
                for (let i = 0; i < textLines.length; i++) {
                    const line = textLines[i].trim();
                    
                    if (line === 'Product Line') {
                        inProductLineSection = true;
                        console.log(`Found Product Line section at line ${i}`);
                        continue;
                    }
                    
                    if (inProductLineSection) {
                        // Stop when we hit another filter section or end
                        if (line.includes('Rarity') || line.includes('Condition') || line.includes('Type') || line === '') {
                            if (lineCount > 5) break;
                        }
                        
                        // Skip headers and counts in parentheses
                        if (line && !line.includes('(') && line.length > 2 && line.length < 100) {
                            lines.push(line);
                            lineCount++;
                            if (lineCount > 50) break;
                        }
                    }
                }
                
                return lines;
            }
        """)
        
        print(f"\nProduct Lines found ({len(product_lines)}):")
        for idx, line in enumerate(product_lines, 1):
            print(f"{idx}. {line}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_filters())
