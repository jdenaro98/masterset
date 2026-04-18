import json

with open('card_product_analysis.json') as f:
    data = json.load(f)

print("="*80)
print("INSPECTOR_PRODUCT_PAGE.PY EXECUTION SUMMARY")
print("="*80)

print("\n PAGE INFORMATION")
print("-" * 80)
print(f"URL: {data['page_url']}")
print(f"Page Title: {data['analysis']['page_title']}")
print(f"Card Name: {data['analysis']['card_name']}")
print(f"Screenshot: {data['screenshot']}")

print("\n SELLER DATA FOUND")
print("-" * 80)
text = data['analysis']['visible_text_sample']

# Extract seller info from text
sellers = []
i = 0
seen_sellers = set()
while i < len(text):
    if any(kw in text[i] for kw in ['Gaming', 'Showcase', 'Spa City']):
        if text[i] not in seen_sellers:
            seller = text[i]
            sales = text[i+1] if i+1 < len(text) else "N/A"
            condition = text[i+2] if i+2 < len(text) else "N/A"
            price = text[i+3] if i+3 < len(text) else "N/A"
            shipping = text[i+4] if i+4 < len(text) else "N/A"
            sellers.append({
                'name': seller,
                'sales': sales,
                'condition': condition,
                'price': price,
                'shipping': shipping
            })
            seen_sellers.add(seller)
    i += 1

for idx, seller in enumerate(sellers, 1):
    print(f"\n  Seller {idx}:")
    print(f"    Name: {seller['name']}")
    print(f"    Sales: {seller['sales']}")
    print(f"    Condition: {seller['condition']}")
    print(f"    Price: {seller['price']}")
    print(f"    Shipping: {seller['shipping']}")

print("\n" + "="*80)
print("ANALYSIS RESULTS")
print("-" * 80)
print(f"Total Visible Text Lines: {len(text)}")
print(f"Tables Found: {len(data['analysis']['all_tables'])}")
print(f"Conditions Found: {data['analysis']['conditions_found']}")
print(f"Seller Listings Detected: {data['seller_listings_found']}")
print(f"Status: {data['status']}")

print("\n" + "="*80)
print("ISSUES FOUND")
print("-" * 80)
if data['errors']:
    print(f"Total Errors: {len(data['errors'])}")
    for error in data['errors']:
        print(f"Error: {error[:200]}...")
else:
    print("No errors recorded")

print("\n" + "="*80)
print("TABLE ANALYSIS")
print("-" * 80)
for table in data['analysis']['all_tables']:
    print(f"\nTable {table['index']}: {table['rows']} rows, {table['cols']} cols")
    print(f"  Content: {table['text_preview'][:100]}...")

