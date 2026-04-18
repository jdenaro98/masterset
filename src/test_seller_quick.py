import asyncio
import json
from datetime import datetime
from scraper import TCGPlayerScraper

async def main():
    print("\n" + "="*80)
    print("POKESCRAPER - SELLER EXTRACTION TEST")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    results = {"test_date": datetime.now().isoformat(), "status": "running"}
    
    try:
        print("\n[1] Setting up browser...")
        await scraper.setup()
        print("    ? Browser ready")
        
        print("\n[2] Getting games list...")
        games_list = await scraper.get_games()
        print(f"    ? Found {len(games_list)} games")
        results["games_found"] = len(games_list)
        
        # Find Pokemon
        pokemon_game = None
        pokemon_url = None
        for name, url in games_list:
            if "pok" in name.lower():
                pokemon_game = name
                pokemon_url = url
                break
        
        if pokemon_game:
            print(f"    Selected: {pokemon_game}")
            results["selected_game"] = pokemon_game
        else:
            pokemon_game = games_list[0][0]
            pokemon_url = games_list[0][1]
            print(f"    Selected: {pokemon_game} (first game)")
            results["selected_game"] = pokemon_game
        
        print("\n[3] Getting sets...")
        sets_list = await scraper.get_sets(pokemon_url)
        print(f"    ? Found {len(sets_list)} sets")
        results["sets_found"] = len(sets_list)
        
        if sets_list:
            set_name, set_url = sets_list[0]
            print(f"    Selected: {set_name}")
            results["selected_set"] = set_name
            
            print("\n[4] Scraping 3 cards with sellers...")
            cards_data = await scraper.scrape_set_price_guide(set_name, set_url, max_cards=3)
            cards = list(cards_data["cards"].values())
            print(f"    ? Scraped {len(cards)} cards")
            
            # Analyze results
            results["cards_scraped"] = len(cards)
            results["cards"] = []
            total_sellers = 0
            cards_with_sellers = 0
            
            for i, card in enumerate(cards, 1):
                card_name = card.get("name", "Unknown")
                sellers = card.get("sellers", [])
                print(f"\n    Card {i}: {card_name}")
                print(f"      Sellers: {len(sellers)}")
                
                card_info = {
                    "name": card_name,
                    "seller_count": len(sellers),
                    "sellers": []
                }
                
                if sellers:
                    cards_with_sellers += 1
                    total_sellers += len(sellers)
                    
                    for j, seller in enumerate(sellers[:3], 1):
                        print(f"        Seller {j}: {seller.get('name', 'N/A')} - ${seller.get('price', 'N/A')}")
                        card_info["sellers"].append({
                            "name": seller.get("name"),
                            "price": seller.get("price"),
                            "condition": seller.get("condition"),
                            "shipping": seller.get("shipping"),
                            "sales": seller.get("sales"),
                            "reputation": seller.get("reputation")
                        })
                
                results["cards"].append(card_info)
            
            results["total_sellers"] = total_sellers
            results["cards_with_sellers"] = cards_with_sellers
            results["status"] = "success"
            
            print("\n" + "="*80)
            print("SUMMARY:")
            print("="*80)
            print(f"Cards scraped: {len(cards)}")
            print(f"Cards with sellers: {cards_with_sellers}")
            print(f"Total sellers extracted: {total_sellers}")
            if cards_with_sellers > 0:
                print(f"Average sellers per card: {total_sellers/cards_with_sellers:.1f}")
            
    except Exception as e:
        print(f"\n? Error: {e}")
        import traceback
        traceback.print_exc()
        results["status"] = "error"
        results["error"] = str(e)
    finally:
        print("\n[5] Cleaning up...")
        await scraper.teardown()
        print("    ? Done")
    
    # Save results
    import os
    os.makedirs("../data", exist_ok=True)
    with open("../data/test_sellers_output.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: ../data/test_sellers_output.json")
    
    # Print JSON output
    print("\n" + "="*80)
    print("FULL JSON OUTPUT:")
    print("="*80)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
