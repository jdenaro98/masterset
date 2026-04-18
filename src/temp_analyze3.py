import json

with open('card_product_analysis.json') as f:
    data = json.load(f)

print("="*80)
print("JSON STRUCTURE KEYS")
print("="*80)
print("\nTop level keys:")
for key in data.keys():
    print(f"  - {key}: {type(data[key]).__name__}")

print("\n" + "="*80)
print("ANALYSIS SECTION KEYS")
print("="*80)
for key in data['analysis'].keys():
    val = data['analysis'][key]
    if isinstance(val, list):
        print(f"  - {key}: list ({len(val)} items)")
    else:
        print(f"  - {key}: {type(val).__name__}")

print("\n" + "="*80)
print("SAMPLE SELLERS")
print("="*80)
print(f"Seller listings: {data['analysis']['seller_listings']}")

print("\n" + "="*80)
print("PAGINATION")
print("="*80)
print(f"Pagination: {data['analysis']['pagination']}")

