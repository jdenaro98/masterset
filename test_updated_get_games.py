"""Test the updated get_games() method."""

import asyncio
import sys
from pathlib import Path

# Make sure we're in the src directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from scraper import TCGPlayerScraper

async def test_get_games():
    """Test the updated get_games method."""
    
    print("\n" + "="*80)
    print("POKESCRAPER - TESTING UPDATED get_games() METHOD")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    
    try:
        await scraper.setup()
        
        print("\n[1] Fetching games from product search grid...")
        games_list = await scraper.get_games()
        
        print(f"\n[2] Found {len(games_list)} games:\n")
        
        for idx, (game_name, game_url) in enumerate(games_list, 1):
            print(f"{idx:2}. {game_name}")
            print(f"    URL: {game_url}")
        
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total games found: {len(games_list)}")
        print(f"Game names: {', '.join([name for name, _ in games_list])}")
        
        # Verify all URLs are valid
        valid_urls = all(url.startswith(('/categories', 'https://')) for _, url in games_list)
        print(f"All URLs valid: {valid_urls}")
        
        if len(games_list) > 0:
            print("\n✓ Test PASSED - Games successfully extracted from product search grid")
        else:
            print("\n✗ Test FAILED - No games found")
        
    except Exception as e:
        print(f"\n✗ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.teardown()

if __name__ == "__main__":
    asyncio.run(test_get_games())
