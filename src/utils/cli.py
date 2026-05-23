"""Command-line interface for ingesting bronze real estate snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import TextIO

from src.config.globals import (
    DEFAULT_SEARCH_SHARD_STRATEGY,
    DEFAULT_WORKERS,
    ESTATE_TYPES,
    MAX_PAGE,
    RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    VOIVODESHIPS,
)
from src.config.source_config import load_source_config
from src.ingestion.adapters.base import PaginatedListingSourceAdapter, SourceAdapter
from src.ingestion.estate_ingestion import iter_estates
from src.ingestion.models import RawListingObservation
from src.ingestion.registry import build_adapters
from src.utils.logger import get_logger
from src.utils.storage import (
    load_bronze_external_ids_by_voivodeship,
    load_bronze_page_checkpoints,
    stream_estates_to_bronze,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class CliOptions:
    """Parsed command-line options for an ingestion run."""

    estate_types: tuple[str, ...]
    voivodeships: tuple[str, ...]
    max_page: int
    workers: int
    pretty: bool
    ignore_checkpoints: bool
    duplicate_page_stop_threshold: int
    search_shard_strategy: str
    source_config_path: Path | None = None


IngestFn = Callable[..., Iterable[RawListingObservation]]
SaveFn = Callable[..., tuple[Path, int]]
ValidateFn = Callable[[], None]
ExistingIdsLoaderFn = Callable[[], dict[str, set[str]]]
PageCheckpointsLoaderFn = Callable[[], dict[str, dict[str, int]]]


def build_parser() -> argparse.ArgumentParser:
    """Build the estate ingestion argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="estate-ingestion",
        description="Ingest real estate listings and save a bronze JSON snapshot.",
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
        help=f"Maximum page to process per filter combination. Defaults to {MAX_PAGE}.",
    )
    parser.add_argument(
        "--workers",
        "--threads",
        type=_positive_int,
        default=DEFAULT_WORKERS,
        help=(
            "Number of worker threads used to process filter combinations. "
            f"Defaults to {DEFAULT_WORKERS}."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--ignore-checkpoints",
        action="store_true",
        help=(
            "Start selected ingestion targets from page 1 instead of using saved "
            "resume page checkpoints. Existing bronze ids are still deduplicated."
        ),
    )
    parser.add_argument(
        "--duplicate-page-stop-threshold",
        type=_non_negative_int,
        default=RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
        help=(
            "Stop a resume/refresh target after this many consecutive pages "
            "containing only duplicate listings. Use 0 to disable this stop; "
            "repeated listing pages are still detected. Defaults to "
            f"{RESUME_DUPLICATE_PAGE_STOP_THRESHOLD}."
        ),
    )
    parser.add_argument(
        "--shard-strategy",
        choices=("none", "price", "market-price"),
        default=DEFAULT_SEARCH_SHARD_STRATEGY,
        help=(
            "Split large source searches into smaller listing queries. "
            f"Defaults to {DEFAULT_SEARCH_SHARD_STRATEGY}."
        ),
    )
    parser.add_argument(
        "--source-config",
        type=Path,
        default=None,
        help=(
            "Path to a source YAML config. Defaults to config/sources.local.yaml "
            "when present, otherwise config/sources.example.yaml."
        ),
    )

    return parser


def parse_cli_args(args: Sequence[str] | None = None) -> CliOptions:
    """Parse command-line arguments into typed options.

    Args:
        args: Optional argument sequence. When omitted, ``argparse`` reads from
            the current process.

    Returns:
        Parsed CLI options.
    """
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
            ignore_checkpoints=namespace.ignore_checkpoints,
            duplicate_page_stop_threshold=namespace.duplicate_page_stop_threshold,
            search_shard_strategy=namespace.shard_strategy,
            source_config_path=namespace.source_config,
        )

    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))


def _validate_required_runtime_env() -> None:
    """Compatibility no-op for callers that still inject a validator."""
    return None


def run_cli(
    args: Sequence[str] | None = None,
    *,
    ingester: IngestFn = iter_estates,
    saver: SaveFn = stream_estates_to_bronze,
    validator: ValidateFn = _validate_required_runtime_env,
    existing_ids_loader: ExistingIdsLoaderFn = load_bronze_external_ids_by_voivodeship,
    page_checkpoints_loader: PageCheckpointsLoaderFn = load_bronze_page_checkpoints,
    stdout: TextIO = sys.stdout,
) -> int:
    """Run the listing ingestion CLI workflow.

    Args:
        args: Optional command-line arguments.
        ingester: Callable that yields ingested estates.
        saver: Callable that persists ingested estates.
        validator: Callable that validates runtime configuration.
        existing_ids_loader: Callable that loads already persisted listing ids.
        page_checkpoints_loader: Callable that loads resume page checkpoints.
        stdout: Text stream receiving the JSON command result.

    Returns:
        Process exit code.
    """
    validator()
    options = parse_cli_args(args)
    source_config = load_source_config(options.source_config_path)
    adapters = build_adapters(
        source_config,
        property_types=options.estate_types,
        voivodeships=options.voivodeships,
        max_pages=options.max_page,
    )
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
    start_pages_by_target = (
        {} if options.ignore_checkpoints else page_checkpoints_loader()
    )
    page_checkpoints_by_voivodeship: dict[str, dict[str, int]] = {}
    page_checkpoint_lock = Lock()

    def progress_callback(
        estate_type: str,
        voivodeship: str,
        page: int,
    ) -> None:
        with page_checkpoint_lock:
            previous_page = page_checkpoints_by_voivodeship.get(voivodeship, {}).get(
                estate_type,
                0,
            )
            page_checkpoints_by_voivodeship.setdefault(voivodeship, {})[estate_type] = (
                max(previous_page, page)
            )

    estates = ingester(
        estate_types=options.estate_types,
        voivodeships=options.voivodeships,
        max_page=options.max_page,
        workers=options.workers,
        existing_external_ids_by_voivodeship=existing_external_ids_by_voivodeship,
        start_pages_by_target=start_pages_by_target,
        duplicate_page_stop_threshold=options.duplicate_page_stop_threshold,
        search_shard_strategy=options.search_shard_strategy,
        progress_callback=progress_callback,
        sources=adapters,
    )
    output_path, count = saver(
        estates,
        estate_types=options.estate_types,
        voivodeships=options.voivodeships,
        max_page=options.max_page,
        page_checkpoints_by_voivodeship=page_checkpoints_by_voivodeship,
        adapter_types_by_source_id=_adapter_types_by_source_id(adapters),
    )
    logger.info("Bronze snapshot saved to %s with %s records", output_path, count)
    json.dump(
        {
            "output_path": str(output_path),
            "count": count,
            "estate_types": list(options.estate_types),
            "voivodeships": list(options.voivodeships),
            "workers": options.workers,
            "ignore_checkpoints": options.ignore_checkpoints,
            "duplicate_page_stop_threshold": options.duplicate_page_stop_threshold,
            "search_shard_strategy": options.search_shard_strategy,
            "source_ids": [adapter.source_id for adapter in adapters],
        },
        stdout,
        ensure_ascii=False,
        indent=2 if options.pretty else None,
    )
    stdout.write("\n")

    return 0


def _adapter_types_by_source_id(
    adapters: Iterable[SourceAdapter],
) -> dict[str, str]:
    return {
        adapter.source_id: adapter.config.adapter_type
        for adapter in adapters
        if isinstance(adapter, PaginatedListingSourceAdapter)
    }


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


def _non_negative_int(value: str) -> int:
    parsed_value = int(value)

    if parsed_value < 0:
        raise argparse.ArgumentTypeError("value must be greater than or equal to 0")

    return parsed_value
