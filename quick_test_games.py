import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from scraper import TCGPlayerScraper

async def quick_test():
    print("\n" + "="*80)
    print("POKESCRAPER - QUICK GAMES TEST")
    print("="*80)
    
    scraper = TCGPlayerScraper()
    
    try:
        print("\n[Setting up browser...]")
        await scraper.setup()
        
        print("[Fetching games...]")
        games_list = await scraper.get_games()
        
        print(f"\n? SUCCESS - Found {len(games_list)} games\n")
        
        print("="*80)
        print("GAMES LIST")
        print("="*80)
        
        for idx, (name, url) in enumerate(games_list, 1):
            print(f"{idx}. {name}")
            print(f"   URL: {url}")
        
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total games: {len(games_list)}")
        print(f"Game names: {', '.join([name for name, _ in games_list])}")
        
    except Exception as e:
        print(f"\n? FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[Cleaning up...]")
        await scraper.teardown()

asyncio.run(quick_test())
