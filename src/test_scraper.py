"""Test script to verify scraper functionality."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import TCGPlayerScraper


async def test_scraper():
    """Test the scraper functionality."""
    scraper = TCGPlayerScraper()
    
    try:
        print("=" * 60)
        print("  Starting TCGPlayer Scraper Tests")
        print("=" * 60)
        
        # Setup
        print("\n1️⃣  Setting up browser...")
        await scraper.setup()
        print("   ✅ Browser setup complete")
        
        # Test 1: Get games
        print("\n2️⃣  Testing game discovery...")
        games = await scraper.get_games()
        print(f"   ✅ Found {len(games)} games:")
        for i, (name, url) in enumerate(games, 1):
            print(f"      {i}. {name}")
            print(f"         URL: {url[:80]}...")
        
        if not games:
            print("   ❌ No games found!")
            return False
        
        # Test 2: Get sets for first game
        print(f"\n3️⃣  Testing set discovery for {games[0][0]}...")
        sets = await scraper.get_sets(games[0][1])
        print(f"   ✅ Found {len(sets)} sets:")
        for i, (name, url) in enumerate(sets[:5], 1):
            print(f"      {i}. {name}")
            print(f"         URL: {url[:80]}...")
        if len(sets) > 5:
            print(f"      ... and {len(sets) - 5} more")
        
        if not sets:
            print("   ❌ No sets found!")
            return False
        
        # Test 3: Test Pokemon language selection
        if any("pokemon" in name.lower() for name, _ in games):
            print(f"\n4️⃣  Testing Pokemon language selection...")
            pokemon_game = next((g for g in games if "pokemon" in g[0].lower()), None)
            if pokemon_game:
                # Test English
                english_sets = await scraper.get_sets(pokemon_game[1], "English")
                print(f"   ✅ Found {len(english_sets)} English Pokemon sets")
                
                # Test Japanese
                japanese_sets = await scraper.get_sets(pokemon_game[1], "Japanese")
                print(f"   ✅ Found {len(japanese_sets)} Japanese Pokemon sets")
        
        # Test 4: Test price guide scraping (just first few cards)
        if games and sets:
            print(f"\n5️⃣  Testing price guide scraping for {sets[0][0]}...")
            print("   ⏳ This may take a minute...")
            card_data = await scraper.scrape_set_price_guide(sets[0][0], sets[0][1])
            print(f"   ✅ Scraped {card_data['metadata']['total_cards']} cards")
            
            # Save test output
            filename = f"test_output_{sets[0][0].replace(' ', '_').lower()}.json"
            await scraper.save_data(card_data, filename)
            print(f"   ✅ Saved to data/{filename}")
        
        print("\n" + "=" * 60)
        print("  ✅ All Tests Passed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\nCleaning up...")
        await scraper.teardown()
        print("✅ Done")


if __name__ == "__main__":
    result = asyncio.run(test_scraper())
    sys.exit(0 if result else 1)
