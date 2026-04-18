import json
from pathlib import Path
import re

def analyze_sellers():
    """Analyze the page text and extract all sellers manually."""
    
    # Read the debug_page_text.txt we just created
    with open("C:\\Users\\jape1\\Desktop\\Git\\pokescraper\\debug_page_text.txt", "r", encoding="utf-8") as f:
        page_text = f.read()
    
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    print("\n=== MANUAL SELLER EXTRACTION ANALYSIS ===\n")
    
    # Find where sellers section starts
    sellers_section_start = None
    for i, line in enumerate(lines):
        if line == "Listings / Page":
            sellers_section_start = i + 1  # Skip to next line after "10"
            print(f"Found 'Listings / Page' at line {i}")
            sellers_section_start = i + 2  # Skip "10" as well
            print(f"Starting seller extraction at line {sellers_section_start}\n")
            break
    
    if not sellers_section_start:
        print("ERROR: Could not find seller section start")
        return
    
    extracted_sellers = []
    i = sellers_section_start
    
    while i < len(lines):
        line = lines[i]
        
        # Stop at pagination
        if line.startswith(('Sort By', 'Customers Also', 'Related Products')) or i > 250:
            break
        
        # Check if this looks like a seller name
        # Pattern: seller name on its own line, followed by percentage and sales
        if i + 2 < len(lines):
            next_line = lines[i + 1]
            next_next_line = lines[i + 2]
            
            # Check if pattern matches: Name, %, (Sales)
            if '%' in next_line and 'Sales' in next_next_line:
                seller_name = line
                reputation_pct = next_line
                sales_match = re.search(r'\((\d+(?:\+)?)', next_next_line)
                
                # Extract condition, price, shipping (next few lines)
                condition = None
                price = None
                shipping = None
                
                for offset in range(3, 10):
                    if i + offset < len(lines):
                        check_line = lines[i + offset]
                        if 'Mint' in check_line or 'Played' in check_line:
                            condition = check_line
                        elif check_line.startswith('$'):
                            price = check_line
                        elif 'Shipping' in check_line:
                            shipping = check_line
                        elif 'Add to Cart' in check_line:
                            break
                
                seller_info = {
                    'name': seller_name,
                    'reputation': reputation_pct,
                    'sales': sales_match.group(1) if sales_match else None,
                    'condition': condition,
                    'price': price,
                    'shipping': shipping
                }
                
                extracted_sellers.append(seller_info)
                
                print(f"SELLER #{len(extracted_sellers)}: {seller_name}")
                print(f"  Reputation: {reputation_pct}")
                print(f"  Sales: {sales_match.group(1) if sales_match else 'N/A'}")
                print(f"  Condition: {condition}")
                print(f"  Price: {price}")
                print(f"  Shipping: {shipping}\n")
        
        i += 1
    
    print(f"\n=== TOTAL SELLERS EXTRACTED: {len(extracted_sellers)} ===")
    
    # Save results
    with open("C:\\Users\\jape1\\Desktop\\Git\\pokescraper\\manual_sellers.json", "w", encoding="utf-8") as f:
        json.dump(extracted_sellers, f, indent=2)
    print("Saved to manual_sellers.json")

if __name__ == "__main__":
    analyze_sellers()
