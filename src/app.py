"""Application bootstrap helpers for command-line execution."""

from __future__ import annotations

from collections.abc import Sequence

from src.utils.cli import run_cli


def main(args: Sequence[str] | None = None) -> int:
    """Run the application CLI.

    Args:
        args: Optional command-line arguments. When omitted, arguments are read
            from the current process.

    Returns:
        Process exit code returned by the CLI.
    """
    return run_cli(args)
