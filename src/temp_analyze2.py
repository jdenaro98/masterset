import json

with open('card_product_analysis.json') as f:
    data = json.load(f)

print("="*80)
print("DETAILED SELLER STRUCTURE")
print("="*80)

# Get all text items
text = data['analysis']['visible_text_sample']
print(f"\nTotal visible text items: {len(text)}")

# Find seller listings pattern
print("\nSeller Listings Found (from visible text):")
i = 0
while i < len(text):
    if 'Gaming' in text[i] or 'Showcase' in text[i] or 'Spa City' in text[i]:
        # Print this seller block and next few items
        seller_name = text[i]
        print(f"\n--- Seller Block ---")
        print(f"1. Seller Name: {seller_name}")
        if i+1 < len(text):
            print(f"2. Sales Info: {text[i+1]}")
        if i+2 < len(text):
            print(f"3. Condition: {text[i+2]}")
        if i+3 < len(text):
            print(f"4. Price: {text[i+3]}")
        if i+4 < len(text):
            print(f"5. Shipping: {text[i+4]}")
        i += 5
    else:
        i += 1

print("\n" + "="*80)
print("PAGE ELEMENT STRUCTURE")
print("="*80)
print(f"Seller listings found: {data['seller_listings_found']}")
print(f"Seller table selectors: {data['seller_table_selectors']}")
print(f"Price elements found: {len(data['price_elements'])}")
print(f"Condition elements found: {len(data['condition_elements'])}")
print(f"Shipping elements found: {len(data['shipping_elements'])}")

print("\n" + "="*80)
print("PAGINATION INFO")
print("="*80)
print(f"Pagination: {data['pagination_info']}")

