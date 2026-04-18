import asyncio
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from scraper import TCGPlayerScraper

async def test_price_guide():
    scraper = TCGPlayerScraper()
    try:
        print('=== Test 5: Price Guide Scraping ===')
        print('Setting up browser...')
        await scraper.setup()
        
        print('Getting games...')
        games = await scraper.get_games()
        print(f'Found {len(games)} games')
        
        # Get Pokemon sets
        pokemon_game = next((g for g in games if 'pokemon' in g[0].lower() and 'latest' not in g[0].lower()), None)
        if not pokemon_game:
            print('ERROR: No Pokemon game found')
            return False
        
        print(f'Found Pokemon game: {pokemon_game[0]}')
        print(f'Getting sets for {pokemon_game[0]}...')
        sets = await scraper.get_sets(pokemon_game[1], 'English')
        print(f'Found {len(sets)} English Pokemon sets')
        
        if not sets:
            print('ERROR: No sets found')
            return False
        
        # Test with first set
        set_name, set_url = sets[0]
        print(f'Testing scrape_set_price_guide for: {set_name}')
        print(f'URL: {set_url}')
        print('Scraping price guide...')
        
        card_data = await scraper.scrape_set_price_guide(set_name, set_url)
        
        print(f"Status: {card_data.get('status')}")
        print(f"Total cards found: {card_data.get('metadata', {}).get('total_cards')}")
        print(f"Cards extracted: {len(card_data.get('cards', []))}")
        
        if card_data.get('cards'):
            print(f"First card sample: Name={card_data['cards'][0].get('name')}, Price={card_data['cards'][0].get('price')}")
        
        return True
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            await scraper.teardown()
        except Exception as e:
            print(f'Teardown error: {e}')

asyncio.run(test_price_guide())
