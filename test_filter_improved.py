import asyncio
import json
from playwright.async_api import async_playwright

async def improved_filter_test():
    """Improved filter test that better identifies the Pokemon product line."""    

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

        print("\nSTEP 1: Click Product Line filter")
        await page.evaluate("""
            () => {
                let buttons = Array.from(document.querySelectorAll('button'));  
                let productLineBtn = buttons.find(btn =>
                    btn.innerText && btn.innerText.trim() === 'Product Line'    
                );
                if (productLineBtn) productLineBtn.click();
            }
        """)
        await asyncio.sleep(2)

        print("STEP 2: Get all labels and find the Pokemon product line option")
        
        # Extract all labels with their characteristics
        all_labels = await page.evaluate("""
            () => {
                let labels = Array.from(document.querySelectorAll('label'));
                return labels.map((lbl, idx) => ({
                    index: idx,
                    text: lbl.innerText.substring(0, 100),
                    has_checkbox: !!lbl.querySelector('input[type="checkbox"]'),
                    parent_text: lbl.parentElement?.innerText?.substring(0, 200) || ''
                }));
            }
        """)

        # Look for Pokemon product line entries (should be near the beginning, likely with a checkbox)
        print(f"Total labels found: {len(all_labels)}")
        print("\nLooking for 'Pokemon' specifically as a product line (first 100):")
        pokemon_matches = []
        for lbl in all_labels[:100]:
            if 'pokemon' in lbl['text'].lower() and lbl['has_checkbox']:
                print(f"  [{lbl['index']}] {lbl['text']} (has checkbox)")
                pokemon_matches.append(lbl)
        
        if not pokemon_matches:
            print("  No checkboxed Pokemon labels found in first 100. Searching all...")
            for lbl in all_labels:
                if lbl['text'].lower().strip() == 'pokemon':
                    print(f"  [{lbl['index']}] {lbl['text']} (has checkbox: {lbl['has_checkbox']})")
                    pokemon_matches.append(lbl)

        print(f"\nFound {len(pokemon_matches)} Pokemon matches")

        print("\nSTEP 3: Click the Pokemon product line checkbox")
        
        # Now click the correct Pokemon checkbox
        pokemon_result = await page.evaluate("""
            () => {
                let labels = Array.from(document.querySelectorAll('label'));
                
                // Strategy 1: Find a label with ONLY "Pokemon" text
                let pokemonLabel = labels.find(lbl => 
                    lbl.innerText && lbl.innerText.trim() === 'Pokemon'
                );
                
                // Strategy 2: If not found, look for label closest to just pokemon
                if (!pokemonLabel) {
                    pokemonLabel = labels.find(lbl =>
                        lbl.innerText && lbl.innerText.trim().length <= 20 &&
                        lbl.innerText.toLowerCase().includes('pokemon') &&
                        !lbl.innerText.includes(':') &&
                        !lbl.innerText.includes('Card') &&
                        !lbl.innerText.includes('Sleeves') &&
                        !lbl.innerText.includes('Box') &&
                        !lbl.innerText.includes('Playmat')
                    );
                }

                if (pokemonLabel) {
                    let checkbox = pokemonLabel.querySelector('input[type="checkbox"]');
                    if (checkbox) {
                        checkbox.click();
                        return { success: true, text: pokemonLabel.innerText.trim(), via: 'checkbox' };
                    } else {
                        pokemonLabel.click();
                        return { success: true, text: pokemonLabel.innerText.trim(), via: 'label' };
                    }
                }
                
                return { success: false, text: 'Pokemon product line not found' };
            }
        """)

        print(f"Click result: {pokemon_result}")
        await asyncio.sleep(3)

        print("\nSTEP 4: Check for Set filter section")
        
        # Look for Set section or any filter that appeared
        page_content = await page.evaluate("() => document.body.innerText")
        lines = page_content.split('\n')
        
        # Check if we got Pokemon-filtered results
        results_found = False
        set_section_found = False
        
        for i, line in enumerate(lines):
            if 'result' in line.lower() or 'product' in line.lower():
                print(f"Line {i}: {line[:80]}")
                results_found = True
            if line.strip() == 'Set':
                set_section_found = True
                print(f"\n? Found Set section at line {i}")
                print("Next 20 lines from Set section:")
                for j in range(i, min(i + 20, len(lines))):
                    print(f"  {lines[j]}")
                break

        if not set_section_found:
            print("? Set section not found")
            print("\nShowing page structure (first 100 lines):")
            for i, line in enumerate(lines[:100]):
                if line.strip():
                    print(f"  {i}: {line[:70]}")

        print("\nSTEP 5: Extract Sets if available")
        
        available_sets = await page.evaluate("""
            () => {
                const sets = [];
                const pageText = document.body.innerText;
                const textLines = pageText.split('\\n').map(l => l.trim());     

                let inSetSection = false;

                for (let i = 0; i < textLines.length; i++) {
                    if (textLines[i] === 'Set') {
                        inSetSection = true;
                        continue;
                    }

                    if (inSetSection) {
                        if (textLines[i] === 'Product Type' || textLines[i] === 'Condition') {
                            break;
                        }

                        if (textLines[i] && textLines[i].length > 2 && textLines[i].length < 150 &&
                            !textLines[i].match(/^\\d+$/) && !textLines[i].includes('(')) {
                            sets.push(textLines[i]);
                            if (sets.length > 50) break;
                        }
                    }
                }

                return sets;
            }
        """)

        print(f"Extracted {len(available_sets)} sets")
        if available_sets:
            for i, s in enumerate(available_sets[:20], 1):
                print(f"  {i:2d}. {s}")

        # Save results
        results = {
            "pokemon_filter_applied": pokemon_result.get('success', False),
            "sets_found": len(available_sets),
            "sets": available_sets,
            "summary": {
                "total_labels_analyzed": len(all_labels),
                "set_section_found": set_section_found,
                "results_section_found": results_found
            }
        }

        with open("pokemon_sets_improved.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n? Results saved to pokemon_sets_improved.json")
        print(f"\nFINAL SUMMARY:")
        print(f"  - Pokemon filter applied: {pokemon_result.get('success')}")
        print(f"  - Sets extracted: {len(available_sets)}")
        if available_sets:
            print(f"  - Sample sets: {available_sets[:3]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(improved_filter_test())
