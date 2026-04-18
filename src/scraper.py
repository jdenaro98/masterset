"""Web scraper using Playwright for TCGPlayer."""

import asyncio
import json
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config import (
    TCGPLAYER_BASE_URL,
    PAGE_LOAD_TIMEOUT,
    ELEMENT_WAIT_TIMEOUT,
    OUTPUT_DIR,
    LOG_DIR,
    DELAY_BETWEEN_REQUESTS,
    DELAY_BETWEEN_PAGES,
)

# Setup logging
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/scraper.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class TCGPlayerScraper:
    """Scrapes TCGPlayer website for card data."""

    def __init__(self):
        """Initialize the scraper."""
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.games_cache = None

    async def setup(self):
        """Setup browser and context."""
        logger.info("Setting up Playwright browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = await self.context.new_page()
        logger.info("Browser setup complete")

    async def teardown(self):
        """Cleanup browser and context."""
        logger.info("Tearing down Playwright browser...")
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()
        logger.info("Browser teardown complete")

    async def get_games(self) -> List[Tuple[str, str]]:
        """
        Get all available games from TCGPlayer's Product Line filter.
        
        Returns:
            List of tuples (game_name, game_slug) sorted alphabetically.
        """
        if self.games_cache:
            logger.info("Using cached games list")
            return self.games_cache

        logger.info("Fetching games list from TCGPlayer Product Line filter...")
        try:
            # Navigate to the product search grid page
            await self.page.goto(
                f"{TCGPLAYER_BASE_URL}/search/all/product?view=grid",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await self.page.wait_for_load_state("networkidle")
            
            # Click Product Line filter to expand it
            await self.page.evaluate("""
                () => {
                    let buttons = Array.from(document.querySelectorAll('button'));
                    let productLineBtn = buttons.find(btn => 
                        btn.innerText && btn.innerText.trim() === 'Product Line'
                    );
                    if (productLineBtn) {
                        productLineBtn.click();
                    }
                }
            """)
            
            await asyncio.sleep(1)  # Wait for filter to expand
            
            # Extract product line names from the expanded filter
            product_lines = await self.page.evaluate("""
                () => {
                    const lines = [];
                    const pageText = document.body.innerText;
                    const textLines = pageText.split('\\n').map(l => l.trim());
                    
                    let inProductLineSection = false;
                    let foundCount = 0;
                    
                    for (let i = 0; i < textLines.length; i++) {
                        if (textLines[i] === 'Product Line') {
                            inProductLineSection = true;
                            continue;
                        }
                        
                        if (inProductLineSection) {
                            // Stop at next filter section
                            if (textLines[i] === 'Set' || textLines[i] === 'Product Type' || 
                                textLines[i].includes('results')) {
                                if (foundCount > 5) break;
                            }
                            
                            // Valid product line entries (skip pure numbers which are listing counts)
                            if (textLines[i] && textLines[i].length > 2 && textLines[i].length < 100 &&
                                !textLines[i].match(/^\\d+$/) && !textLines[i].includes('(')) {
                                lines.push(textLines[i]);
                                foundCount++;
                                if (foundCount > 150) break;
                            }
                        }
                    }
                    
                    return lines;
                }
            """)
            
            if product_lines:
                # Convert product line names to slugs and create tuples
                games_list = []
                for name in product_lines:
                    # Create slug by converting to lowercase and replacing spaces with hyphens
                    slug = name.lower().replace(' ', '-').replace('&', 'and')
                    games_list.append((name, slug))
                
                # Sort alphabetically by name
                games_list.sort(key=lambda x: x[0].lower())
                
                self.games_cache = games_list
                logger.info(f"Found {len(self.games_cache)} games: {[g[0] for g in self.games_cache[:10]]}")
                return self.games_cache
            else:
                logger.warning("No product lines found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching games from Product Line filter: {e}")
            raise

    async def get_sets(self, game_slug: str) -> List[Tuple[str, str]]:
        """
        Get all sets for a specific game by clicking the Set filter to expand it.
        
        Args:
            game_slug: Game slug (e.g., "pokemon", "yugioh", "magic-the-gathering")
            
        Returns:
            List of tuples (set_name, set_slug) sorted alphabetically
        """
        logger.info(f"Fetching sets for game: {game_slug}")
        
        try:
            # Navigate to the game-specific search page
            await self.page.goto(
                f"{TCGPLAYER_BASE_URL}/search/{game_slug}/product?view=grid",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Click the Set filter button to expand it
            await self.page.evaluate("""
                () => {
                    let buttons = Array.from(document.querySelectorAll('button'));
                    let setBtn = buttons.find(btn => 
                        btn.innerText && btn.innerText.trim() === 'Set'
                    );
                    if (setBtn) {
                        console.log('Found Set button, clicking...');
                        setBtn.click();
                    }
                }
            """)
            
            await asyncio.sleep(1)  # Wait for filter to expand
            
            # Extract set names from the expanded Set filter
            sets_list = await self.page.evaluate("""
                () => {
                    const sets = [];
                    const pageText = document.body.innerText;
                    const textLines = pageText.split('\\n').map(l => l.trim());
                    
                    let inSetSection = false;
                    let foundCount = 0;
                    
                    for (let i = 0; i < textLines.length; i++) {
                        if (textLines[i] === 'Set') {
                            inSetSection = true;
                            continue;
                        }
                        
                        if (inSetSection) {
                            // Stop at next filter section or other markers
                            if (textLines[i] === 'Product Type' || textLines[i] === 'Card Type' ||
                                textLines[i] === 'Condition' || textLines[i] === 'Rarity' ||
                                textLines[i] === 'Clear Filters' ||
                                textLines[i].includes('results')) {
                                if (foundCount > 5) break;
                            }
                            
                            // Valid set entries:
                            // - Not empty
                            // - 2-200 characters (set names vary)
                            // - Not just numbers (prices/counts)
                            // - Not currency (starts with $)
                            // - Not common filter markers
                            if (textLines[i] && 
                                textLines[i].length >= 2 && 
                                textLines[i].length < 200 &&
                                !textLines[i].startsWith('$') &&
                                !textLines[i].match(/^\\d+$/) &&
                                !textLines[i].match(/^\\d+,\\d+$/) &&
                                !textLines[i].includes('(') &&
                                !textLines[i].includes('All Categories') &&
                                !textLines[i].includes('View') &&
                                textLines[i] !== 'Set' &&
                                textLines[i] !== 'Product Type' &&
                                textLines[i] !== 'Card Type' &&
                                textLines[i] !== 'Rarity' &&
                                textLines[i] !== 'Condition' &&
                                textLines[i] !== 'Clear Filters' &&
                                textLines[i] !== 'Printing' &&
                                textLines[i] !== 'Sort & View' &&
                                textLines[i] !== 'Sort by:') {
                                
                                sets.push(textLines[i]);
                                foundCount++;
                                if (foundCount > 500) break;
                            }
                        }
                    }
                    
                    return sets;
                }
            """)
            
            if sets_list:
                # Create tuples with set name and slug, then sort alphabetically
                sets_with_slugs = []
                for set_name in sets_list:
                    # Create slug for the set
                    set_slug = set_name.lower().replace(' ', '-').replace(':', '').replace('/', '-').replace('&', 'and')
                    sets_with_slugs.append((set_name, set_slug))
                
                # Sort alphabetically by name
                sets_with_slugs.sort(key=lambda x: x[0].lower())
                
                logger.info(f"Found {len(sets_with_slugs)} sets: {[s[0] for s in sets_with_slugs[:10]]}")
                return sets_with_slugs
            else:
                logger.warning(f"No sets found for game: {game_slug}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching sets for {game_slug}: {e}")
            raise

    async def scrape_card_sellers(self, card_url: str) -> List[Dict]:
        """
        Scrape all seller listings for a specific card.
        
        Args:
            card_url: Full URL to the card product page
            
        Returns:
            List of seller dictionaries with price, shipping, condition, etc.
        """
        logger.info(f"Scraping sellers for card: {card_url[:80]}...")
        
        sellers = []
        
        try:
            await self.page.goto(card_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Extract sellers from visible text on the page
            page_sellers = await self.page.evaluate("""
                () => {
                    const sellers = [];
                    const pageText = document.body.innerText;
                    const lines = pageText.split('\\n').map(line => line.trim()).filter(line => line.length > 0);
                    
                    // Find the "Listings / Page" anchor which marks the start of seller listings
                    let startIdx = -1;
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes('Listings / Page') || lines[i].includes('Listings /')) {
                            startIdx = i;
                            break;
                        }
                    }
                    
                    if (startIdx === -1) {
                        // Fallback: look for any "Listings" line
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i].includes('Listings') && (lines[i].includes('as low as') || 
                                (i + 1 < lines.length && lines[i + 1].includes('as low as')))) {
                                startIdx = i;
                                break;
                            }
                        }
                    }
                    
                    if (startIdx === -1) {
                        return sellers; // No listings found
                    }
                    
                    // Start parsing sellers from after the anchor
                    let currentSeller = {};
                    
                    for (let i = startIdx + 1; i < lines.length; i++) {
                        const line = lines[i];
                        
                        // Stop at pagination controls or other sections
                        if (line.includes('Sort By') || line.includes('Show More') || 
                            line.includes('Seller') || line.includes('Price') ||
                            line === '') {
                            continue;
                        }
                        
                        // Detect seller name - typically starts with capital letter and no special chars like $
                        if (!line.includes('$') && !line.includes('+') && !line.includes('-') &&
                            !line.includes('%') && !line.includes('Sales') && !line.includes('Mint') && 
                            !line.includes('Played') && !line.includes('Shipping') &&
                            line.length > 3 && line.length < 60) {
                            
                            // Check if line looks like a seller name
                            if (/^[A-Za-z]/.test(line) && !line.match(/^\\d/) && 
                                !line.includes('Cart') && !line.includes('Qty')) {
                                
                                // If we have a previous seller with at least name, save it
                                if (currentSeller.name && currentSeller.price) {
                                    sellers.push({...currentSeller});
                                }
                                currentSeller = { name: line };
                            }
                        }
                        
                        // Extract reputation percentage
                        if (line.match(/^\\d+(\\.\\d+)?%$/)) {
                            currentSeller.reputation = line;
                        }
                        
                        // Extract sales count - format: (1234 Sales) or (1234 Sales) or 1234+ Sales
                        if ((line.includes('Sales') || line.includes('sales')) && line.match(/\\d+/)) {
                            const match = line.match(/(\\d+)\\s*\\+?\\s*(?:Sales|sales)/);
                            if (match) {
                                currentSeller.sales = match[1];
                            }
                        }
                        
                        // Extract condition (Near Mint, Lightly Played, etc.)
                        if (line.match(/Mint|Played|Damaged|PSA|Light|Heavy|Excellent|Good|Fair|Poor/)) {
                            currentSeller.condition = line;
                        }
                        
                        // Extract price (format: $XX.XX at start of line)
                        if (line.match(/^\\$\\d+(\\.\\d{2})?$/)) {
                            currentSeller.price = parseFloat(line.replace('$', ''));
                        }
                        
                        // Extract shipping (format: Shipping: Included or + $X.XX Shipping or Shipping: Included)
                        if (line.includes('Shipping')) {
                            if (line.includes('Included')) {
                                currentSeller.shipping = 0;
                            } else {
                                const match = line.match(/\\$\\d+(\\.\\d{2})?/);
                                if (match) {
                                    currentSeller.shipping = parseFloat(match[0].replace('$', ''));
                                }
                            }
                        }
                    }
                    
                    // Don't forget the last seller
                    if (currentSeller.name && currentSeller.price) {
                        sellers.push(currentSeller);
                    }
                    
                    return sellers;
                }
            """)
            
            sellers.extend(page_sellers)
            logger.info(f"Found {len(page_sellers)} sellers on initial page")
            
            # Check for pagination - "View X Other Listings" link
            has_more_sellers = await self.page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a');
                    for (let link of links) {
                        if (link.innerText && link.innerText.includes('View') && link.innerText.includes('Listings')) {
                            return link.innerText;
                        }
                    }
                    return null;
                }
            """)
            
            if has_more_sellers:
                logger.info(f"Pagination found: {has_more_sellers}")
                
                # Try to find and click the pagination link
                try:
                    # Wait a bit for the page to settle
                    await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
                    
                    # Find the "View X Other Listings" link and click it
                    pagination_clicked = await self.page.evaluate("""
                        () => {
                            const links = document.querySelectorAll('a');
                            for (let link of links) {
                                if (link.innerText && link.innerText.includes('View') && link.innerText.includes('Listings')) {
                                    link.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                    
                    if pagination_clicked:
                        logger.info("Pagination link clicked, waiting for modal to load...")
                        
                        # Wait for modal/pagination content to load
                        await asyncio.sleep(2)  # Give time for modal to appear
                        
                        try:
                            # Try to wait for modal content
                            await self.page.wait_for_selector('[class*="modal"], [class*="dialog"], [class*="popup"]', timeout=5000)
                        except:
                            # Modal may not have specific selector, that's OK
                            pass
                        
                        # Extract additional sellers from modal/pagination
                        modal_sellers = await self.page.evaluate("""
                            () => {
                                const sellers = [];
                                const pageText = document.body.innerText;
                                const lines = pageText.split('\\n').map(line => line.trim()).filter(line => line.length > 0);
                                
                                let currentSeller = {};
                                
                                for (let i = 0; i < lines.length; i++) {
                                    const line = lines[i];
                                    
                                    // Stop at common end markers
                                    if (line.includes('Sort By') || line.includes('Show More')) {
                                        break;
                                    }
                                    
                                    // Detect seller name
                                    if (!line.includes('$') && !line.includes('+') && !line.includes('-') &&
                                        !line.includes('%') && !line.includes('Sales') && !line.includes('Mint') && 
                                        !line.includes('Played') && !line.includes('Shipping') &&
                                        line.length > 3 && line.length < 60) {
                                        
                                        if (/^[A-Za-z]/.test(line) && !line.match(/^\\d/) && 
                                            !line.includes('Cart') && !line.includes('Qty') &&
                                            !line.includes('Listings')) {
                                            
                                            if (currentSeller.name && currentSeller.price) {
                                                sellers.push({...currentSeller});
                                            }
                                            currentSeller = { name: line };
                                        }
                                    }
                                    
                                    if (line.match(/^\\d+(\\.\\d+)?%$/)) {
                                        currentSeller.reputation = line;
                                    }
                                    
                                    if ((line.includes('Sales') || line.includes('sales')) && line.match(/\\d+/)) {
                                        const match = line.match(/(\\d+)\\s*\\+?\\s*(?:Sales|sales)/);
                                        if (match) {
                                            currentSeller.sales = match[1];
                                        }
                                    }
                                    
                                    if (line.match(/Mint|Played|Damaged|PSA|Light|Heavy|Excellent|Good|Fair|Poor/)) {
                                        currentSeller.condition = line;
                                    }
                                    
                                    if (line.match(/^\\$\\d+(\\.\\d{2})?$/)) {
                                        currentSeller.price = parseFloat(line.replace('$', ''));
                                    }
                                    
                                    if (line.includes('Shipping')) {
                                        if (line.includes('Included')) {
                                            currentSeller.shipping = 0;
                                        } else {
                                            const match = line.match(/\\$\\d+(\\.\\d{2})?/);
                                            if (match) {
                                                currentSeller.shipping = parseFloat(match[0].replace('$', ''));
                                            }
                                        }
                                    }
                                }
                                
                                if (currentSeller.name && currentSeller.price) {
                                    sellers.push(currentSeller);
                                }
                                
                                return sellers;
                            }
                        """)
                        
                        # Add modal sellers to our list (avoiding duplicates)
                        seller_names = set(s['name'] for s in sellers)
                        for seller in modal_sellers:
                            if seller.get('name') not in seller_names:
                                sellers.append(seller)
                                seller_names.add(seller['name'])
                        
                        logger.info(f"Found {len(modal_sellers)} additional sellers from pagination (total now: {len(sellers)})")
                    else:
                        logger.info("Could not click pagination link")
                        
                except Exception as e:
                    logger.warning(f"Error handling pagination: {e}")
                    # Continue with what we have
            
        except Exception as e:
            logger.error(f"Error scraping card sellers: {e}")
        
        return sellers

    async def scrape_set_price_guide(
        self, 
        game_slug: str,
        set_name: str,
        set_filter_value: str,
        max_cards: Optional[int] = None
    ) -> Dict:
        """
        Scrape all card data from a set's price guide.
        Uses filter-based approach: navigate to game page and apply set filter.
        
        Args:
            game_slug: Game slug (e.g., "pokemon")
            set_name: Display name of the set
            set_filter_value: The filter value/text for the set from the Set filter
            max_cards: Optional limit on cards to scrape (for testing)
            
        Returns:
            Dictionary with card data and seller listings
        """
        logger.info(f"Scraping price guide for {set_name}")
        
        cards_data = {
            "metadata": {
                "set": set_name,
                "game": game_slug,
                "scraped_at": datetime.now().isoformat(),
                "total_cards": 0,
            },
            "cards": {},
        }
        
        try:
            # Navigate to the game page
            game_url = f"{TCGPLAYER_BASE_URL}/search/{game_slug}/product?view=grid"
            logger.info(f"Navigating to game page: {game_url}")
            await self.page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Click the Set filter to expand it
            logger.info("Expanding Set filter...")
            await self.page.evaluate("""
                () => {
                    let buttons = Array.from(document.querySelectorAll('button'));
                    let setBtn = buttons.find(btn => 
                        btn.innerText && btn.innerText.trim() === 'Set'
                    );
                    if (setBtn) {
                        console.log('Found Set button, clicking...');
                        setBtn.click();
                    }
                }
            """)
            
            await asyncio.sleep(1)  # Wait for filter to expand
            
            # Click the specific set checkbox/option
            logger.info(f"Clicking set filter: {set_filter_value}")
            await self.page.evaluate(f"""
                () => {{
                    const setName = "{set_filter_value}";
                    const allLabels = Array.from(document.querySelectorAll('label'));
                    const setLabel = allLabels.find(label => 
                        label.innerText && label.innerText.includes(setName)
                    );
                    if (setLabel) {{
                        console.log('Found set label, clicking...');
                        setLabel.click();
                    }}
                }}
            """)
            
            await asyncio.sleep(2)  # Wait for filter to apply and page to load
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Collect all card links first from the filtered results
            all_card_links = []
            page_num = 1
            
            # First pass: collect all card URLs from filtered grid
            while True:
                logger.info(f"Collecting card links from page {page_num}...")
                
                # For pagination, re-navigate to game page with page parameter while keeping filter
                if page_num > 1:
                    page_url = f"{game_url}?page={page_num}"
                    await self.page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    await self.page.wait_for_load_state("networkidle")
                    await asyncio.sleep(DELAY_BETWEEN_PAGES)
                    
                    # Re-apply the set filter
                    await self.page.evaluate("""
                        () => {
                            let buttons = Array.from(document.querySelectorAll('button'));
                            let setBtn = buttons.find(btn => 
                                btn.innerText && btn.innerText.trim() === 'Set'
                            );
                            if (setBtn) {
                                setBtn.click();
                            }
                        }
                    """)
                    
                    await asyncio.sleep(1)
                    
                    # Re-click the set checkbox
                    await self.page.evaluate(f"""
                        () => {{
                            const setName = "{set_filter_value}";
                            const allLabels = Array.from(document.querySelectorAll('label'));
                            const setLabel = allLabels.find(label => 
                                label.innerText && label.innerText.includes(setName)
                            );
                            if (setLabel) {{
                                setLabel.click();
                            }}
                        }}
                    """)
                    
                    await asyncio.sleep(2)
                
                # Extract card links
                page_cards = await self.page.evaluate("""
                    () => {
                        const cards = [];
                        const seenUrls = new Set();
                        
                        // Select all product links
                        document.querySelectorAll('a[href*="/product/"]').forEach((link) => {
                            const href = link.getAttribute('href') || '';
                            const text = link.innerText?.trim();
                            
                            if (href && !seenUrls.has(href) && text && text.length > 2) {
                                seenUrls.add(href);
                                cards.push({
                                    name: text,
                                    url: href
                                });
                            }
                        });
                        
                        return cards;
                    }
                """)
                
                if not page_cards:
                    logger.info("No more card links found")
                    break
                
                all_card_links.extend(page_cards)
                logger.info(f"Collected {len(page_cards)} card links from page {page_num}")
                
                # Stop if we've reached the max
                if max_cards and len(all_card_links) >= max_cards:
                    all_card_links = all_card_links[:max_cards]
                    break
                
                # Check for next page
                check_next = await self.page.evaluate("""
                    () => {
                        const pageIndicators = document.querySelectorAll('[class*="page"], [aria-label*="page"], .pagination');
                        return pageIndicators.length > 0;
                    }
                """)
                
                if not check_next or page_num >= 20:
                    break
                
                page_num += 1
            
            logger.info(f"Total card links collected: {len(all_card_links)}")
            
            # Second pass: scrape seller data for each card
            for idx, card_link in enumerate(all_card_links, 1):
                card_name = card_link["name"].split('\n')[0].strip()
                card_url = card_link["url"]
                
                logger.info(f"Scraping card {idx}/{len(all_card_links)}: {card_name}")
                
                # Get seller data for this card
                sellers = await self.scrape_card_sellers(card_url)
                
                # Store card data
                if card_name not in cards_data["cards"]:
                    cards_data["cards"][card_name] = {
                        "name": card_name,
                        "url": card_url,
                        "sellers": sellers
                    }
            
            cards_data["metadata"]["total_cards"] = len(cards_data["cards"])
            logger.info(f"Scraped {len(cards_data['cards'])} cards with seller data")
            
        except Exception as e:
            logger.error(f"Error scraping price guide: {e}")
            raise
        
        return cards_data

    async def save_data(self, data: Dict, filename: str):
        """
        Save scraped data to JSON file.
        
        Args:
            data: Dictionary of card data
            filename: Output filename
        """
        output_path = Path(OUTPUT_DIR) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved to {output_path}")


async def main():
    """Main scraper execution."""
    scraper = TCGPlayerScraper()
    try:
        await scraper.setup()
        games = await scraper.get_games()
        print(f"Found games: {[g[0] for g in games]}")
    finally:
        await scraper.teardown()


if __name__ == "__main__":
    asyncio.run(main())
