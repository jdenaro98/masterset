import asyncio
import json
import sys
from pathlib import Path

# Make sure we're in the src directory
sys.path.insert(0, str(Path(__file__).parent))

from scraper import TCGPlayerScraper

async def test_seller_extraction():
    """Test seller extraction with a quick sample"""
    
    print("\n" + "="*80)
    print("POKESCRAPER - SELLER EXTRACTION TEST")
    print("="*80)
    
    # Initialize scraper
    print("\n[1] Initializing TCGPlayerScraper...")
    scraper = TCGPlayerScraper()
    
    try:
        await scraper.setup()
        
        # Get games
        print("[2] Fetching available games...")
        games_list = await scraper.get_games()
        print(f"    Found {len(games_list)} games")
        
        # Display games
        for i, (game_name, game_url) in enumerate(games_list[:5]):
            print(f"    {i}: {game_name}")
        
        # Select first game (Pokemon if available)
        pokemon_idx = None
        for i, (name, _) in enumerate(games_list):
            if "pok" in name.lower():
                pokemon_idx = i
                break
        
        if pokemon_idx is not None:
            selected_idx = pokemon_idx
        else:
            selected_idx = 0
        
        selected_game_name, selected_game_url = games_list[selected_idx]
        print(f"\n[3] Selected game: {selected_game_name}")
        
        # Get sets for this game
        print(f"[4] Fetching sets for {selected_game_name}...")
        sets_list = await scraper.get_sets(selected_game_url)
        print(f"    Found {len(sets_list)} sets")
        
        # Display first few sets
        for i, (set_name, set_url) in enumerate(sets_list[:3]):
            print(f"    {i}: {set_name}")
        
        # Select first set
        if sets_list:
            selected_set_name, selected_set_url = sets_list[0]
            print(f"\n[5] Selected set: {selected_set_name}")
            
            # Get cards from this set (limit to first 3)
            print(f"[6] Scraping cards from {selected_set_name}...")
            cards_data = await scraper.scrape_set_price_guide(
                selected_set_name,
                selected_set_url,
                max_cards=3
            )
            
            cards = list(cards_data["cards"].values())
            print(f"    Scraped {len(cards)} cards")
            
            # Verify seller data
            results = {
                "game": selected_game_name,
                "set": selected_set_name,
                "cards": cards,
                "validation": {
                    "total_cards": len(cards),
                    "cards_with_sellers": 0,
                    "total_sellers": 0,
                    "seller_fields_valid": 0,
                    "errors": []
                }
            }
            
            print(f"\n[7] Validating seller data...")
            required_fields = ["name", "price"]
            optional_fields = ["reputation", "sales", "condition", "shipping"]
            
            for card_idx, card in enumerate(cards):
                card_name = card.get("name", "Unknown")
                print(f"\n    Card {card_idx + 1}: {card_name}")
                
                sellers = card.get("sellers", [])
                if sellers:
                    results["validation"]["cards_with_sellers"] += 1
                    results["validation"]["total_sellers"] += len(sellers)
                    print(f"    Sellers found: {len(sellers)}")
                    
                    # Check first seller's fields
                    if sellers:
                        first_seller = sellers[0]
                        has_required = all(f in first_seller for f in required_fields)
                        fields_present = [f for f in (required_fields + optional_fields) if f in first_seller]
                        
                        print(f"    Sample seller: {first_seller.get('name', 'N/A')}")
                        print(f"    Fields present: {', '.join(fields_present)}")
                        print(f"    Data: name={first_seller.get('name')}, price=${first_seller.get('price')}, sales={first_seller.get('sales')}")
                        
                        if has_required:
                            results["validation"]["seller_fields_valid"] += 1
                            print(f"    ? All required fields present")
                        else:
                            missing = [f for f in required_fields if f not in first_seller]
                            print(f"    ? Missing required fields: {missing}")
                else:
                    results["validation"]["errors"].append({
                        "card": card_name,
                        "issue": "No sellers found"
                    })
                    print(f"    ? No sellers extracted")
            
            # Create output directory if needed
            output_dir = Path("data")
            output_dir.mkdir(exist_ok=True)
            
            # Save results
            output_file = output_dir / "test_sellers_output.json"
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            
            print(f"\n[8] Results saved to: {output_file}")
            
            # Print summary
            print("\n" + "="*80)
            print("VALIDATION SUMMARY")
            print("="*80)
            val = results["validation"]
            print(f"Total cards scraped: {val['total_cards']}")
            print(f"Cards with sellers: {val['cards_with_sellers']}")
            print(f"Total sellers extracted: {val['total_sellers']}")
            if val['cards_with_sellers'] > 0:
                print(f"Avg sellers per card: {val['total_sellers'] / val['cards_with_sellers']:.1f}")
            print(f"Cards with all required fields valid: {val['seller_fields_valid']}")
            
            if val["errors"]:
                print(f"\nErrors found: {len(val['errors'])}")
                for error in val["errors"]:
                    print(f"  - {error['card']}: {error['issue']}")
            else:
                print("\n? No errors found - all sellers extracted successfully!")
            
            print("\n" + "="*80)
            print("JSON OUTPUT SAMPLE (First card with sellers):")
            print("="*80)
            
            for card in cards:
                if card.get("sellers"):
                    sample = {
                        "card_name": card.get("name"),
                        "sellers_sample": card.get("sellers", [])[:2]
                    }
                    print(json.dumps(sample, indent=2))
                    break
        else:
            print("No sets found!")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[9] Cleaning up...")
        await scraper.teardown()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(test_seller_extraction())
