"""Market ranking CLI for public real estate feature datasets."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TextIO

from src.config.globals import (
    PUBLIC_DATA_DIR,
    RANKING_FIELDNAMES,
)
from src.config.types import GroupBy, OutputFormat, SortBy
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MarketRankingOptions:
    """Parsed options for the market ranking CLI."""

    input_path: Path | None
    group_by: GroupBy
    voivodeships: tuple[str, ...]
    estate_types: tuple[str, ...]
    min_records: int
    limit: int
    sort_by: SortBy
    ascending: bool
    output_format: OutputFormat
    include_suppressed_location: bool


@dataclass(frozen=True)
class PublicMarketRecord:
    """Minimal public feature fields required for market ranking."""

    estate_type: str
    voivodeship: str
    city: str | None
    public_target_price_pln: float | None
    public_target_price_per_sqm_pln: float | None


@dataclass(frozen=True)
class MarketRankingRow:
    """One grouped market ranking result."""

    rank: int
    group: str
    records_count: int
    median_price_per_sqm_pln: float | None
    avg_price_per_sqm_pln: float | None
    q25_price_per_sqm_pln: float | None
    q75_price_per_sqm_pln: float | None
    median_price_pln: float | None
    share_with_price_per_sqm: float
    share_with_total_price: float


def build_parser() -> argparse.ArgumentParser:
    """Build the market ranking CLI parser."""
    parser = argparse.ArgumentParser(
        prog="market-ranking",
        description=(
            "Rank public real estate markets by price, coverage, and listing volume."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        dest="input_path",
        help=(
            "Path to a public ML feature CSV. Defaults to the latest "
            "data/public/estate_public_ml_features_*.csv file."
        ),
    )
    parser.add_argument(
        "--group-by",
        choices=(
            "voivodeship",
            "city",
            "estate_type",
            "voivodeship_city",
            "voivodeship_estate_type",
        ),
        default="voivodeship",
        help="Market grain used for ranking. Defaults to voivodeship.",
    )
    parser.add_argument(
        "--voivodeship",
        action="append",
        dest="voivodeships",
        metavar="SLUG",
        help="Filter by voivodeship slug. Can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--estate-type",
        action="append",
        dest="estate_types",
        metavar="SLUG",
        help="Filter by estate type. Can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--min-records",
        type=_positive_int,
        default=10,
        help="Minimum records required for a group to appear. Defaults to 10.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="Maximum number of ranked rows to print. Defaults to 20.",
    )
    parser.add_argument(
        "--sort-by",
        choices=(
            "records_count",
            "median_price_per_sqm_pln",
            "avg_price_per_sqm_pln",
            "median_price_pln",
            "share_with_price_per_sqm",
        ),
        default="median_price_per_sqm_pln",
        help="Metric used for ranking. Defaults to median price per sqm.",
    )
    parser.add_argument(
        "--ascending",
        action="store_true",
        help="Sort from lowest to highest value.",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        dest="output_format",
        help="Output format. Defaults to table.",
    )
    parser.add_argument(
        "--include-suppressed-location",
        action="store_true",
        help=(
            "Include rows with suppressed city labels when grouping by city-based "
            "grains. By default they are skipped."
        ),
    )

    return parser


def parse_cli_args(args: Sequence[str] | None = None) -> MarketRankingOptions:
    """Parse command-line arguments into typed market ranking options."""
    namespace = build_parser().parse_args(args)

    return MarketRankingOptions(
        input_path=namespace.input_path,
        group_by=namespace.group_by,
        voivodeships=tuple(_split_values(namespace.voivodeships)),
        estate_types=tuple(_split_values(namespace.estate_types)),
        min_records=namespace.min_records,
        limit=namespace.limit,
        sort_by=namespace.sort_by,
        ascending=namespace.ascending,
        output_format=namespace.output_format,
        include_suppressed_location=namespace.include_suppressed_location,
    )


def run_cli(
    args: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
) -> int:
    """Run the market ranking CLI workflow."""
    options = parse_cli_args(args)
    input_path = options.input_path or find_latest_public_ml_features()
    logger.debug("Market ranking started for %s", input_path)
    records = load_public_market_records(input_path)
    ranking = build_market_ranking(records, options=options)
    render_ranking(ranking, output_format=options.output_format, stdout=stdout)
    logger.debug("Market ranking finished: rows=%s", len(ranking))

    return 0


def find_latest_public_ml_features(public_dir: Path = PUBLIC_DATA_DIR) -> Path:
    """Find the latest public ML feature CSV snapshot."""
    snapshots = sorted(public_dir.glob("estate_public_ml_features_*.csv"))

    if not snapshots:
        raise FileNotFoundError(f"No public ML feature snapshots found in {public_dir}")

    return snapshots[-1]


def load_public_market_records(input_path: Path) -> list[PublicMarketRecord]:
    """Load public feature rows used by market ranking."""
    records: list[PublicMarketRecord] = []

    with input_path.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)

        for row in reader:
            records.append(
                PublicMarketRecord(
                    estate_type=row.get("estate_type", ""),
                    voivodeship=row.get("voivodeship", ""),
                    city=_optional_text(row.get("city")),
                    public_target_price_pln=_optional_float(
                        row.get("public_target_price_pln")
                    ),
                    public_target_price_per_sqm_pln=_optional_float(
                        row.get("public_target_price_per_sqm_pln")
                    ),
                )
            )

    return records


def build_market_ranking(
    records: Iterable[PublicMarketRecord],
    *,
    options: MarketRankingOptions,
) -> list[MarketRankingRow]:
    """Build ranked market groups from public feature records."""
    selected_voivodeships = set(options.voivodeships)
    selected_estate_types = set(options.estate_types)
    groups: dict[str, list[PublicMarketRecord]] = {}

    for record in records:
        if selected_voivodeships and record.voivodeship not in selected_voivodeships:
            continue

        if selected_estate_types and record.estate_type not in selected_estate_types:
            continue

        group_key = _group_key(
            record,
            group_by=options.group_by,
            include_suppressed_location=options.include_suppressed_location,
        )

        if group_key is None:
            continue

        groups.setdefault(group_key, []).append(record)

    ranking_rows = [
        _build_ranking_row(group=group, records=group_records)
        for group, group_records in groups.items()
        if len(group_records) >= options.min_records
    ]
    sorted_rows = _sort_ranking_rows(
        ranking_rows,
        sort_by=options.sort_by,
        ascending=options.ascending,
    )

    return [
        replace(row, rank=index)
        for index, row in enumerate(sorted_rows[: options.limit], start=1)
    ]


def render_ranking(
    rows: Sequence[MarketRankingRow],
    *,
    output_format: OutputFormat,
    stdout: TextIO,
) -> None:
    """Render ranking rows to stdout."""
    if output_format == "json":
        json.dump(
            [asdict(row) for row in rows],
            stdout,
            ensure_ascii=False,
            indent=2,
        )
        stdout.write("\n")
        return

    if output_format == "csv":
        writer = csv.DictWriter(stdout, fieldnames=list(RANKING_FIELDNAMES))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
        return

    _render_table(rows, stdout=stdout)


def _build_ranking_row(
    *,
    group: str,
    records: Sequence[PublicMarketRecord],
) -> MarketRankingRow:
    price_per_sqm_values = [
        record.public_target_price_per_sqm_pln
        for record in records
        if record.public_target_price_per_sqm_pln is not None
    ]
    price_values = [
        record.public_target_price_pln
        for record in records
        if record.public_target_price_pln is not None
    ]

    return MarketRankingRow(
        rank=0,
        group=group,
        records_count=len(records),
        median_price_per_sqm_pln=_median(price_per_sqm_values),
        avg_price_per_sqm_pln=_mean(price_per_sqm_values),
        q25_price_per_sqm_pln=_quantile(price_per_sqm_values, 0.25),
        q75_price_per_sqm_pln=_quantile(price_per_sqm_values, 0.75),
        median_price_pln=_median(price_values),
        share_with_price_per_sqm=_round_share(len(price_per_sqm_values), len(records)),
        share_with_total_price=_round_share(len(price_values), len(records)),
    )


def _group_key(
    record: PublicMarketRecord,
    *,
    group_by: GroupBy,
    include_suppressed_location: bool,
) -> str | None:
    city = record.city or "suppressed"

    if group_by == "voivodeship":
        return record.voivodeship

    if group_by == "estate_type":
        return record.estate_type

    if group_by == "voivodeship_estate_type":
        return f"{record.voivodeship}/{record.estate_type}"

    if group_by == "city":
        if record.city is None and not include_suppressed_location:
            return None

        return city

    if record.city is None and not include_suppressed_location:
        return None

    return f"{record.voivodeship}/{city}"


def _sort_ranking_rows(
    rows: Sequence[MarketRankingRow],
    *,
    sort_by: SortBy,
    ascending: bool,
) -> list[MarketRankingRow]:
    populated_rows: list[MarketRankingRow] = []
    missing_rows: list[MarketRankingRow] = []

    for row in rows:
        if getattr(row, sort_by) is None:
            missing_rows.append(row)
            continue

        populated_rows.append(row)

    return [
        *sorted(
            populated_rows,
            key=lambda row: float(getattr(row, sort_by)),
            reverse=not ascending,
        ),
        *sorted(missing_rows, key=lambda row: row.group),
    ]


def _render_table(rows: Sequence[MarketRankingRow], *, stdout: TextIO) -> None:
    headers = (
        "rank",
        "group",
        "records",
        "median_sqm",
        "avg_sqm",
        "q25_sqm",
        "q75_sqm",
        "median_price",
        "sqm_cov",
    )
    table_rows = [
        (
            str(row.rank),
            row.group,
            str(row.records_count),
            _format_money(row.median_price_per_sqm_pln),
            _format_money(row.avg_price_per_sqm_pln),
            _format_money(row.q25_price_per_sqm_pln),
            _format_money(row.q75_price_per_sqm_pln),
            _format_money(row.median_price_pln),
            _format_percent(row.share_with_price_per_sqm),
        )
        for row in rows
    ]
    widths = [
        (
            max(len(headers[index]), *(len(row[index]) for row in table_rows))
            if table_rows
            else len(headers[index])
        )
        for index in range(len(headers))
    ]
    header_line = "  ".join(
        header.ljust(widths[index]) for index, header in enumerate(headers)
    )
    separator_line = "  ".join("-" * width for width in widths)
    stdout.write(header_line + "\n")
    stdout.write(separator_line + "\n")

    for row in table_rows:
        stdout.write(
            "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
            + "\n"
        )


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None

    return round(statistics.median(values), 2)


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None

    return round(statistics.fmean(values), 2)


def _quantile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None

    sorted_values = sorted(values)
    index = round((len(sorted_values) - 1) * fraction)

    return round(sorted_values[index], 2)


def _round_share(count: int, total: int) -> float:
    if total == 0:
        return 0

    return round(count / total, 4)


def _format_money(value: float | None) -> str:
    if value is None:
        return ""

    return f"{value:,.0f}".replace(",", " ")


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped_value = value.strip()

    return stripped_value or None


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None

    return float(value)


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


if __name__ == "__main__":
    raise SystemExit(run_cli())
