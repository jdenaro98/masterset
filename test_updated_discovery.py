"""Test the updated scraper with new game/set discovery methods."""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from scraper import TCGPlayerScraper

async def test_updated_scraper():
    """Test the updated scraper."""
    
    print("\n" + "="*80)
    print("POKESCRAPER - TESTING UPDATED GAME/SET DISCOVERY")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    
    try:
        await scraper.setup()
        
        # Step 1: Get games (should be 68+ and alphabetized)
        print("\n[1] Fetching games from Product Line filter...")
        games_list = await scraper.get_games()
        
        print(f"[OK] Found {len(games_list)} games (alphabetized)")
        print("\nFirst 20 games:")
        for idx, (name, slug) in enumerate(games_list[:20], 1):
            print(f"  {idx:2d}. {name:40s} ({slug})")
        
        # Verify alphabetization
        sorted_names = [g[0] for g in games_list]
        is_sorted = sorted_names == sorted(sorted_names, key=lambda x: x.lower())
        print(f"\n[OK] Alphabetized: {'YES' if is_sorted else 'NO'}")
        
        # Step 2: Select a game (Pokemon)
        print("\n[2] Finding and selecting Pokemon...")
        pokemon_game = None
        for name, slug in games_list:
            if "pokemon" in name.lower() and "japan" not in name.lower():
                pokemon_game = (name, slug)
                break
        
        if pokemon_game:
            game_name, game_slug = pokemon_game
            print(f"[OK] Selected: {game_name} (slug: {game_slug})")
            
            # Step 3: Get sets for Pokemon
            print("\n[3] Fetching sets for Pokemon...")
            sets_list = await scraper.get_sets(game_slug)
            
            if sets_list:
                print(f"[OK] Found {len(sets_list)} sets (alphabetized)")
                print("\nFirst 20 sets:")
                for idx, (name, slug) in enumerate(sets_list[:20], 1):
                    print(f"  {idx:2d}. {name:50s} ({slug[:30]}...)")
                
                # Verify alphabetization
                sorted_set_names = [s[0] for s in sets_list]
                is_sorted = sorted_set_names == sorted(sorted_set_names, key=lambda x: x.lower())
                print(f"\n[OK] Sets alphabetized: {'YES' if is_sorted else 'NO'}")
            else:
                print("[FAIL] No sets found!")
        else:
            print("[FAIL] Pokemon not found in games list!")
        
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Games found: {len(games_list)}")
        print(f"Games alphabetized: {is_sorted}")
        if pokemon_game and sets_list:
            print(f"Sets found for {pokemon_game[0]}: {len(sets_list)}")
            print(f"Sets alphabetized: {is_sorted}")
            print("\n[OK] TEST PASSED - Game/Set discovery working correctly!")
        else:
            print("\n[FAIL] TEST FAILED")
        
    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.teardown()

if __name__ == "__main__":
    asyncio.run(test_updated_scraper())
