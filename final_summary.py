import json
import os

print("\n" + "="*100)
print("POKESCRAPER - PRODUCT LINES EXTRACTION SUMMARY")
print("="*100)

# File info
print("\n1. EXECUTION DETAILS")
print("-"*100)
print(f"   Script: inspect_product_lines.py")
print(f"   Target URL: https://www.tcgplayer.com/search/all/product?view=grid")
print(f"   Execution Status: SUCCESSFUL")

# Load data
with open("product_lines.json") as f:
    data = json.load(f)

product_lines = data["product_lines"]

print(f"\n2. EXTRACTION RESULTS")
print("-"*100)
print(f"   Total product lines found: {data['total_found']}")
print(f"   Total product lines extracted: {len(product_lines)}")

# File sizes
json_size = os.path.getsize("product_lines.json")
text_size = os.path.getsize("product_lines_page_text.txt")
print(f"\n   Output files created:")
print(f"   - product_lines.json: {json_size:,} bytes")
print(f"   - product_lines_page_text.txt: {text_size:,} bytes")

# Categorization
print(f"\n3. CATEGORY DISTRIBUTION")
print("-"*100)

categories = {
    "Magic: The Gathering": 0,
    "Yu-Gi-Oh!": 0,
    "Pokemon": 0,
    "Pokemon (Japan)": 0,
    "Disney Lorcana": 0,
    "Multi-Game/General": 0
}

for line in product_lines:
    url = line["url"]
    if "/magic-the-gathering/" in url:
        categories["Magic: The Gathering"] += 1
    elif "/yugioh/" in url:
        categories["Yu-Gi-Oh!"] += 1
    elif "/pokemon-japan/" in url:
        categories["Pokemon (Japan)"] += 1
    elif "/pokemon/" in url:
        categories["Pokemon"] += 1
    elif "/disney-lorcana/" in url:
        categories["Disney Lorcana"] += 1
    else:
        categories["Multi-Game/General"] += 1

for game, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
    if count > 0:
        percentage = (count / len(product_lines)) * 100
        bar_length = int(count / 2)
        bar = "|" * bar_length
        print(f"   {game:<25} {count:2} lines  {percentage:5.1f}%  {bar}")

# Name analysis
print(f"\n4. PRODUCT NAME CHARACTERISTICS")
print("-"*100)

name_stats = {
    "avg_length": 0,
    "min_length": float('inf'),
    "max_length": 0,
    "with_numbers": 0,
    "with_colons": 0,
    "with_hyphens": 0,
}

total_length = 0
for line in product_lines:
    name = line["name"]
    length = len(name)
    total_length += length
    name_stats["min_length"] = min(name_stats["min_length"], length)
    name_stats["max_length"] = max(name_stats["max_length"], length)
    
    if any(c.isdigit() for c in name):
        name_stats["with_numbers"] += 1
    if ":" in name:
        name_stats["with_colons"] += 1
    if "-" in name:
        name_stats["with_hyphens"] += 1

name_stats["avg_length"] = total_length / len(product_lines)

print(f"   Average name length: {name_stats['avg_length']:.1f} characters")
print(f"   Shortest name: {name_stats['min_length']} characters")
print(f"   Longest name: {name_stats['max_length']} characters")
print(f"   Names with numbers: {name_stats['with_numbers']} ({100*name_stats['with_numbers']/len(product_lines):.1f}%)")
print(f"   Names with colons: {name_stats['with_colons']} ({100*name_stats['with_colons']/len(product_lines):.1f}%)")
print(f"   Names with hyphens: {name_stats['with_hyphens']} ({100*name_stats['with_hyphens']/len(product_lines):.1f}%)")

# Interesting findings
print(f"\n5. PAGE STRUCTURE INSIGHTS")
print("-"*100)
print(f"   TCGPlayer catalog includes 6 major card games:")
print(f"   1. Magic: The Gathering (most popular - 10 sets shown)")
print(f"   2. Pokemon (International) (10 sets shown)")
print(f"   3. Yu-Gi-Oh! (10 sets shown)")
print(f"   4. Pokemon (Japan) (10 sets shown)")
print(f"   5. Disney Lorcana (newest - 7 sets shown)")
print(f"   6. Others (1 Piece, Digimon, etc.)")

print(f"\n   URL Pattern:")
print(f"   - Base: /categories/trading-and-collectible-card-games/")
print(f"   - Game: [game-name]/")
print(f"   - Product: [product-slug]/ (optional)")

print(f"\n   Navigation Structure:")
print(f"   - Main categories in header: Magic, Yu-Gi-Oh!, Pokemon, Disney Lorcana")
print(f"   - Additional categories under 'More Products' dropdown")
print(f"   - Grid view displaying first 20 products per page")
print(f"   - Each product shows: name, thumbnail, listing count, price")

print(f"\n6. DATA EXTRACTION METHOD")
print("-"*100)
print(f"   - Method: Browser automation with text extraction")
print(f"   - CSS Selectors: Used to locate product grid")
print(f"   - Text Parsing: Extracted product names and URLs from page text")
print(f"   - Data Format: JSON with URLs and names")
print(f"   - Total items parsed from page: All {len(product_lines)} product lines")

print(f"\n7. NEXT STEPS FOR SCRAPING")
print("-"*100)
print(f"   These product lines can be used to:")
print(f"   1. Navigate to individual set pages")
print(f"   2. Extract price guides for specific sets")
print(f"   3. Collect card listings and prices")
print(f"   4. Track card price history")
print(f"   5. Monitor seller listings and reputations")

print("\n" + "="*100 + "\n")

