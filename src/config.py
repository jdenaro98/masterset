"""Configuration constants for the scraper."""

# TCGPlayer URLs
TCGPLAYER_BASE_URL = "https://www.tcgplayer.com"
TCGPLAYER_SEARCH_URL = f"{TCGPLAYER_BASE_URL}/search/all/product"

# Timeouts (in milliseconds)
PAGE_LOAD_TIMEOUT = 30000
ELEMENT_WAIT_TIMEOUT = 10000

# Selectors
GAME_DROPDOWN_SELECTOR = "[data-testid='game-selector']"  # May need adjustment
GAME_OPTION_SELECTOR = "[role='option']"

# Output settings
OUTPUT_DIR = "data"
LOG_DIR = "logs"

# Scraper delays (in seconds) to be respectful to the server
DELAY_BETWEEN_REQUESTS = 1
DELAY_BETWEEN_PAGES = 2
