import asyncio
import json
from playwright.async_api import async_playwright

async def debug_filter_application():
    """Debug the filter application process."""    

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

        print("\n" + "="*80)
        print("STEP 1: Analyzing initial page structure")
        print("="*80)

        # Get initial page state
        initial_analysis = await page.evaluate("""
            () => {
                let buttons = Array.from(document.querySelectorAll('button'));
                let productLineBtn = buttons.find(btn =>
                    btn.innerText && btn.innerText.trim() === 'Product Line'    
                );
                
                return {
                    total_buttons: buttons.length,
                    product_line_found: !!productLineBtn,
                    first_5_buttons: buttons.slice(0, 5).map(b => b.innerText.substring(0, 50))
                };
            }
        """)

        print(f"Found {initial_analysis['total_buttons']} buttons")
        print(f"Product Line button found: {initial_analysis['product_line_found']}")
        print(f"Sample buttons: {initial_analysis['first_5_buttons']}")

        print("\n" + "="*80)
        print("STEP 2: Clicking Product Line filter")
        print("="*80)

        # Click Product Line
        click_result = await page.evaluate("""
            () => {
                let buttons = Array.from(document.querySelectorAll('button'));  
                let productLineBtn = buttons.find(btn =>
                    btn.innerText && btn.innerText.trim() === 'Product Line'    
                );

                if (productLineBtn) {
                    productLineBtn.click();
                    return { success: true, text: productLineBtn.innerText.trim() };
                }
                return { success: false };
            }
        """)

        print(f"Clicked Product Line: {click_result['success']}")
        await asyncio.sleep(2)

        print("\n" + "="*80)
        print("STEP 3: Analyzing expanded filter options")
        print("="*80)

        # Get expanded filter options
        expanded_state = await page.evaluate("""
            () => {
                let labels = Array.from(document.querySelectorAll('label'));
                let pokemon_labels = labels.filter(l => 
                    l.innerText && l.innerText.toLowerCase().includes('pokemon')
                );
                
                return {
                    total_labels: labels.length,
                    pokemon_labels_found: pokemon_labels.length,
                    sample_labels: labels.slice(0, 10).map(l => l.innerText.substring(0, 80)),
                    pokemon_labels_text: pokemon_labels.map(l => l.innerText.substring(0, 100))
                };
            }
        """)

        print(f"Total labels found: {expanded_state['total_labels']}")
        print(f"Pokemon-related labels: {expanded_state['pokemon_labels_found']}")
        if expanded_state['pokemon_labels_text']:
            print(f"Pokemon labels:")
            for lbl in expanded_state['pokemon_labels_text']:
                print(f"  - {lbl}")
        else:
            print(f"Sample labels found:")
            for lbl in expanded_state['sample_labels'][:5]:
                print(f"  - {lbl}")

        print("\n" + "="*80)
        print("STEP 4: Attempting to find and click Pokemon filter")
        print("="*80)

        # Try to find and click Pokemon
        pokemon_click = await page.evaluate("""
            () => {
                let labels = Array.from(document.querySelectorAll('label'));
                let pokemon_label = labels.find(lbl =>
                    lbl.innerText && lbl.innerText.toLowerCase().includes('pokemon') &&
                    !lbl.innerText.toLowerCase().includes('international')
                );

                if (!pokemon_label) {
                    // Try any pokemon match
                    pokemon_label = labels.find(lbl =>
                        lbl.innerText && lbl.innerText.toLowerCase().includes('pokemon')
                    );
                }

                if (pokemon_label) {
                    pokemon_label.click();
                    return {
                        success: true, 
                        text: pokemon_label.innerText.trim(),
                        clicked: true
                    };
                }
                return { success: false, text: 'Pokemon label not found' };
            }
        """)

        print(f"Pokemon filter action: {pokemon_click}")
        await asyncio.sleep(3)

        print("\n" + "="*80)
        print("STEP 5: Looking for Set filter after Pokemon selection")
        print("="*80)

        # Get current page text to find Set section
        page_text = await page.evaluate("() => document.body.innerText")
        text_lines = page_text.split('\n')
        
        set_index = -1
        for i, line in enumerate(text_lines):
            if line.strip() == 'Set':
                set_index = i
                break
        
        if set_index >= 0:
            print(f"Found 'Set' section at line {set_index}")
            print("Lines around Set section:")
            for i in range(max(0, set_index - 2), min(len(text_lines), set_index + 30)):
                print(f"  {i}: {text_lines[i][:70]}")
        else:
            print("'Set' section not found in page text")

        print("\n" + "="*80)
        print("STEP 6: Extracting available sets for Pokemon")
        print("="*80)

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
                        console.log('Found Set section at line ' + i);
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

                return { sets: sets, total: sets.length };
            }
        """)

        print(f"\nFound {available_sets['total']} sets")
        if available_sets['sets']:
            print("Sample sets:")
            for i, s in enumerate(available_sets['sets'][:15], 1):
                print(f"  {i:2d}. {s}")
        else:
            print("No sets found in extracted data")

        print("\n" + "="*80)
        print("STEP 7: Final Results Summary")
        print("="*80)

        results = {
            "filter_clicked": click_result.get('success', False),
            "pokemon_filter_found": pokemon_click.get('success', False),
            "sets_extracted": available_sets['total'],
            "sets": available_sets['sets'],
            "debug_info": {
                "initial_buttons": initial_analysis['total_buttons'],
                "expanded_labels": expanded_state['total_labels'],
                "pokemon_labels": expanded_state['pokemon_labels_found']
            }
        }

        with open("pokemon_sets_debug_results.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to pokemon_sets_debug_results.json")
        print(f"\n? Filter clicked: {results['filter_clicked']}")
        print(f"? Pokemon found: {results['pokemon_filter_found']}")
        print(f"? Sets extracted: {results['sets_extracted']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_filter_application())
