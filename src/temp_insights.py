import json
import os

with open('card_product_analysis.json') as f:
    data = json.load(f)

print("="*80)
print("FILES AND SELECTOR TEST RESULTS")
print("="*80)
print(f"\nScreenshot file: {data['screenshot']}")
if os.path.exists(data['screenshot']):
    size = os.path.getsize(data['screenshot'])
    print(f"  Exists: YES ({size} bytes)")
else:
    print(f"  Exists: NO")

print("\n" + "="*80)
print("SELECTOR TEST RESULTS")
print("="*80)
print(f"Seller table selectors tested: {len(data['analysis']['seller_table_selectors'])}")
print(f"Price elements found: {len(data['analysis']['price_elements'])}")
print(f"Condition elements found: {len(data['analysis']['condition_elements'])}")
print(f"Shipping elements found: {len(data['analysis']['shipping_elements'])}")

if data['analysis']['seller_listings']:
    print("\nSeller listings from selectors:")
    for seller in data['analysis']['seller_listings']:
        print(f"  {seller}")
else:
    print("\nNo seller listings extracted via CSS selectors")
    
print("\n" + "="*80)
print("KEY INSIGHTS FOR SCRAPER")
print("="*80)
print("""
1. SELLER LISTING PATTERN IDENTIFIED:
   The sellers appear in sequence:
   - Seller Name (e.g., "Wylder Gaming")
   - Sales Count: (9766 Sales)
   - Condition: "Near Mint"
   - Price: $20.50
   - Shipping: "Shipping: Included" or "+ $X.XX Shipping"
   
2. PAGE STRUCTURE:
   - Total listings shown: 123
   - Visible sellers: 3 (Wylder Gaming, Showcase Games, Spa City CandC)
   - There is a "View 123 Other Listings" link suggesting pagination/modal
   
3. DATA FIELDS AVAILABLE:
   - Conditions found: Near Mint (others may be available via filters)
   - Price: Located after condition
   - Shipping: Either "Included" or shows additional cost
   - Seller ratings: Sales count in parentheses
   
4. TABLES ON PAGE:
   - Table 0: Pricing comparison (Normal/Foil)
   - Table 1: Market Price & Recent Sale
   - Table 2: Volatility indicator
   - Table 3: Inventory info
   - Table 4: Sale statistics (Low/High/Total sold)
   - Table 5: Price history chart (31 rows, 2 cols)

5. SELECTOR ISSUE:
   - Error encountered while testing selectors
   - Need to use text-based extraction approach instead
   - Visible text parsing successfully extracted seller data
""")

