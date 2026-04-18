"""Main entry point for the TCGPlayer scraper CLI."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from cli import CLI
from scraper import TCGPlayerScraper


async def main():
    """Main CLI flow."""
    cli = CLI()
    scraper = TCGPlayerScraper()
    
    try:
        cli.print_header("TCGPlayer Web Scraper")
        cli.display_message("Initializing scraper...", "info")
        
        # Setup scraper
        await scraper.setup()
        
        # Step 1: Get and display games
        cli.display_loading("Fetching available games...")
        games_list = await scraper.get_games()
        cli.clear_loading()
        
        if not games_list:
            cli.display_message("No games found. Please check your connection.", "error")
            return
        
        # Extract just game names for display
        game_names = [name for name, _ in games_list]
        cli.display_message(f"Found {len(game_names)} games", "success")
        
        # Step 2: User selects a game
        game_choice = cli.display_game_selection(game_names)
        selected_game_name, selected_game_slug = games_list[game_choice - 1]
        cli.display_message(f"Selected: {selected_game_name}", "success")
        
        # Step 3: Get and display sets
        cli.display_loading("Fetching sets...")
        sets_list = await scraper.get_sets(selected_game_slug)
        cli.clear_loading()
        
        if not sets_list:
            cli.display_message("No sets found for this game.", "warning")
            return
        
        # Extract just set names for display
        set_names = [name for name, _ in sets_list]
        cli.display_message(f"Found {len(set_names)} sets", "success")
        
        # Step 4: User selects a set
        set_choice = cli.display_set_selection(set_names, selected_game_name)
        selected_set_name, selected_set_slug = sets_list[set_choice - 1]
        cli.display_message(f"Selected: {selected_set_name}", "success")
        
        # Step 5: Scrape price guide data
        cli.display_loading("Starting scrape (this may take a while)...")
        cli.clear_loading()
        
        card_data = await scraper.scrape_set_price_guide(
            selected_game_slug,
            selected_set_name,
            selected_set_name  # Use set name as the filter value
        )
        
        # Step 6: Save data
        filename = f"{selected_game_name}_{selected_set_name}.json"
        filename = filename.replace(" ", "_").replace(":", "").lower()
        await scraper.save_data(card_data, filename)
        
        cli.display_message(f"Scraping complete! Data saved to data/{filename}", "success")
        
    except KeyboardInterrupt:
        cli.display_message("Scraping cancelled by user", "warning")
    except Exception as e:
        cli.display_message(f"An error occurred: {e}", "error")
        import traceback
        traceback.print_exc()
    finally:
        cli.display_loading("Cleaning up...")
        await scraper.teardown()
        cli.clear_loading()


if __name__ == "__main__":
    asyncio.run(main())
