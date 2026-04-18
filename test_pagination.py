"""End-to-end CLI test with seller pagination."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import TCGPlayerScraper

async def test_cli_with_pagination():
    """Test the full scraper pipeline including pagination."""
    
    print("\n" + "="*80)
    print("POKESCRAPER - END-TO-END CLI TEST WITH PAGINATION")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    
    try:
        # Initialize
        print("\n[STEP 1] Initializing Playwright browser...")
        await scraper.setup()
        print("✓ Browser initialized")
        
        # Get games
        print("\n[STEP 2] Fetching available games...")
        games = await scraper.get_games()
        print(f"✓ Found {len(games)} games")
        print(f"  Sample games: {', '.join([g[0] for g in games[:3]])}")
        
        # Select first game (Pokemon if available)
        selected_idx = 0
        for i, (name, _) in enumerate(games):
            if "pok" in name.lower():
                selected_idx = i
                break
        
        selected_game_name, selected_game_url = games[selected_idx]
        print(f"\n[STEP 3] Selected game: {selected_game_name}")
        
        # Get sets
        print(f"\n[STEP 4] Fetching sets for {selected_game_name}...")
        sets_list = await scraper.get_sets(selected_game_url)
        print(f"✓ Found {len(sets_list)} sets")
        print(f"  Sample sets: {', '.join([s[0] for s in sets_list[:3]])}")
        
        # Select first set
        if not sets_list:
            print("✗ No sets found!")
            return
        
        selected_set_name, selected_set_url = sets_list[0]
        print(f"\n[STEP 5] Selected set: {selected_set_name}")
        
        # Scrape cards with seller data and pagination
        print(f"\n[STEP 6] Scraping cards with seller pagination...")
        print("  (Limiting to 2 cards for quick test)")
        
        cards_data = await scraper.scrape_set_price_guide(
            selected_set_name,
            selected_set_url,
            max_cards=2
        )
        
        cards = list(cards_data["cards"].values())
        print(f"✓ Scraped {len(cards)} cards")
        
        # Analyze results
        print("\n[STEP 7] Analyzing seller data...")
        print("-" * 80)
        
        total_sellers = 0
        cards_with_pagination = 0
        
        for idx, card in enumerate(cards, 1):
            card_name = card.get("name", "Unknown")
            sellers = card.get("sellers", [])
            seller_count = len(sellers)
            total_sellers += seller_count
            
            print(f"\nCard {idx}: {card_name}")
            print(f"  Sellers found: {seller_count}")
            
            if seller_count > 20:
                cards_with_pagination += 1
                print(f"  ✓ PAGINATION WORKED - Got more than 20 sellers!")
            elif seller_count > 0:
                print(f"  - Initial sellers only (no pagination triggered)")
            else:
                print(f"  ✗ No sellers found")
            
            # Show sample seller
            if sellers:
                sample = sellers[0]
                print(f"  Sample seller:")
                print(f"    Name: {sample.get('name')}")
                print(f"    Price: ${sample.get('price')}")
                print(f"    Reputation: {sample.get('reputation')}")
                print(f"    Sales: {sample.get('sales')}")
                print(f"    Condition: {sample.get('condition')}")
                print(f"    Shipping: {sample.get('shipping')}")
        
        # Summary
        print("\n" + "="*80)
        print("RESULTS SUMMARY")
        print("="*80)
        print(f"Total cards scraped: {len(cards)}")
        print(f"Total sellers extracted: {total_sellers}")
        if len(cards) > 0:
            print(f"Avg sellers per card: {total_sellers / len(cards):.1f}")
        print(f"Cards with pagination data: {cards_with_pagination}")
        
        if cards_with_pagination > 0:
            print("\n✓ SUCCESS - Pagination is working!")
        elif total_sellers > 0:
            print("\n⚠ Pagination may not have triggered (only visible sellers extracted)")
        else:
            print("\n✗ Failed to extract sellers")
        
        # Save detailed results
        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / "test_pagination_results.json"
        with open(output_file, "w") as f:
            json.dump({
                "game": selected_game_name,
                "set": selected_set_name,
                "cards": cards,
                "summary": {
                    "total_cards": len(cards),
                    "total_sellers": total_sellers,
                    "cards_with_pagination": cards_with_pagination,
                    "avg_sellers_per_card": total_sellers / len(cards) if len(cards) > 0 else 0
                }
            }, f, indent=2)
        
        print(f"\nDetailed results saved to: {output_file}")
        
        # Show JSON sample
        print("\n" + "="*80)
        print("JSON OUTPUT SAMPLE")
        print("="*80)
        if cards and cards[0].get("sellers"):
            sample_output = {
                "card": cards[0].get("name"),
                "sellers_sample": cards[0].get("sellers", [])[:3]
            }
            print(json.dumps(sample_output, indent=2))
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[STEP 8] Cleaning up...")
        await scraper.teardown()
        print("✓ Browser closed")
        print("\n" + "="*80)
        print("TEST COMPLETE")
        print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_cli_with_pagination())
