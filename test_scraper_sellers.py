import json
import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import the scraper
from pokescraper import PokeScraper

def test_seller_extraction():
    """Test seller extraction with a quick sample"""
    
    print("\n" + "="*80)
    print("POKESCRAPER - SELLER EXTRACTION TEST")
    print("="*80)
    
    # Initialize scraper
    print("\n[1] Initializing PokeScraper...")
    scraper = PokeScraper()
    
    # Get games
    print("[2] Fetching available games...")
    try:
        games = scraper.get_games()
        print(f"    Found {len(games)} games")
        
        # Display games
        for i, game in enumerate(games[:5]):
            print(f"    {i}: {game}")
        
        # Select Pokemon (should be first)
        selected_game = games[0]
        print(f"\n[3] Selected game: {selected_game}")
        
        # Get sets for this game
        print(f"[4] Fetching sets for {selected_game}...")
        sets = scraper.get_sets(selected_game)
        print(f"    Found {len(sets)} sets")
        
        # Display first few sets
        for i, set_name in enumerate(sets[:3]):
            print(f"    {i}: {set_name}")
        
        # Select first set
        selected_set = sets[0]
        print(f"\n[5] Selected set: {selected_set}")
        
        # Get cards for this set (limit to first 3)
        print(f"[6] Fetching cards from {selected_set}...")
        cards = scraper.get_cards(selected_game, selected_set, limit=3)
        print(f"    Fetched {len(cards)} cards")
        
        # Verify seller data
        results = {
            "game": selected_game,
            "set": selected_set,
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
        required_fields = ["name", "reputation", "sales", "condition", "price", "shipping"]
        
        for card_idx, card in enumerate(cards):
            print(f"\n    Card {card_idx + 1}: {card.get('name', 'Unknown')}")
            
            sellers = card.get("sellers", [])
            if sellers:
                results["validation"]["cards_with_sellers"] += 1
                results["validation"]["total_sellers"] += len(sellers)
                print(f"    Sellers found: {len(sellers)}")
                
                # Check first seller's fields
                if sellers:
                    first_seller = sellers[0]
                    fields_present = [f for f in required_fields if f in first_seller]
                    print(f"    Sample seller fields: {', '.join(fields_present)}")
                    
                    if len(fields_present) == len(required_fields):
                        results["validation"]["seller_fields_valid"] += 1
                        print(f"    ? All fields present in first seller")
                    else:
                        missing = [f for f in required_fields if f not in first_seller]
                        print(f"    ? Missing fields: {', '.join(missing)}")
                        results["validation"]["errors"].append({
                            "card": card.get("name"),
                            "issue": f"Missing fields: {missing}"
                        })
            else:
                results["validation"]["errors"].append({
                    "card": card.get("name"),
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
        print(f"Avg sellers per card: {val['total_sellers'] / max(val['cards_with_sellers'], 1):.1f}")
        print(f"Cards with all fields valid: {val['seller_fields_valid']}")
        
        if val["errors"]:
            print(f"\nErrors found: {len(val['errors'])}")
            for error in val["errors"]:
                print(f"  - {error['card']}: {error['issue']}")
        else:
            print("\n? No errors found - all sellers extracted successfully!")
        
        print("\n" + "="*80)
        print("JSON OUTPUT SAMPLE (First card, first 2 sellers):")
        print("="*80)
        
        if cards and cards[0].get("sellers"):
            sample = {
                "card_name": cards[0].get("name"),
                "sellers_sample": cards[0].get("sellers", [])[:2]
            }
            print(json.dumps(sample, indent=2))
        
        return results
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_seller_extraction()
