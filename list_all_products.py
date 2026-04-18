import json

with open("product_lines.json") as f:
    data = json.load(f)

product_lines = data["product_lines"]

print("\n" + "="*100)
print("ALL 76 PRODUCT LINES EXTRACTED FROM TCGPLAYER")
print("="*100)

# Group by category
categories = {}
for i, line in enumerate(product_lines, 1):
    url = line["url"]
    
    # Determine game category
    if "/magic-the-gathering/" in url:
        cat = "Magic: The Gathering"
    elif "/yugioh/" in url:
        cat = "Yu-Gi-Oh!"
    elif "/pokemon-japan/" in url:
        cat = "Pokemon (Japan)"
    elif "/pokemon/" in url:
        cat = "Pokemon"
    elif "/disney-lorcana/" in url:
        cat = "Disney Lorcana"
    else:
        cat = "Multi-Game/General"
    
    if cat not in categories:
        categories[cat] = []
    categories[cat].append((i, line))

# Print by category
for cat in sorted(categories.keys()):
    print(f"\n{cat.upper()} ({len(categories[cat])} items)")
    print("-" * 100)
    for idx, line in categories[cat]:
        print(f"  {idx:2}. {line['name']}")

print("\n" + "="*100 + "\n")

