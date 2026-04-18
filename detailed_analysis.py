import json

with open("product_lines.json") as f:
    data = json.load(f)

product_lines = data["product_lines"]

print("\n" + "="*100)
print("DETAILED PRODUCT LINES STRUCTURE ANALYSIS")
print("="*100)

# Group by game type
games = {}
for line in product_lines:
    url = line["url"]
    if "/magic-the-gathering/" in url:
        game = "Magic: The Gathering"
    elif "/yugioh/" in url:
        game = "Yu-Gi-Oh!"
    elif "/pokemon/" in url:
        if "pokemon-japan" in url:
            game = "Pokemon (Japan)"
        else:
            game = "Pokemon"
    elif "/disney-lorcana/" in url:
        game = "Disney Lorcana"
    else:
        game = "Other"
    
    if game not in games:
        games[game] = {"count": 0, "examples": []}
    games[game]["count"] += 1
    games[game]["examples"].append(line)

print("\nGAME CATALOG SUMMARY")
print("-"*100)
for game in sorted(games.keys(), key=lambda x: games[x]["count"], reverse=True):
    print(f"\n{game}: {games[game]['count']} product lines")
    for i, line in enumerate(games[game]["examples"][:3], 1):
        print(f"  {i}. {line['name']}")
    if games[game]["count"] > 3:
        print(f"  ... and {games[game]['count'] - 3} more")

print("\n" + "-"*100)
print("URL STRUCTURE PATTERNS")
print("-"*100)

# Analyze URL patterns
url_bases = {}
for line in product_lines:
    url = line["url"]
    # Extract the base category
    parts = url.split("/")
    if len(parts) >= 5:
        game_type = parts[4]
        if game_type not in url_bases:
            url_bases[game_type] = 0
        url_bases[game_type] += 1

print("\nBase game categories found:")
for game_type in sorted(url_bases.keys()):
    print(f"  /categories/trading-and-collectible-card-games/{game_type}/ : {url_bases[game_type]} products")

print("\n" + "-"*100)
print("NAME PATTERNS & CHARACTERISTICS")
print("-"*100)

# Analyze names
name_patterns = {
    "has_colon": 0,
    "has_hyphen": 0,
    "all_caps": 0,
    "has_year": 0,
    "has_number": 0,
    "short_names": 0,  # < 20 chars
    "long_names": 0,   # > 40 chars
}

for line in product_lines:
    name = line["name"]
    if ":" in name:
        name_patterns["has_colon"] += 1
    if "-" in name:
        name_patterns["has_hyphen"] += 1
    if name.isupper() and len(name) > 2:
        name_patterns["all_caps"] += 1
    if any(c.isdigit() for c in name):
        name_patterns["has_number"] += 1
    if "20" in name or "19" in name:
        name_patterns["has_year"] += 1
    if len(name) < 20:
        name_patterns["short_names"] += 1
    if len(name) > 40:
        name_patterns["long_names"] += 1

print("\nName characteristics:")
for pattern, count in sorted(name_patterns.items(), key=lambda x: x[1], reverse=True):
    percentage = (count / len(product_lines)) * 100
    print(f"  {pattern}: {count} ({percentage:.1f}%)")

print("\n" + "="*100 + "\n")

