from __future__ import annotations

from collections.abc import Sequence

from src.utils.cli import run_cli


def main(args: Sequence[str] | None = None) -> int:
    return run_cli(args)
