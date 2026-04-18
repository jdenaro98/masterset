import asyncio
import json
from playwright.async_api import async_playwright

async def better_inspect_filters():
    """Better inspection of TCGPlayer filters with proper element targeting."""

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
        await page.wait_for_timeout(2000)  # Extra wait for filters to render

        print("Page loaded. Extracting detailed filter information...\n")

        # Use a more sophisticated JavaScript to find filters
        filter_data = await page.evaluate("""
            () => {
                const result = {
                    filterSections: [],
                    productLineOptions: [],
                    filterElements: {}
                };

                // Method 1: Look for data attributes containing filter info
                const filterButtons = document.querySelectorAll('button, div[role="button"]');
                console.log(`Found ${filterButtons.length} button/clickable elements`);

                // Method 2: Find common filter label patterns
                const allLabels = document.querySelectorAll('label, legend, h3, h4');
                for (const label of allLabels) {
                    const text = label.innerText?.trim();
                    if (text && (text.includes('Product Line') || text.includes('Line'))) {
                        console.log('Found Product Line label:', text);
                        // Get the parent container of this label
                        let container = label.closest('fieldset, div[class*="filter"], section');
                        if (container) {
                            const inputs = container.querySelectorAll('input[type="checkbox"]');
                            const options = Array.from(inputs).map((inp, idx) => {
                                const labelEl = inp.nextElementSibling || inp.parentElement.querySelector('label');
                                return {
                                    text: labelEl?.innerText?.trim() || inp.value || `Option ${idx}`,
                                    value: inp.value,
                                    checked: inp.checked
                                };
                            });
                            result.productLineOptions = options;
                        }
                    }
                }

                // Method 3: Look through all visible text for product line context
                const bodyText = document.body.innerText;
                const lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

                // Find filters section
                let filterIdx = lines.findIndex(l => l.includes('Product Line') || l.includes('product line'));
                if (filterIdx >= 0) {
                    console.log(`Found Product Line reference at text line ${filterIdx}`);
                    result.productLineSectionText = lines.slice(filterIdx, filterIdx + 100);
                }

                // Method 4: Find data in script tags or attributes
                const scripts = document.querySelectorAll('script[type="application/json"], script[data-*]');
                console.log(`Found ${scripts.length} JSON script tags`);

                // Method 5: Check for React/Vue component state
                const divs = document.querySelectorAll('div[class*="Product"], div[class*="product"], div[class*="Filter"], div[class*="filter"]');
                for (const div of divs) {
                    const key = Object.keys(div).find(k => k.startsWith('__react') || k.startsWith('__vue'));
                    if (key && div[key]?.memoizedProps) {
                        result.filterElements[div.className] = 'Has framework data';
                    }
                }

                return result;
            }
        """);

        print("Filter Analysis Results:")
        print("=" * 80)
        
        if filter_data.get('productLineOptions'):
            print(f"\n? Found {len(filter_data['productLineOptions'])} Product Line Options:")
            for i, opt in enumerate(filter_data['productLineOptions'], 1):
                print(f"  {i}. {opt['text']} (value: {opt['value']})")
        else:
            print("\n? No Product Line options found in standard filter elements")

        if filter_data.get('productLineSectionText'):
            print(f"\n? Product Line Section Text ({len(filter_data['productLineSectionText'])} lines):")
            for line in filter_data['productLineSectionText'][:30]:
                print(f"  {line}")

        # Try clicking on Product Line to expand it
        print("\n" + "=" * 80)
        print("Attempting to click and expand Product Line filter...\n")

        # Find and click any element containing "Product Line"
        try:
            # Look for clickable elements with Product Line text
            await page.click('text=Product Line', timeout=5000)
            await page.wait_for_timeout(1000)
            print("? Clicked Product Line filter")
            
            # Now extract visible options
            expanded_options = await page.evaluate("""
                () => {
                    const lines = [];
                    const pageText = document.body.innerText;
                    const textLines = pageText.split('\\n');
                    
                    let inProductLineSection = false;
                    let emptyLineCount = 0;
                    
                    for (let i = 0; i < textLines.length; i++) {
                        const line = textLines[i].trim();
                        
                        if (line === 'Product Line') {
                            inProductLineSection = true;
                            continue;
                        }
                        
                        if (inProductLineSection) {
                            if (line === '') {
                                emptyLineCount++;
                                if (emptyLineCount > 2) break;
                                continue;
                            }
                            emptyLineCount = 0;
                            
                            // Filter out certain patterns
                            if (!line.includes('(') && !line.includes('Set') && !line.includes('Type') 
                                && line.length > 2 && line.length < 150) {
                                lines.push(line);
                                if (lines.length > 100) break;
                            }
                        }
                    }
                    
                    return lines;
                }
            """);

            print(f"\n? Expanded Product Line section shows {len(expanded_options)} items:\n")
            for i, line in enumerate(expanded_options[:50], 1):
                print(f"  {i:2d}. {line}")
                
        except Exception as e:
            print(f"? Could not click Product Line filter: {e}")

        await browser.close()

asyncio.run(better_inspect_filters())
