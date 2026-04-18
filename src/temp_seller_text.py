import json

with open('card_product_analysis.json') as f:
    data = json.load(f)

# Show last 50 text items which should contain seller listing information
text = data['analysis']['visible_text_sample']
print("FULL SELLER LISTING SECTION (last 50 text items):")
print("="*80)
for i, item in enumerate(text[-50:], start=len(text)-50):
    print(f"{i:3d}: {item}")

