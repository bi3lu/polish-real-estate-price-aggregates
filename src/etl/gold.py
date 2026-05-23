"""Silver-to-gold ETL transformations and aggregate builders."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.config.globals import GOLD_DATA_DIR, SILVER_DATA_DIR
from src.config.types import T
from src.ingestion.models import CanonicalListing
from src.models.gold_estate import (
    GoldDataQuality,
    GoldGeoAggregate,
    GoldListingFeature,
    GoldSegmentAggregate,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GoldTables:
    """Container for all gold-layer tables produced by the ETL stage."""

    ml_features: list[GoldListingFeature]
    geo_aggregates: list[GoldGeoAggregate]
    segment_aggregates: list[GoldSegmentAggregate]
    data_quality: list[GoldDataQuality]


@dataclass(frozen=True)
class GoldOutputPaths:
    """Filesystem paths for written gold-layer CSV snapshots."""

    ml_features: Path
    geo_aggregates: Path
    segment_aggregates: Path
    data_quality: Path


def run_silver_to_gold(
    *,
    silver_path: Path | None = None,
    silver_dir: Path = SILVER_DATA_DIR,
    gold_dir: Path = GOLD_DATA_DIR,
    processed_at: datetime | None = None,
) -> GoldOutputPaths:
    """Run the silver-to-gold ETL stage.

    Args:
        silver_path: Optional explicit silver CSV path. When omitted, the latest
            silver snapshot is selected from ``silver_dir``.
        silver_dir: Directory containing silver CSV snapshots.
        gold_dir: Directory where gold CSV snapshots are written.
        processed_at: Optional timestamp used for deterministic outputs.

    Returns:
        Paths to all written gold CSV snapshots.
    """
    selected_silver_path = silver_path or find_latest_silver_snapshot(silver_dir)
    snapshot_time = processed_at or datetime.now(timezone.utc)
    logger.info("Gold ETL started for silver snapshot %s", selected_silver_path)
    silver_records = load_silver_snapshot(selected_silver_path)
    gold_tables = transform_silver_records(
        silver_records,
        processed_at=snapshot_time,
    )
    output_paths = save_gold_tables(
        gold_tables,
        output_dir=gold_dir,
        processed_at=snapshot_time,
    )
    logger.info(
        "Gold ETL finished: ml_features=%s geo_aggregates=%s "
        "segment_aggregates=%s data_quality=%s",
        len(gold_tables.ml_features),
        len(gold_tables.geo_aggregates),
        len(gold_tables.segment_aggregates),
        len(gold_tables.data_quality),
    )

    return output_paths


def find_latest_silver_snapshot(silver_dir: Path = SILVER_DATA_DIR) -> Path:
    """Find the latest silver CSV snapshot.

    Args:
        silver_dir: Directory containing silver CSV files.

    Returns:
        Path to the most recent silver snapshot.

    Raises:
        FileNotFoundError: If the directory contains no silver snapshots.
    """
    snapshots = sorted(silver_dir.glob("estate_silver_*.csv"))

    if not snapshots:
        raise FileNotFoundError(f"No silver snapshots found in {silver_dir}")

    return snapshots[-1]


def load_silver_snapshot(silver_path: Path) -> list[CanonicalListing]:
    """Load and validate silver records from a CSV snapshot.

    Args:
        silver_path: CSV file to load.

    Returns:
        Valid silver records. Invalid rows are skipped and logged.
    """
    records: list[CanonicalListing] = []

    with silver_path.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)

        for line_number, row in enumerate(reader, start=2):
            try:
                records.append(CanonicalListing.model_validate(_parse_silver_row(row)))

            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid silver row in %s:%s: %s",
                    silver_path,
                    line_number,
                    exc,
                )

    return records


def transform_silver_records(
    records: Iterable[CanonicalListing],
    *,
    processed_at: datetime | None = None,
) -> GoldTables:
    """Transform silver records into gold feature, aggregate, and quality tables.

    Args:
        records: Silver records to transform.
        processed_at: Optional processing timestamp for deterministic outputs.

    Returns:
        Grouped gold tables ready to be written to CSV.
    """
    snapshot_time = processed_at or datetime.now(timezone.utc)
    processed_at_text = snapshot_time.isoformat()
    record_list = list(records)
    ml_features = [
        build_listing_feature(record, processed_at=processed_at_text)
        for record in record_list
    ]

    return GoldTables(
        ml_features=ml_features,
        geo_aggregates=build_geo_aggregates(
            ml_features,
            processed_at=processed_at_text,
        ),
        segment_aggregates=build_segment_aggregates(
            ml_features,
            processed_at=processed_at_text,
        ),
        data_quality=build_data_quality(
            ml_features,
            processed_at=processed_at_text,
        ),
    )


def build_listing_feature(
    record: CanonicalListing,
    *,
    processed_at: str,
) -> GoldListingFeature:
    """Build a model-ready gold feature row from one silver record.

    Args:
        record: Source silver listing record.
        processed_at: ISO timestamp assigned to the output row.

    Returns:
        Enriched listing feature row.
    """
    price_per_sqm, price_per_sqm_source = _resolve_price_per_sqm(record)
    total_monthly_cost = _sum_optional(record.price_pln, record.rent_pln)
    amenities = (
        record.has_lift,
        record.has_balcony,
        record.has_garage,
        record.has_basement,
        record.has_separate_kitchen,
        record.has_air_conditioning,
        record.has_garden,
    )

    return GoldListingFeature(
        record_id=_anonymize_record_id(record.record_id),
        estate_type=record.estate_type,
        voivodeship=record.voivodeship,
        city=record.city,
        district=record.district,
        latitude=record.latitude,
        longitude=record.longitude,
        price_pln=record.price_pln,
        price_per_sqm_pln=price_per_sqm,
        rent_pln=record.rent_pln,
        area_sqm=record.area_sqm,
        terrain_area_sqm=record.terrain_area_sqm,
        rooms=record.rooms,
        floor=record.floor,
        building_floors_num=record.building_floors_num,
        market=record.market,
        building_type=record.building_type,
        build_year=record.build_year,
        seller_type=record.seller_type,
        has_lift=record.has_lift,
        has_balcony=record.has_balcony,
        has_garage=record.has_garage,
        has_basement=record.has_basement,
        has_separate_kitchen=record.has_separate_kitchen,
        has_air_conditioning=record.has_air_conditioning,
        has_garden=record.has_garden,
        image_count=record.image_count,
        has_coordinates=record.has_coordinates,
        is_price_outlier=_is_price_outlier(record.price_pln, price_per_sqm),
        price_per_sqm_source=price_per_sqm_source,
        total_monthly_cost_pln=total_monthly_cost,
        area_bucket=_bucket_number(
            record.area_sqm,
            (
                (35, "lt_35"),
                (50, "35_50"),
                (70, "50_70"),
                (100, "70_100"),
                (150, "100_150"),
            ),
            "gte_150",
        ),
        price_bucket=_bucket_number(
            record.price_pln,
            (
                (300_000, "lt_300k"),
                (500_000, "300k_500k"),
                (750_000, "500k_750k"),
                (1_000_000, "750k_1m"),
                (1_500_000, "1m_1_5m"),
            ),
            "gte_1_5m",
        ),
        rooms_bucket=_bucket_rooms(record.rooms),
        building_age_years=_building_age(record.build_year),
        floor_ratio=_safe_ratio(record.floor, record.building_floors_num),
        amenity_count=sum(1 for amenity in amenities if amenity),
        geo_precision=_geo_precision(record),
        ml_target_price_pln=record.price_pln,
        ml_target_price_per_sqm_pln=price_per_sqm,
        processed_at=processed_at,
    )


def build_geo_aggregates(
    records: Iterable[GoldListingFeature],
    *,
    processed_at: str,
) -> list[GoldGeoAggregate]:
    """Build geographic aggregates from gold listing features.

    Args:
        records: Gold listing features to aggregate.
        processed_at: ISO timestamp assigned to aggregate rows.

    Returns:
        Geographic aggregate rows sorted by aggregate key.
    """
    return _aggregate_groups(
        records,
        key_fn=lambda record: (
            record.voivodeship,
            record.city,
            record.district,
            record.estate_type,
        ),
        build_fn=lambda key, group: _build_geo_aggregate(
            key,
            group,
            processed_at=processed_at,
        ),
    )


def build_segment_aggregates(
    records: Iterable[GoldListingFeature],
    *,
    processed_at: str,
) -> list[GoldSegmentAggregate]:
    """Build market segment aggregates from gold listing features.

    Args:
        records: Gold listing features to aggregate.
        processed_at: ISO timestamp assigned to aggregate rows.

    Returns:
        Segment aggregate rows sorted by aggregate key.
    """
    return _aggregate_groups(
        records,
        key_fn=lambda record: (
            record.estate_type,
            record.voivodeship,
            record.market,
            record.building_type,
            record.rooms_bucket,
            record.area_bucket,
        ),
        build_fn=lambda key, group: _build_segment_aggregate(
            key,
            group,
            processed_at=processed_at,
        ),
    )


def build_data_quality(
    records: Iterable[GoldListingFeature],
    *,
    processed_at: str,
) -> list[GoldDataQuality]:
    """Build data quality metrics for a gold ETL run.

    Args:
        records: Gold listing features to measure.
        processed_at: ISO timestamp assigned to metric rows.

    Returns:
        Data quality metric rows.
    """
    record_list = list(records)
    total = len(record_list)

    return [
        _quality_metric(
            "records_count",
            float(total),
            total,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_price",
            _share(record.price_pln is not None for record in record_list),
            total,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_price_per_sqm",
            _share(record.price_per_sqm_pln is not None for record in record_list),
            total,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_coordinates",
            _share(record.has_coordinates for record in record_list),
            total,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_price_outliers",
            _share(record.is_price_outlier for record in record_list),
            total,
            processed_at=processed_at,
        ),
        _quality_metric(
            "distinct_cities_count",
            float(len({record.city for record in record_list if record.city})),
            total,
            processed_at=processed_at,
        ),
    ]


def save_gold_tables(
    tables: GoldTables,
    *,
    output_dir: Path = GOLD_DATA_DIR,
    processed_at: datetime | None = None,
) -> GoldOutputPaths:
    """Write all gold tables to timestamped CSV snapshots.

    Args:
        tables: Gold tables to serialize.
        output_dir: Directory where CSV snapshots are written.
        processed_at: Optional timestamp used in output filenames.

    Returns:
        Paths to the written CSV files.
    """
    snapshot_time = processed_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot_time.strftime("%Y%m%dT%H%M%S%fZ")

    output_paths = GoldOutputPaths(
        ml_features=output_dir / f"estate_gold_ml_features_{timestamp}.csv",
        geo_aggregates=output_dir / f"estate_gold_geo_aggregates_{timestamp}.csv",
        segment_aggregates=output_dir
        / f"estate_gold_segment_aggregates_{timestamp}.csv",
        data_quality=output_dir / f"estate_gold_data_quality_{timestamp}.csv",
    )
    _write_model_csv(output_paths.ml_features, tables.ml_features, GoldListingFeature)
    _write_model_csv(
        output_paths.geo_aggregates,
        tables.geo_aggregates,
        GoldGeoAggregate,
    )
    _write_model_csv(
        output_paths.segment_aggregates,
        tables.segment_aggregates,
        GoldSegmentAggregate,
    )
    _write_model_csv(output_paths.data_quality, tables.data_quality, GoldDataQuality)

    return output_paths


def _build_geo_aggregate(
    key: tuple[str | None, ...],
    records: list[GoldListingFeature],
    *,
    processed_at: str,
) -> GoldGeoAggregate:
    voivodeship = key[0]
    city = key[1]
    district = key[2]
    estate_type = key[3]
    prices = _values(records, lambda record: record.price_pln)
    prices_per_sqm = _values(records, lambda record: record.price_per_sqm_pln)
    areas = _values(records, lambda record: record.area_sqm)

    return GoldGeoAggregate(
        geo_id=_build_id(voivodeship, city, district, estate_type),
        voivodeship=voivodeship,
        city=city,
        district=district,
        estate_type=estate_type,
        records_count=len(records),
        priced_records_count=len(prices),
        coordinate_records_count=sum(1 for record in records if record.has_coordinates),
        avg_latitude=_mean(_values(records, lambda record: record.latitude)),
        avg_longitude=_mean(_values(records, lambda record: record.longitude)),
        min_price_pln=min(prices) if prices else None,
        p25_price_pln=_percentile(prices, 0.25),
        median_price_pln=_median(prices),
        avg_price_pln=_mean(prices),
        p75_price_pln=_percentile(prices, 0.75),
        max_price_pln=max(prices) if prices else None,
        median_price_per_sqm_pln=_median(prices_per_sqm),
        avg_price_per_sqm_pln=_mean(prices_per_sqm),
        median_area_sqm=_median(areas),
        avg_area_sqm=_mean(areas),
        share_with_coordinates=_share(record.has_coordinates for record in records),
        share_agency=_share(record.seller_type == "agency" for record in records),
        share_private=_share(record.seller_type == "private" for record in records),
        processed_at=processed_at,
    )


def _build_segment_aggregate(
    key: tuple[str | None, ...],
    records: list[GoldListingFeature],
    *,
    processed_at: str,
) -> GoldSegmentAggregate:
    estate_type = key[0]
    voivodeship = key[1]
    market = key[2]
    building_type = key[3]
    rooms_bucket = key[4]
    area_bucket = key[5]
    prices = _values(records, lambda record: record.price_pln)
    prices_per_sqm = _values(records, lambda record: record.price_per_sqm_pln)
    areas = _values(records, lambda record: record.area_sqm)
    rents = _values(records, lambda record: record.rent_pln)

    return GoldSegmentAggregate(
        segment_id=_build_id(
            estate_type,
            voivodeship,
            market,
            building_type,
            rooms_bucket,
            area_bucket,
        ),
        estate_type=estate_type,
        voivodeship=voivodeship,
        market=market,
        building_type=building_type,
        rooms_bucket=rooms_bucket,
        area_bucket=area_bucket,
        records_count=len(records),
        priced_records_count=len(prices),
        median_price_pln=_median(prices),
        avg_price_pln=_mean(prices),
        median_price_per_sqm_pln=_median(prices_per_sqm),
        avg_price_per_sqm_pln=_mean(prices_per_sqm),
        median_area_sqm=_median(areas),
        avg_area_sqm=_mean(areas),
        median_rent_pln=_median(rents),
        share_with_lift=_share(record.has_lift for record in records),
        share_with_balcony=_share(record.has_balcony for record in records),
        share_with_garage=_share(record.has_garage for record in records),
        share_with_garden=_share(record.has_garden for record in records),
        share_with_air_conditioning=_share(
            record.has_air_conditioning for record in records
        ),
        processed_at=processed_at,
    )


def _parse_silver_row(row: dict[str, str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    bool_fields = {
        "has_lift",
        "has_balcony",
        "has_garage",
        "has_basement",
        "has_separate_kitchen",
        "has_air_conditioning",
        "has_garden",
        "has_price",
        "has_location",
        "has_coordinates",
    }
    int_fields = {
        "rooms",
        "floor",
        "building_floors_num",
        "build_year",
        "image_count",
    }
    float_fields = {
        "latitude",
        "longitude",
        "price_pln",
        "price_per_sqm_pln",
        "rent_pln",
        "area_sqm",
        "terrain_area_sqm",
    }

    for key, value in row.items():
        if key in bool_fields:
            parsed[key] = value.lower() == "true" if value else False

        elif value == "":
            parsed[key] = 0 if key == "image_count" else None

        elif key in int_fields:
            parsed[key] = int(value)

        elif key in float_fields:
            parsed[key] = float(value)

        else:
            parsed[key] = value

    return parsed


def _anonymize_record_id(record_id: str) -> str:
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:16]

    return f"gold_{digest}"


def _resolve_price_per_sqm(record: CanonicalListing) -> tuple[float | None, str | None]:
    if record.price_per_sqm_pln is not None:
        return record.price_per_sqm_pln, "source"

    if record.price_pln is None or record.area_sqm is None or record.area_sqm <= 0:
        return None, None

    return round(record.price_pln / record.area_sqm, 2), "derived"


def _is_price_outlier(
    price: float | None,
    price_per_sqm: float | None,
) -> bool:
    if price is not None and (price < 10_000 or price > 100_000_000):
        return True

    return price_per_sqm is not None and (
        price_per_sqm < 500 or price_per_sqm > 100_000
    )


def _sum_optional(first: float | None, second: float | None) -> float | None:
    if first is None and second is None:
        return None

    return (first or 0.0) + (second or 0.0)


def _bucket_number(
    value: float | None,
    thresholds: tuple[tuple[float, str], ...],
    fallback: str,
) -> str | None:
    if value is None:
        return None

    for upper_bound, label in thresholds:
        if value < upper_bound:
            return label

    return fallback


def _bucket_rooms(rooms: int | None) -> str | None:
    if rooms is None:
        return None

    if rooms <= 1:
        return "1"

    if rooms >= 5:
        return "5_plus"

    return str(rooms)


def _building_age(build_year: int | None) -> int | None:
    if build_year is None:
        return None

    current_year = datetime.now(timezone.utc).year

    if build_year > current_year:
        return None

    return current_year - build_year


def _safe_ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None

    return round(numerator / denominator, 4)


def _geo_precision(record: CanonicalListing) -> str:
    if record.has_coordinates:
        return "coordinates"

    if record.district:
        return "district"

    if record.city:
        return "city"

    if record.voivodeship:
        return "voivodeship"

    return "unknown"


def _aggregate_groups(
    records: Iterable[GoldListingFeature],
    *,
    key_fn: Callable[[GoldListingFeature], tuple[str | None, ...]],
    build_fn: Callable[[tuple[str | None, ...], list[GoldListingFeature]], T],
) -> list[T]:
    groups: dict[tuple[str | None, ...], list[GoldListingFeature]] = {}

    for record in records:
        groups.setdefault(key_fn(record), []).append(record)

    return [
        build_fn(key, groups[key])
        for key in sorted(
            groups,
            key=lambda values: tuple(value or "" for value in values),
        )
    ]


def _values(
    records: Iterable[GoldListingFeature],
    getter: Callable[[GoldListingFeature], float | int | None],
) -> list[float]:
    return [float(value) for record in records if (value := getter(record)) is not None]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None

    return round(sum(values) / len(values), 2)


def _median(values: list[float]) -> float | None:
    return _percentile(values, 0.5)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None

    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = position - lower_index
    result = (
        sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
    )

    return round(result, 2)


def _share(values: Iterable[bool]) -> float:
    bool_values = list(values)

    if not bool_values:
        return 0.0

    return round(sum(1 for value in bool_values if value) / len(bool_values), 4)


def _quality_metric(
    metric: str,
    value: float,
    records_count: int,
    *,
    processed_at: str,
) -> GoldDataQuality:
    return GoldDataQuality(
        metric=metric,
        value=value,
        records_count=records_count,
        processed_at=processed_at,
    )


def _build_id(*parts: str | None) -> str:
    return "|".join(part or "unknown" for part in parts)


def _write_model_csv(
    output_path: Path,
    records: list[T],
    model_type: type[Any],
) -> None:
    fieldnames = list(model_type.model_fields)
    logger.info("Writing gold CSV with %s records to %s", len(records), output_path)

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
            extrasaction="raise",
        )
        writer.writeheader()

        for record in records:
            writer.writerow(_serialize_csv_row(record))


def _serialize_csv_row(record: Any) -> dict[str, str | int | float]:
    row = record.model_dump(mode="json")

    return {key: _serialize_csv_value(value) for key, value in row.items()}


def _serialize_csv_value(value: Any) -> str | int | float:
    if value is None:
        return ""

    if isinstance(value, bool):
        return str(value).lower()

    if isinstance(value, (int, float)):
        return value

    return str(value)


if __name__ == "__main__":
    run_silver_to_gold()
