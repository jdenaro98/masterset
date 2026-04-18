# TCGPlayer Web Scraper

A Python CLI tool for scraping card game price data from TCGPlayer using Playwright for web automation.

## Project Structure

```
pokescraper/
├── src/
│   ├── main.py              # CLI entry point
│   ├── scraper.py           # Playwright scraper logic
│   ├── cli.py               # CLI interface and user interaction
│   ├── config.py            # Configuration constants
│   ├── inspector.py         # Utilities for inspecting the website
│   ├── inspector_game_page.py
│   ├── inspector_sets.py
│   └── inspector_price_guide.py
├── data/                    # Output JSON files
├── logs/                    # Log files
└── requirements.txt         # Python dependencies
```

## Quick Start

### Option 1: Windows Batch File (Easiest) 🚀
Double-click `run_pokescraper.bat` - it handles everything automatically:
- Creates virtual environment (if needed)
- Installs dependencies
- Launches the CLI

### Option 2: PowerShell
```powershell
# Navigate to pokescraper directory
cd C:\Users\jape1\Desktop\Git\pokescraper

# Run the script
.\run_pokescraper.ps1

# Optional: reset virtual environment
.\run_pokescraper.ps1 -Reset
```

### Option 3: Manual Setup (Any Platform)
```bash
# Navigate to project directory
cd pokescraper

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the scraper
python src/main.py
```

## Features

### Implemented ✅
- [x] Scrape TCGPlayer game list from navbar (75 games)
- [x] Present user with numbered game selection
- [x] Handle Pokemon language selection (English/Japanese)
- [x] Scrape sets for chosen game/language (100+ sets per game)
- [x] Present user with numbered set selection
- [x] Navigate to price guide and collect card data with pagination
- [x] **Seller extraction** - Extract 20-30+ sellers per card with:
  - [x] Seller name and reputation
  - [x] Sales count
  - [x] Card condition
  - [x] Price (numeric)
  - [x] Shipping cost (numeric or 0 for included)
- [x] **Seller pagination** - Click "View X Other Listings" modal to get all sellers
- [x] JSON output with proper structure
- [x] Comprehensive logging

### Data Output

Each card includes seller data:
```json
{
  "name": "Card Name",
  "url": "https://tcgplayer.com/product/...",
  "sellers": [
    {
      "name": "Seller Name",
      "reputation": "99.9%",
      "sales": "9766",
      "condition": "Near Mint",
      "price": 20.5,
      "shipping": 0
    }
  ]
}
```

### In Progress 🔄
- [ ] Extract detailed seller data (prices, shipping, conditions) for each card
- [ ] Handle pagination for seller listings per card
- [ ] Handle multiple card forms (holo/reverse holo)
- [ ] Output complete JSON with all seller information

### Data Structure

The output JSON will have the following format:

```json
{
  "metadata": {
    "set": "Set Name",
    "scraped_at": "2026-04-17T12:34:56.789Z",
    "total_cards": 150
  },
  "cards": {
    "Card Name #001": {
      "name": "Card Name #001",
      "sellers": [
        {
          "seller_name": "Seller Name",
          "price": 0.50,
          "shipping": 0.10,
          "condition": "Near Mint",
          "quantity_available": 5
        }
      ],
      "url": "link to card on TCGPlayer"
    }
  }
}
```

## Usage

1. Run the program: `python src/main.py`
2. Select a trading card game from the list
3. If Pokemon, select English or Japanese
4. Select a set from the available sets
5. Wait for scraping to complete - data will be saved to `data/` folder

## Architecture

- **CLI Module**: Handles all user interaction and menu displays
- **Scraper Module**: Uses Playwright to navigate and extract data from TCGPlayer
- **Config Module**: Stores configuration constants and selectors
- **Inspector Modules**: Utilities for analyzing TCGPlayer's structure (for development)

## Next Steps

1. Implement detailed seller data extraction per card
2. Handle pagination for multiple seller pages per card
3. Optimize scraping speed with parallel card processing
4. Add error handling and retry logic for failed requests
5. Add support for filtering cards by condition/rarity
