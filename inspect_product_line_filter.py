"""Extract Product Line filter options from TCGPlayer."""

import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_product_line_filter():
    """Extract all Product Line options from the filter."""
    
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
        
        print("Page loaded. Looking for Product Line filter...")
        
        # Try to find and click the Product Line filter button to expand it
        product_line_filter = await page.evaluate("""
            () => {
                const allText = document.body.innerText;
                const lines = allText.split('\\n').map(l => l.trim());
                
                // Find all elements that might contain product line options
                const result = {
                    productLines: [],
                    filterElements: []
                };
                
                // Method 1: Look for button or label containing "Product Line"
                let buttons = Array.from(document.querySelectorAll('button, label, div[role="button"]'));
                let productLineBtn = buttons.find(btn => 
                    btn.innerText && btn.innerText.includes('Product Line')
                );
                
                if (productLineBtn) {
                    result.productLineButton = {
                        text: productLineBtn.innerText,
                        tagName: productLineBtn.tagName,
                        class: productLineBtn.className
                    };
                }
                
                // Method 2: Look through the page text systematically
                let inProductLineSection = false;
                let sectionContent = [];
                
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i] === 'Product Line') {
                        inProductLineSection = true;
                        continue;
                    }
                    
                    if (inProductLineSection) {
                        // Stop at next section header
                        if (lines[i] === 'Set' || lines[i] === 'Product Type' || lines[i] === 'Condition' || 
                            lines[i] === 'Rarity' || lines[i].includes('results')) {
                            break;
                        }
                        
                        // Collect non-empty lines
                        if (lines[i] && lines[i].length > 0 && !lines[i].match(/^\\d+$/) && 
                            !lines[i].startsWith('(')) {
                            sectionContent.push(lines[i]);
                        }
                    }
                }
                
                result.productLines = sectionContent;
                
                return result;
            }
        """)
        
        print(f"\nProduct Line Filter Info:")
        print(json.dumps(product_line_filter, indent=2))
        
        # Try clicking the Product Line filter to expand it if it's collapsed
        await page.evaluate("""
            () => {
                // Find elements that might be filter toggles
                let buttons = Array.from(document.querySelectorAll('button'));
                let productLineBtn = buttons.find(btn => 
                    btn.innerText && btn.innerText.includes('Product Line')
                );
                
                if (productLineBtn) {
                    console.log('Found Product Line button, clicking...');
                    productLineBtn.click();
                }
            }
        """)
        
        # Wait a bit for filter to expand
        await asyncio.sleep(2)
        
        # Extract product lines again after potential expansion
        product_lines_expanded = await page.evaluate("""
            () => {
                const lines = [];
                const pageText = document.body.innerText;
                const textLines = pageText.split('\\n').map(l => l.trim());
                
                let inProductLineSection = false;
                let foundCount = 0;
                
                for (let i = 0; i < textLines.length; i++) {
                    if (textLines[i] === 'Product Line') {
                        inProductLineSection = true;
                        continue;
                    }
                    
                    if (inProductLineSection) {
                        // Stop markers
                        if (textLines[i] === 'Set' || textLines[i] === 'Product Type' || 
                            textLines[i].includes('results') || textLines[i] === '') {
                            if (foundCount > 5) break;
                        }
                        
                        // Valid product line entries
                        if (textLines[i] && textLines[i].length > 2 && textLines[i].length < 100 &&
                            !textLines[i].match(/^\\d+$/) && !textLines[i].includes('(')) {
                            lines.push(textLines[i]);
                            foundCount++;
                            if (foundCount > 150) break;
                        }
                    }
                }
                
                return lines;
            }
        """)
        
        print(f"\nProduct Lines extracted ({len(product_lines_expanded)}):")
        for idx, line in enumerate(product_lines_expanded[:120], 1):
            print(f"{idx}. {line}")
        
        # Save to file
        with open("product_lines_from_filter.json", "w") as f:
            json.dump({
                "total_found": len(product_lines_expanded),
                "product_lines": product_lines_expanded,
                "filter_info": product_line_filter
            }, f, indent=2)
        
        print(f"\nResults saved to product_lines_from_filter.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_product_line_filter())
