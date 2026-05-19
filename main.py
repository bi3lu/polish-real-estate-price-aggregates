"""Command-line entry point for the real estate scraping application."""

from __future__ import annotations

import sys

from src.app import main

if __name__ == "__main__":
    sys.exit(main())
