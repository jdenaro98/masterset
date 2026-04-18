"""Automated CLI flow test with user input simulation."""

import asyncio
import json
import sys
from pathlib import Path
from io import StringIO

# Add src directory to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from cli import CLI
from scraper import TCGPlayerScraper

async def test_cli_flow():
    """Test the complete CLI flow with automated selections."""

    print("\n" + "="*80)
    print("POKESCRAPER - CLI FLOW TEST WITH AUTOMATION")
    print("="*80)

    cli = CLI()
    scraper = TCGPlayerScraper()

    try:
        # Step 1: Initialize
        print("\n[1] INITIALIZING SCRAPER")
        print("-" * 80)
        cli.print_header("TCGPlayer Web Scraper")

        await scraper.setup()
        print("? Playwright browser initialized")

        # Step 2: Fetch games
        print("\n[2] FETCHING GAMES")
        print("-" * 80)
        cli.display_message("Fetching available games...", "info")
        games = await scraper.get_games()
        print(f"? Found {len(games)} games")
        print(f"  Games: {', '.join([g[0] for g in games[:5]])}, ...")

        # Step 3: Select game (automated)
        print("\n[3] GAME SELECTION (AUTOMATED)")
        print("-" * 80)
        game_names = [name for name, _ in games]

        # Find Pokemon if available, otherwise use first game
        selected_idx = 0
        for i, name in enumerate(game_names):
            if "pok" in name.lower():
                selected_idx = i + 1  # Menu is 1-indexed
                break

        if selected_idx == 0:
            selected_idx = 1
            
        selected_game_name, selected_game_url = games[selected_idx - 1]
        print(f"? Selected: {selected_game_name}")
        print(f"  Game #{selected_idx} from menu")

        # Step 4: Language selection (if Pokemon)
        print("\n[4] LANGUAGE SELECTION (if applicable)")
        print("-" * 80)
        selected_language = None
        if "pokemon" in selected_game_name.lower():
            selected_language = "English"
            print(f"? Selected: {selected_language}")
        else:
            print("(Not applicable for this game)")

        # Step 5: Fetch sets
        print("\n[5] FETCHING SETS")
        print("-" * 80)
        cli.display_message(f"Fetching sets for {selected_game_name}...", "info")
        sets_list = await scraper.get_sets(selected_game_url, selected_language)
        print(f"? Found {len(sets_list)} sets")
        print(f"  Sets: {', '.join([s[0] for s in sets_list[:5]])}, ...")       

        # Step 6: Select set (automated)
        print("\n[6] SET SELECTION (AUTOMATED)")
        print("-" * 80)
        if sets_list:
            selected_set_name, selected_set_url = sets_list[0]
            print(f"? Selected: {selected_set_name}")
            print(f"  Set #1 from menu")
        else:
            print("? No sets found!")
            return

        # Step 7: Scrape with limited cards
        print("\n[7] SCRAPING CARDS WITH SELLERS")
        print("-" * 80)
        print("Note: Limiting to 3 cards for quick test")
        print("(Scraping with seller extraction and pagination)")

        cards_data = await scraper.scrape_set_price_guide(
            selected_set_name,
            selected_set_url,
            max_cards=3
        )

        cards = list(cards_data["cards"].values())
        print(f"? Scraped {len(cards)} cards with sellers")

        # Step 8: Verify data
        print("\n[8] DATA VERIFICATION")
        print("-" * 80)

        total_sellers = 0
        all_have_sellers = True

        for idx, card in enumerate(cards, 1):
            name = card.get("name", "Unknown")
            sellers = card.get("sellers", [])
            seller_count = len(sellers)
            total_sellers += seller_count

            print(f"  Card {idx}: {name}")
            print(f"    Sellers: {seller_count}")

            if not sellers:
                all_have_sellers = False
            else:
                # Show sample seller
                sample = sellers[0]
                print(f"    Sample: {sample.get('name')} @ ${sample.get('price')} (Shipping: ${sample.get('shipping')} or Included)")

        # Step 9: Save results
        print("\n[9] SAVING RESULTS")
        print("-" * 80)

        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)

        filename = f"cli_test_{selected_game_name}_{selected_set_name}".replace(" ", "_").replace(":", "").lower()
        filename = filename + ".json"

        await scraper.save_data(cards_data, filename)
        print(f"? Saved to: data/{filename}")

        # Step 10: Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Game: {selected_game_name}")
        print(f"Set: {selected_set_name}")
        print(f"Cards Scraped: {len(cards)}")
        print(f"Total Sellers: {total_sellers}")
        if len(cards) > 0:
            print(f"Avg Sellers/Card: {total_sellers / len(cards):.1f}")        
        print(f"All cards have sellers: {'? YES' if all_have_sellers else '? NO'}")

        # Status
        if all_have_sellers and total_sellers > 0:
            print("\n? CLI TEST PASSED - Full pipeline working correctly!")   
        else:
            print("\n? CLI TEST FAILED - Issues detected")

        print("\n" + "="*80)

        # Show JSON structure
        print("\nJSON OUTPUT STRUCTURE:")
        print("-" * 80)

        if cards:
            sample_card = {
                "name": cards[0].get("name"),
                "url": cards[0].get("url"),
                "sellers_count": len(cards[0].get("sellers", [])),
                "sample_sellers": cards[0].get("sellers", [])[:2]
            }
            print(json.dumps(sample_card, indent=2))

    except Exception as e:
        print(f"\n? ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[10] CLEANUP")
        print("-" * 80)
        await scraper.teardown()
        print("? Browser closed")
        print("\nCLI FLOW TEST COMPLETE\n")

if __name__ == "__main__":
    asyncio.run(test_cli_flow())
