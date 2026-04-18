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
        Get all available games from TCGPlayer's homepage.
        
        Returns:
            List of tuples (game_name, category_url)
        """
        if self.games_cache:
            logger.info("Using cached games list")
            return self.games_cache

        logger.info("Fetching games list from TCGPlayer...")
        try:
            await self.page.goto(TCGPLAYER_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            
            # Extract game links from navbar
            games = await self.page.evaluate("""
                () => {
                    const games = [];
                    
                    // Look for the navbar with game links
                    const navbar = document.querySelector('nav.navbar.is-black');
                    if (navbar) {
                        navbar.querySelectorAll('a').forEach(link => {
                            const href = link.getAttribute('href') || '';
                            const text = link.textContent.trim();
                            
                            // Look for game category links
                            if (href.includes('/categories/trading-and-collectible-card-games/') &&
                                !href.includes('/price-guides') &&
                                text.length > 0 && text.length < 50) {
                                
                                // Avoid duplicates
                                if (!games.some(g => g.name === text)) {
                                    games.push({
                                        name: text,
                                        url: href
                                    });
                                }
                            }
                        });
                    }
                    
                    return games;
                }
            """)
            
            if games:
                # Convert to list of tuples for easier handling
                self.games_cache = [(g["name"], g["url"]) for g in games]
                logger.info(f"Found {len(self.games_cache)} games: {[g[0] for g in self.games_cache]}")
                return self.games_cache
            else:
                logger.warning("No games found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching games: {e}")
            raise

    async def get_sets(self, game_category_url: str, language: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Get all sets for a specific game category.
        
        Args:
            game_category_url: URL to the game's category page
            language: Optional language for Pokemon ("English" or "Japanese")
            
        Returns:
            List of tuples (set_name, set_url)
        """
        logger.info(f"Fetching sets from {game_category_url}")
        
        try:
            # Handle Pokemon language selection
            if language:
                if language == "Japanese":
                    game_category_url = game_category_url.replace("/pokemon", "/pokemon-japan")
                # English is default, no change needed
            
            full_url = TCGPLAYER_BASE_URL + game_category_url
            await self.page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Extract set links
            sets = await self.page.evaluate("""
                () => {
                    const sets = [];
                    
                    // Find all links that point to specific sets
                    document.querySelectorAll('a').forEach(link => {
                        const href = link.getAttribute('href') || '';
                        const text = link.textContent.trim();
                        
                        // Look for set links (they have game name + set name in path)
                        if (href.includes('/categories/trading-and-collectible-card-games/') &&
                            !href.includes('/price-guides') &&
                            !href.includes('?') &&
                            href.split('/').length > 4 && // Has a set path
                            text.length > 2 && text.length < 100 &&
                            !text.includes('Price Guide') &&
                            !text.includes('Shop All') &&
                            !text.includes('Latest Sets')) {
                            
                            // Avoid duplicates
                            if (!sets.some(s => s.url === href)) {
                                sets.push({
                                    name: text,
                                    url: href
                                });
                            }
                        }
                    });
                    
                    return sets;
                }
            """)
            
            if sets:
                result = [(s["name"], s["url"]) for s in sets]
                logger.info(f"Found {len(result)} sets")
                return result
            else:
                logger.warning("No sets found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching sets: {e}")
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
        set_name: str,
        set_category_url: str,
        max_cards: Optional[int] = None
    ) -> Dict:
        """
        Scrape all card data from a set's price guide.
        
        Args:
            set_name: Name of the set
            set_category_url: URL to the set's category page
            max_cards: Optional limit on cards to scrape (for testing)
            
        Returns:
            Dictionary with card data and seller listings
        """
        logger.info(f"Scraping price guide for {set_name}")
        
        cards_data = {
            "metadata": {
                "set": set_name,
                "scraped_at": datetime.now().isoformat(),
                "total_cards": 0,
            },
            "cards": {},
        }
        
        try:
            # Navigate to the set's category page
            full_url = TCGPLAYER_BASE_URL + set_category_url
            await self.page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Collect all card links first
            all_card_links = []
            page_num = 1
            
            # First pass: collect all card URLs
            while True:
                logger.info(f"Collecting card links from page {page_num}...")
                
                # Navigate to specific page
                page_url = f"{full_url}?page={page_num}"
                await self.page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(DELAY_BETWEEN_PAGES)
                
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
