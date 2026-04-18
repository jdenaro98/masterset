"""CLI interface for user interaction."""

import sys
from typing import List, Optional


class CLI:
    """Handles all command-line interface interactions."""

    @staticmethod
    def clear_screen():
        """Clear the terminal screen."""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    @staticmethod
    def print_header(text: str):
        """Print a formatted header."""
        print("\n" + "=" * 60)
        print(f"  {text}")
        print("=" * 60 + "\n")

    @staticmethod
    def print_options(options: List[str], start_number: int = 1):
        """Print a numbered list of options."""
        for i, option in enumerate(options, start=start_number):
            print(f"  {i}. {option}")
        print()

    @staticmethod
    def get_user_choice(max_option: int, prompt: str = "Enter your choice") -> int:
        """Get a valid user choice between 1 and max_option."""
        while True:
            try:
                choice = input(f"{prompt} (1-{max_option}): ").strip()
                choice_num = int(choice)
                if 1 <= choice_num <= max_option:
                    return choice_num
                else:
                    print(f"  ❌ Please enter a number between 1 and {max_option}\n")
            except ValueError:
                print("  ❌ Please enter a valid number\n")

    @staticmethod
    def get_yes_no(prompt: str = "Continue?") -> bool:
        """Get a yes/no response from the user."""
        while True:
            response = input(f"{prompt} (y/n): ").strip().lower()
            if response in ('y', 'yes'):
                return True
            elif response in ('n', 'no'):
                return False
            else:
                print("  ❌ Please enter 'y' or 'n'\n")

    @staticmethod
    def display_game_selection(games: List[str]):
        """Display game selection menu."""
        CLI.print_header("Select a Trading Card Game")
        CLI.print_options(games)
        return CLI.get_user_choice(len(games))

    @staticmethod
    def display_language_selection() -> str:
        """Display language selection for Pokemon."""
        CLI.print_header("Select Language for Pokemon")
        languages = ["English", "Japanese"]
        CLI.print_options(languages)
        choice = CLI.get_user_choice(len(languages))
        return languages[choice - 1]

    @staticmethod
    def display_set_selection(sets: List[str], game_name: str):
        """Display set selection menu."""
        CLI.print_header(f"Select a {game_name} Set")
        CLI.print_options(sets)
        return CLI.get_user_choice(len(sets))

    @staticmethod
    def display_scraping_progress(card_number: int, total_cards: int, card_name: str):
        """Display scraping progress."""
        percentage = (card_number / total_cards) * 100
        print(f"\r  Progress: [{card_number}/{total_cards}] ({percentage:.1f}%) - {card_name[:40]}", end="", flush=True)

    @staticmethod
    def display_message(message: str, message_type: str = "info"):
        """Display a formatted message."""
        if message_type == "success":
            print(f"  ✅ {message}")
        elif message_type == "error":
            print(f"  ❌ {message}")
        elif message_type == "info":
            print(f"  ℹ️  {message}")
        elif message_type == "warning":
            print(f"  ⚠️  {message}")

    @staticmethod
    def display_loading(message: str = "Loading..."):
        """Display a loading message."""
        print(f"\n  ⏳ {message}", end="", flush=True)

    @staticmethod
    def clear_loading():
        """Clear the loading message."""
        print("\r" + " " * 80 + "\r", end="", flush=True)
