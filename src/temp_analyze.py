import json
with open('card_product_analysis.json') as f:
    data = json.load(f)

print('='*80)
print('PAGE STRUCTURE ANALYSIS')
print('='*80)
print(f"Page Title: {data['analysis']['page_title']}")
print(f"Card Name: {data['analysis']['card_name']}")
print(f"Conditions Found: {data['analysis']['conditions_found']}")
print(f"Total Tables: {len(data['analysis']['all_tables'])}")

print()
print('='*80)
print('TABLE STRUCTURES')
print('='*80)
for t in data['analysis']['all_tables'][:3]:
    print(f"Table {t['index']}: {t['rows']} rows, {t['cols']} cols")
    print(f"  Text: {t['text_preview'][:80]}...")

print()
print('='*80)
print('SELLER DATA FROM VISIBLE TEXT')
print('='*80)
text = data['analysis']['visible_text_sample']
seller_info = [x for x in text if any(kw in x for kw in ['Listings', 'Sold by', 'Gaming', 'Sales)', 'Showcase', '$', 'Shipping'])]
for item in seller_info[-30:]:
    print(f"  {item}")

print()
print('='*80)
print('ERROR STATUS')
print('='*80)
print(f"Status: {data['status']}")
if data['errors']:
    print(f"Errors: {len(data['errors'])}")
    print(f"First error: {data['errors'][0][:100]}")
