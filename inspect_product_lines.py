import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_product_lines():
    """Inspect and extract Product Line filter options from TCGPlayer."""

    url = "https://www.tcgplayer.com/search/all/product?view=grid"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        print(f"Navigating to {url}\n")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)      
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        print("=" * 80)
        print("TCGPLAYER FILTER INSPECTION REPORT")
        print("=" * 80)

        # Step 1: Find all filter-related text and elements
        print("\n[1] Looking for filter sections and labels...\n")
        
        filter_info = await page.evaluate("""
            () => {
                const result = {
                    allText: [],
                    filterElements: []
                };

                const bodyText = document.body.innerText;
                const lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                
                // Look for all lines that might be filter-related
                const filterKeywords = ['Product Line', 'Set', 'Type', 'Condition', 'Rarity'];
                let filterStart = -1;
                
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].includes('Product Line')) {
                        filterStart = i;
                        break;
                    }
                }
                
                if (filterStart >= 0) {
                    result.allText = lines.slice(filterStart, filterStart + 150);
                }
                
                // Also find any clickable/interactive elements
                const buttons = document.querySelectorAll('button, [role="button"]');
                for (const btn of buttons) {
                    const text = btn.innerText?.trim();
                    if (text && (text.includes('Product') || text.includes('Line'))) {
                        result.filterElements.push({
                            text: text,
                            tagName: btn.tagName,
                            role: btn.getAttribute('role')
                        });
                    }
                }
                
                return result;
            }
        """);

        if filter_info['allText']:
            print(f"Found {len(filter_info['allText'])} text lines from filter area:")
            for i, line in enumerate(filter_info['allText'][:40], 1):
                print(f"  {i:2d}. {line}")
        
        if filter_info['filterElements']:
            print(f"\n\nFound {len(filter_info['filterElements'])} filter-related elements:")
            for elem in filter_info['filterElements']:
                print(f"  - {elem['text']} (tag: {elem['tagName']}, role: {elem['role']})")

        # Step 2: Try clicking on Product Line filter button
        print("\n" + "=" * 80)
        print("[2] Attempting to expand Product Line filter...\n")
        
        try:
            # Find the Product Line button or label
            await page.click('button:has-text("Product Line")', timeout=5000)
            print("? Clicked on Product Line filter")
            await page.wait_for_timeout(1000)
        except:
            print("? Could not click with has-text selector, trying alternative...")
            try:
                # Try with just text selector
                await page.click('text="Product Line"', timeout=5000)
                print("? Clicked on Product Line filter (using text selector)")
                await page.wait_for_timeout(1000)
            except:
                print("? Could not click Product Line filter")

        # Step 3: Extract visible options after expansion
        print("\n[3] Extracting Product Line options...\n")
        
        product_lines = await page.evaluate("""
            () => {
                const lines = document.body.innerText.split('\\n').map(l => l.trim()).filter(l => l);
                
                let foundProductLine = false;
                let options = [];
                let consecutiveEmpty = 0;
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    
                    if (line === 'Product Line') {
                        foundProductLine = true;
                        continue;
                    }
                    
                    if (foundProductLine) {
                        // Stop conditions
                        if (line === 'Set' || line === 'Product Type' || line === 'Rarity') {
                            if (consecutiveEmpty > 1) break;
                        }
                        
                        if (line === '') {
                            consecutiveEmpty++;
                            if (consecutiveEmpty > 3) break;
                            continue;
                        }
                        
                        consecutiveEmpty = 0;
                        
                        // Collect lines that look like product line names
                        // Exclude lines with parentheses (counts) and certain keywords
                        if (!line.includes('(') && 
                            line !== 'All' && 
                            line !== 'Set' && 
                            line !== 'Type' &&
                            line.length > 2 && 
                            line.length < 150) {
                            options.push(line);
                            
                            if (options.length > 100) break;
                        }
                    }
                }
                
                return options;
            }
        """);

        print(f"Product Line Options Found: {len(product_lines)}\n")
        print("-" * 80)
        for i, line in enumerate(product_lines, 1):
            print(f"  {i:3d}. {line}")
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Product Lines extracted: {len(product_lines)}")
        print(f"Filter page accessible: Yes")
        print(f"Product Line section found: {'Yes' if product_lines else 'No'}")
        
        await browser.close()

asyncio.run(inspect_product_lines())
