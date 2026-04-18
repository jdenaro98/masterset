import asyncio
import json
from pathlib import Path

async def debug_with_more_logs():
    """Debug the extraction logic with more detailed logging."""
    
    # Read the debug_page_text.txt we just created
    with open("C:\\Users\\jape1\\Desktop\\Git\\pokescraper\\debug_page_text.txt", "r", encoding="utf-8") as f:
        page_text = f.read()
    
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    print(f"\nTotal lines in page: {len(lines)}")
    print("\n=== SEARCHING FOR LISTINGS SECTION ===")
    
    # Find lines with "Listings"
    for i, line in enumerate(lines):
        if 'Listings' in line or 'as low as' in line.lower():
            print(f"Line {i}: {line}")
    
    print("\n=== CHECKING CONDITION LOGIC ===")
    # Check if any line has BOTH
    found_both = False
    for i, line in enumerate(lines):
        if 'Listings' in line and 'as low as' in line:
            print(f"Line {i} HAS BOTH keywords: {line}")
            found_both = True
    
    if not found_both:
        print("NO LINE HAS BOTH 'Listings' and 'as low as' - THIS IS THE BUG!")
    
    print("\n=== LINES NEAR 'LISTINGS' KEYWORD ===")
    for i, line in enumerate(lines):
        if 'Listings' in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 15)
            print(f"\nContext starting at line {i}:")
            for j in range(start, end):
                marker = " <-- HERE" if j == i else ""
                print(f"  {j}: {lines[j]}{marker}")
            break
    
    print("\n=== FIRST ACTUAL SELLER LISTING ===")
    # Find where sellers actually start
    for i, line in enumerate(lines):
        if line == "Wylder Gaming":
            start = max(0, i - 3)
            end = min(len(lines), i + 15)
            print(f"Found 'Wylder Gaming' at line {i}")
            print(f"Context around seller:")
            for j in range(start, end):
                marker = " <-- SELLER NAME" if j == i else ""
                print(f"  {j}: {lines[j]}{marker}")
            break

if __name__ == "__main__":
    asyncio.run(debug_with_more_logs())
