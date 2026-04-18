import json

with open("product_lines.json") as f:
    data = json.load(f)

product_lines = data["product_lines"]

print("\n" + "="*90)
print("POKESCRAPER - PRODUCT LINES EXTRACTION REPORT")
print("="*90)

print(f"\nSOURCE URL: {data['url']}")
print(f"TOTAL PRODUCT LINES FOUND: {data['total_found']}")

# Analyze by game type
game_types = {}
for line in product_lines:
    url = line["url"]
    if "/magic-the-gathering/" in url:
        game_type = "Magic: The Gathering"
    elif "/yugioh/" in url:
        game_type = "Yu-Gi-Oh!"
    elif "/pokemon/" in url:
        game_type = "Pokemon"
    else:
        game_type = "Other"
    
    if game_type not in game_types:
        game_types[game_type] = []
    game_types[game_type].append(line)

print("\n" + "-"*90)
print("DISTRIBUTION BY GAME TYPE")
print("-"*90)
for game_type, lines in sorted(game_types.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  {game_type}: {len(lines)} product lines")

print("\n" + "-"*90)
print("FIRST 15 PRODUCT LINES")
print("-"*90)
for i, line in enumerate(product_lines[:15], 1):
    url = line["url"]
    print(f"{i:2}. {line['name']:<55} | {url}")

print("\n" + "-"*90)
print("LAST 10 PRODUCT LINES")
print("-"*90)
for i, line in enumerate(product_lines[-10:], len(product_lines)-9):
    url = line["url"]
    print(f"{i:2}. {line['name']:<55} | {url}")

print("\n" + "="*90)
print("INTERESTING PATTERNS")
print("="*90)

# Find crossover games (non-Magic in the top listings)
mtg_count = sum(1 for l in product_lines[:15] if "/magic-the-gathering/" in l["url"])
yugioh_count = sum(1 for l in product_lines[:15] if "/yugioh/" in l["url"])
print(f"\nTop 15 breakdown:")
print(f"  Magic: The Gathering: {mtg_count} lines")
print(f"  Yu-Gi-Oh!: {yugioh_count} lines")

# Look for common keywords/themes
print(f"\nCommon themes in product names:")
themes = {}
for line in product_lines:
    name = line["name"].lower()
    if "edition" in name:
        themes["Edition/Variant"] = themes.get("Edition/Variant", 0) + 1
    if "collection" in name:
        themes["Collection"] = themes.get("Collection", 0) + 1
    if "deck" in name:
        themes["Deck"] = themes.get("Deck", 0) + 1
    if "secret" in name:
        themes["Secret/Mystery"] = themes.get("Secret/Mystery", 0) + 1
    if any(c.isupper() for c in name.split()):
        themes["Special/Crossover"] = themes.get("Special/Crossover", 0) + 1

for theme, count in sorted(themes.items(), key=lambda x: x[1], reverse=True):
    print(f"  {theme}: {count}")

print("\n" + "="*90 + "\n")

