import json

files = [
    'data/cli_test_pokémon_secrets_of_strixhaven.json',
    'data/cli_test_hololive_official_card_game_secrets_of_strixhaven.json'
]

for fpath in files:
    print(f'\n' + '='*80)
    print(f'FILE: {fpath}')
    print('='*80)
    try:
        with open(fpath) as f:
            data = json.load(f)
        
        print(f'Set: {data["metadata"]["set"]}')
        print(f'Total Cards: {data["metadata"]["total_cards"]}')
        print(f'Scraped At: {data["metadata"]["scraped_at"]}')
        
        print(f'\nCards:')
        for card_name, card_data in data['cards'].items():
            sellers = card_data.get('sellers', [])
            print(f'  {card_name}: {len(sellers)} sellers')
            if sellers:
                sample = sellers[0]
                print(f'    Sample: {sample["name"]} - ${sample["price"]} + ${sample["shipping"]} shipping')
    except Exception as e:
        print(f'Error reading file: {e}')
