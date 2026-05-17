from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from src.config.env import get_required_env_file_value
from src.config.globals import ESTATE_TYPES, MAX_PAGE, VOIVODESHIPS, DEFAULT_WORKERS
from src.models.estate import Estate
from src.scraper.estate_scraper import iter_estates
from src.utils.logger import get_logger
from src.utils.storage import (
    load_bronze_external_ids_by_voivodeship,
    stream_estates_to_bronze,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class CliOptions:
    estate_types: tuple[str, ...]
    voivodeships: tuple[str, ...]
    max_page: int
    workers: int
    pretty: bool


ScrapeFn = Callable[..., Iterable[Estate]]
SaveFn = Callable[..., tuple[Path, int]]
ValidateFn = Callable[[], None]
ExistingIdsLoaderFn = Callable[[], dict[str, set[str]]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="estate-scraper",
        description="Scrape real estate listings and save a bronze JSON snapshot.",
    )
    parser.add_argument(
        "-v",
        "--voivodeship",
        action="append",
        dest="voivodeships",
        metavar="SLUG",
        help=(
            "Voivodeship slug. Can be passed multiple times or as comma-separated "
            "values. Defaults to all configured voivodeships."
        ),
    )
    parser.add_argument(
        "-t",
        "--estate-type",
        action="append",
        dest="estate_types",
        metavar="SLUG",
        help=(
            "Estate type slug. Can be passed multiple times or as comma-separated "
            "values. Defaults to all configured estate types."
        ),
    )
    parser.add_argument(
        "--max-page",
        type=_positive_int,
        default=MAX_PAGE,
        help=f"Maximum page to scrape per filter combination. Defaults to {MAX_PAGE}.",
    )
    parser.add_argument(
        "--workers",
        "--threads",
        type=_positive_int,
        default=DEFAULT_WORKERS,
        help=(
            "Number of worker threads used to scrape filter combinations. "
            f"Defaults to {DEFAULT_WORKERS}."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    return parser


def parse_cli_args(args: Sequence[str] | None = None) -> CliOptions:
    parser = build_parser()
    namespace = parser.parse_args(args)

    try:
        return CliOptions(
            estate_types=_resolve_values(
                namespace.estate_types,
                allowed_values=ESTATE_TYPES,
                argument_name="--estate-type",
            ),
            voivodeships=_resolve_values(
                namespace.voivodeships,
                allowed_values=VOIVODESHIPS,
                argument_name="--voivodeship",
            ),
            max_page=namespace.max_page,
            workers=namespace.workers,
            pretty=namespace.pretty,
        )

    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))


def _validate_required_runtime_env() -> None:
    get_required_env_file_value("MAIN_URL")
    get_required_env_file_value("ESTATE_URL")


def run_cli(
    args: Sequence[str] | None = None,
    *,
    scraper: ScrapeFn = iter_estates,
    saver: SaveFn = stream_estates_to_bronze,
    validator: ValidateFn = _validate_required_runtime_env,
    existing_ids_loader: ExistingIdsLoaderFn = load_bronze_external_ids_by_voivodeship,
    stdout: TextIO = sys.stdout,
) -> int:
    validator()
    options = parse_cli_args(args)
    logger.info(
        "CLI run started: estate_types=%s voivodeships=%s max_page=%s workers=%s",
        ", ".join(options.estate_types),
        ", ".join(options.voivodeships),
        options.max_page,
        options.workers,
    )
    existing_external_ids_by_voivodeship = existing_ids_loader()
    selected_existing_count = sum(
        len(existing_external_ids_by_voivodeship.get(voivodeship, set()))
        for voivodeship in options.voivodeships
    )
    logger.info(
        "Loaded %s existing bronze external ids for selected voivodeships",
        selected_existing_count,
    )
    estates = scraper(
        estate_types=options.estate_types,
        voivodeships=options.voivodeships,
        max_page=options.max_page,
        workers=options.workers,
        existing_external_ids_by_voivodeship=existing_external_ids_by_voivodeship,
    )
    output_path, count = saver(
        estates,
        estate_types=options.estate_types,
        voivodeships=options.voivodeships,
        max_page=options.max_page,
    )
    logger.info("Bronze snapshot saved to %s with %s records", output_path, count)
    json.dump(
        {
            "output_path": str(output_path),
            "count": count,
            "estate_types": list(options.estate_types),
            "voivodeships": list(options.voivodeships),
            "workers": options.workers,
        },
        stdout,
        ensure_ascii=False,
        indent=2 if options.pretty else None,
    )
    stdout.write("\n")

    return 0


def _resolve_values(
    values: Sequence[str] | None,
    *,
    allowed_values: Iterable[str],
    argument_name: str,
) -> tuple[str, ...]:
    allowed_set = set(allowed_values)
    selected_values = _split_values(values)

    if not selected_values:
        return tuple(sorted(allowed_set))

    unknown_values = sorted(set(selected_values) - allowed_set)

    if unknown_values:
        allowed_text = ", ".join(sorted(allowed_set))
        unknown_text = ", ".join(unknown_values)
        raise argparse.ArgumentTypeError(
            f"{argument_name} has unsupported value(s): {unknown_text}. "
            f"Allowed values: {allowed_text}"
        )

    return tuple(dict.fromkeys(selected_values))


def _split_values(values: Sequence[str] | None) -> list[str]:
    if values is None:
        return []

    split_values: list[str] = []

    for value in values:
        split_values.extend(part.strip() for part in value.split(",") if part.strip())

    return split_values


def _positive_int(value: str) -> int:
    parsed_value = int(value)

    if parsed_value < 1:
        raise argparse.ArgumentTypeError("value must be greater than or equal to 1")

    return parsed_value
