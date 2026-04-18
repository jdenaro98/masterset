import asyncio
import json
from playwright.async_api import async_playwright

async def correct_pokemon_filter():
    """Correctly click on the Pokemon product line (not a product type)."""    

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
        await asyncio.sleep(2)

        print("="*80)
        print("METHOD 1: Use text-based navigation to find and click Pokemon")
        print("="*80)

        # Let's use the page's own navigation by finding the Pokemon link directly
        # Navigate directly to Pokemon's search URL
        pokemon_url = "https://www.tcgplayer.com/search/pokemon/product?view=grid"
        print(f"\nNavigating directly to Pokemon URL: {pokemon_url}\n")
        
        await page.goto(pokemon_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        print("="*80)
        print("AFTER POKEMON FILTER APPLIED")
        print("="*80)

        # Check the page content for Set filter section
        page_content = await page.evaluate("() => document.body.innerText")
        lines = page_content.split('\n')

        print(f"\nTotal lines in page: {len(lines)}")
        print("Looking for key sections:")

        # Find key sections
        set_idx = -1
        product_type_idx = -1
        condition_idx = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == 'Set':
                set_idx = i
                print(f"  ? Set filter found at line {i}")
            elif stripped == 'Product Type':
                product_type_idx = i
                print(f"  ? Product Type filter found at line {i}")
            elif stripped == 'Condition':
                condition_idx = i
                print(f"  ? Condition filter found at line {i}")

        if set_idx >= 0:
            print(f"\n? Found SET FILTER SECTION! Extracting sets...\n")
            print("Lines from Set section (next 50 lines):")
            for i in range(set_idx, min(set_idx + 50, len(lines))):
                print(f"  {i-set_idx:2d}: {lines[i]}")
        else:
            print(f"\n? Set section not found. First 150 lines of page:")
            for i, line in enumerate(lines[:150]):
                if line.strip():
                    print(f"  {i}: {line[:80]}")

        print("\n" + "="*80)
        print("EXTRACTING SETS FOR POKEMON")
        print("="*80)

        available_sets = await page.evaluate("""
            () => {
                const sets = [];
                const pageText = document.body.innerText;
                const textLines = pageText.split('\\n').map(l => l.trim());     

                let inSetSection = false;
                let setCount = 0;

                for (let i = 0; i < textLines.length; i++) {
                    // Look for Set section
                    if (textLines[i] === 'Set') {
                        inSetSection = true;
                        console.log('Found Set section at line ' + i);
                        continue;
                    }

                    if (inSetSection) {
                        // Stop markers
                        if (textLines[i] === 'Product Type' || 
                            textLines[i] === 'Condition' ||
                            textLines[i] === 'Rarity' ||
                            textLines[i].includes('All Filters') ||
                            setCount > 150) {
                            console.log('Stopping at line ' + i);
                            break;
                        }

                        // Skip empty lines
                        if (!textLines[i]) {
                            continue;
                        }

                        // Look for valid set names
                        // Sets usually have length > 2 but < 150, no parentheses (those are usually counts)
                        // and they're not "View all" type links
                        if (textLines[i].length > 2 && 
                            textLines[i].length < 150 &&
                            !textLines[i].match(/^\\d+$/) && 
                            !textLines[i].includes('(') &&
                            !textLines[i].includes('View') &&
                            !textLines[i].includes('filter') &&
                            textLines[i].charAt(0) !== '?' &&
                            textLines[i] !== 'Set') {
                            
                            sets.push(textLines[i]);
                            setCount++;
                        }
                    }
                }

                console.log('Total sets extracted: ' + sets.length);
                return { sets: sets, total: sets.length };
            }
        """)

        print(f"\nExtracted {available_sets['total']} sets:\n")
        
        if available_sets['sets']:
            for i, set_name in enumerate(available_sets['sets'], 1):
                print(f"  {i:3d}. {set_name}")
        else:
            print("  No sets extracted")

        # Save results
        results = {
            "method": "Direct URL navigation to pokemon URL",
            "url_used": pokemon_url,
            "sets_found": available_sets['total'],
            "sets": available_sets['sets'][:50],  # Save first 50
            "summary": {
                "success": available_sets['total'] > 0,
                "sets_with_filter": available_sets['total']
            }
        }

        with open("pokemon_sets_via_filter.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Results saved to pokemon_sets_via_filter.json")
        print(f"{'='*80}")
        print(f"\nSUMMARY:")
        print(f"  Sets found for Pokemon: {available_sets['total']}")
        print(f"  Status: {'SUCCESS ?' if available_sets['total'] > 0 else 'FAILED ?'}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(correct_pokemon_filter())
