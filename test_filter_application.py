"""Test applying Product Line filter to get Set options."""

import asyncio
import json
from playwright.async_api import async_playwright

async def test_filter_application():
    """Test applying a Product Line filter and extracting available sets."""
    
    # Start with base URL
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
        
        print("Page loaded. Looking for filter options...")
        
        # Extract text to understand structure
        page_text = await page.evaluate("() => document.body.innerText")
        
        # Find Product Line button and click it
        print("\n[1] Finding and clicking Product Line filter...")
        click_result = await page.evaluate("""
            () => {
                let buttons = Array.from(document.querySelectorAll('button'));
                let productLineBtn = buttons.find(btn => 
                    btn.innerText && btn.innerText.trim() === 'Product Line'
                );
                
                if (productLineBtn) {
                    console.log('Found Product Line button');
                    productLineBtn.click();
                    return {
                        found: true,
                        clicked: true
                    };
                }
                return { found: false };
            }
        """)
        
        print(f"Click result: {click_result}")
        
        # Wait for filter to expand
        await asyncio.sleep(2)
        
        # Look for "Pokemon" checkbox to click
        print("\n[2] Finding and clicking Pokemon filter...")
        pokemon_click = await page.evaluate("""
            () => {
                // Look for checkboxes or labels
                let inputs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                let labels = Array.from(document.querySelectorAll('label'));
                
                console.log(`Found ${inputs.length} checkboxes, ${labels.length} labels`);
                
                // Find Pokemon checkbox or label
                let pokemonCheck = inputs.find(inp => 
                    inp.value && (inp.value.toLowerCase().includes('pokemon') || 
                    inp.getAttribute('aria-label')?.toLowerCase().includes('pokemon'))
                );
                
                let pokemonLabel = labels.find(lbl => 
                    lbl.innerText && lbl.innerText.toLowerCase().includes('pokemon')
                );
                
                if (pokemonLabel) {
                    console.log('Found Pokemon label:', pokemonLabel.innerText);
                    pokemonLabel.click();
                    return { found: true, type: 'label', text: pokemonLabel.innerText };
                }
                
                if (pokemonCheck) {
                    console.log('Found Pokemon checkbox');
                    pokemonCheck.click();
                    return { found: true, type: 'checkbox', value: pokemonCheck.value };
                }
                
                return { found: false };
            }
        """)
        
        print(f"Pokemon click result: {pokemon_click}")
        
        # Wait for page to update with Pokemon-only results
        await asyncio.sleep(3)
        
        # Now look for Set filter and extract available sets
        print("\n[3] Extracting available Sets...")
        available_sets = await page.evaluate("""
            () => {
                const sets = [];
                const pageText = document.body.innerText;
                const textLines = pageText.split('\\n').map(l => l.trim());
                
                let inSetSection = false;
                let foundCount = 0;
                
                for (let i = 0; i < textLines.length; i++) {
                    if (textLines[i] === 'Set') {
                        inSetSection = true;
                        console.log('Found Set section');
                        continue;
                    }
                    
                    if (inSetSection) {
                        // Stop markers
                        if (textLines[i] === 'Product Type' || textLines[i] === 'Condition' ||
                            textLines[i].includes('results') || foundCount > 100) {
                            break;
                        }
                        
                        // Valid set entries
                        if (textLines[i] && textLines[i].length > 2 && textLines[i].length < 150 &&
                            !textLines[i].match(/^\\d+$/) && !textLines[i].includes('(')) {
                            sets.push(textLines[i]);
                            foundCount++;
                        }
                    }
                }
                
                return sets;
            }
        """)
        
        print(f"\nFound {len(available_sets)} sets:")
        for idx, set_name in enumerate(available_sets[:30], 1):
            print(f"  {idx}. {set_name}")
        
        # Save results
        with open("pokemon_sets_via_filter.json", "w") as f:
            json.dump({
                "product_line": "Pokemon",
                "total_sets_found": len(available_sets),
                "sets": available_sets
            }, f, indent=2)
        
        print(f"\nResults saved to pokemon_sets_via_filter.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_filter_application())
