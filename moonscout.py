"""MoonScout - Terminal entry point for crescent moon observation assistant."""

import sys
from agent import run_agent


def print_header():
    """Print the MoonScout welcome header."""
    print()
    print("=" * 60)
    print("  🌙  MoonScout — Crescent Moon Observation Assistant")
    print("=" * 60)
    print()
    print("  Find the best locations to observe the crescent moon.")
    print("  Supports hilal sighting and general crescent viewing.")
    print()
    print("  Example queries:")
    print('    "Best spot to see the crescent near London this Friday"')
    print('    "Where can I sight the hilal within 30 miles of Chicago?"')
    print('    "Crescent moon viewing spots near Islamabad next week"')
    print()
    print("-" * 60)
    print()


def status_update(message: str):
    """Print a status update during agent execution."""
    print(f"  [{message}]")


def main():
    """Main terminal interface for MoonScout."""
    print_header()

    # Check if query was passed as command line argument
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"  Query: {query}")
    else:
        try:
            query = input("  Ask MoonScout: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Goodbye! Clear skies!")
            return

    if not query:
        print("  Please enter a query. Example: 'Best crescent viewing near NYC tonight'")
        return

    print()
    print("  Scouting locations...")
    print()

    try:
        response = run_agent(query, status_callback=status_update)
        print()
        print("-" * 60)
        print()
        print(response)
        print()
        print("-" * 60)
        print("  🌙 Happy observing! Clear skies!")
        print()

    except ValueError as e:
        print(f"\n  Configuration error: {e}")
        print("  Make sure your .env file has a valid OPENAI_API_KEY.")
    except Exception as e:
        print(f"\n  An error occurred: {e}")
        print("  Please check your internet connection and try again.")


if __name__ == "__main__":
    main()
