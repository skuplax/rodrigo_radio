#!/usr/bin/env python3
"""Entry point for Rodrigo Radio TUI Monitor.

Usage:
    python tui_monitor.py

Or make executable and run:
    chmod +x tui_monitor.py
    ./tui_monitor.py
"""

import sys
from pathlib import Path

# Add the project root to the path for imports
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass  # python-dotenv not required but helpful


def main():
    """Main entry point."""
    try:
        from tui.app import run_app
        run_app()
    except ImportError as e:
        print(f"Error: Missing dependencies. {e}")
        print("\nPlease install TUI dependencies:")
        print("  pip install -r requirements-tui.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()


