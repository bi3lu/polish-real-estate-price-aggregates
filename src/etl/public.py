from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.config.globals import DEFAULT_MIN_GROUP_SIZE, GOLD_DATA_DIR, PUBLIC_DATA_DIR, T
from src.models.gold_estate import GoldListingFeature
from src.models.public_estate import PublicDataQuality, PublicListingFeature
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PublicTables:
    ml_features: list[PublicListingFeature]
    data_quality: list[PublicDataQuality]


@dataclass(frozen=True)
class PublicOutputPaths:
    ml_features: Path
    data_quality: Path


def run_gold_to_public(
    *,
    gold_ml_features_path: Path | None = None,
    gold_dir: Path = GOLD_DATA_DIR,
    public_dir: Path = PUBLIC_DATA_DIR,
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
    processed_at: datetime | None = None,
) -> PublicOutputPaths:
    selected_gold_path = gold_ml_features_path or find_latest_gold_ml_features(gold_dir)
    snapshot_time = processed_at or datetime.now(timezone.utc)
    logger.info("Public ETL started for gold ML snapshot %s", selected_gold_path)
    gold_records = load_gold_ml_features(selected_gold_path)
    public_tables = transform_gold_records_for_public(
        gold_records,
        min_group_size=min_group_size,
        processed_at=snapshot_time,
    )
    output_paths = save_public_tables(
        public_tables,
        output_dir=public_dir,
        processed_at=snapshot_time,
    )
    logger.info(
        "Public ETL finished: ml_features=%s data_quality=%s",
        len(public_tables.ml_features),
        len(public_tables.data_quality),
    )

    return output_paths


def find_latest_gold_ml_features(gold_dir: Path = GOLD_DATA_DIR) -> Path:
    snapshots = sorted(gold_dir.glob("estate_gold_ml_features_*.csv"))

    if not snapshots:
        raise FileNotFoundError(f"No gold ML feature snapshots found in {gold_dir}")

    return snapshots[-1]


def load_gold_ml_features(gold_ml_features_path: Path) -> list[GoldListingFeature]:
    records: list[GoldListingFeature] = []

    with gold_ml_features_path.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)

        for line_number, row in enumerate(reader, start=2):
            try:
                records.append(GoldListingFeature.model_validate(_parse_gold_row(row)))

            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid gold ML row in %s:%s: %s",
                    gold_ml_features_path,
                    line_number,
                    exc,
                )

    return records


def transform_gold_records_for_public(
    records: list[GoldListingFeature],
    *,
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
    processed_at: datetime | None = None,
) -> PublicTables:
    if min_group_size < 1:
        raise ValueError("min_group_size must be greater than or equal to 1")

    snapshot_time = processed_at or datetime.now(timezone.utc)
    processed_at_text = snapshot_time.isoformat()
    city_counts = Counter(_city_key(record) for record in records)
    grid_counts = Counter(_grid_key(record) for record in records)
    public_records = [
        build_public_listing_feature(
            record,
            city_count=city_counts[_city_key(record)],
            grid_count=grid_counts[_grid_key(record)],
            min_group_size=min_group_size,
            processed_at=processed_at_text,
        )
        for record in records
    ]

    return PublicTables(
        ml_features=public_records,
        data_quality=build_public_data_quality(
            public_records,
            source_records_count=len(records),
            min_group_size=min_group_size,
            processed_at=processed_at_text,
        ),
    )


def build_public_listing_feature(
    record: GoldListingFeature,
    *,
    city_count: int,
    grid_count: int,
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
    processed_at: str,
) -> PublicListingFeature:
    lat_grid, lon_grid = _rounded_grid(record.latitude, record.longitude)
    keep_city = city_count >= min_group_size
    keep_grid = not keep_city and grid_count >= min_group_size

    return PublicListingFeature(
        estate_type=record.estate_type,
        voivodeship=record.voivodeship,
        city=record.city if keep_city else None,
        geo_lat_grid=lat_grid if keep_grid else None,
        geo_lon_grid=lon_grid if keep_grid else None,
        market=record.market,
        building_type=record.building_type,
        seller_type=record.seller_type,
        area_bucket=record.area_bucket,
        price_bucket=record.price_bucket,
        rooms_bucket=record.rooms_bucket,
        building_age_bucket=_bucket_number(
            record.building_age_years,
            (
                (2, "new_0_2"),
                (10, "3_10"),
                (25, "11_25"),
                (50, "26_50"),
            ),
            "gt_50",
        ),
        floor_bucket=_bucket_number(
            record.floor,
            (
                (1, "ground"),
                (3, "1_2"),
                (6, "3_5"),
                (11, "6_10"),
            ),
            "gt_10",
        ),
        building_floors_bucket=_bucket_number(
            record.building_floors_num,
            (
                (2, "1"),
                (5, "2_4"),
                (11, "5_10"),
            ),
            "gt_10",
        ),
        terrain_area_bucket=_bucket_number(
            record.terrain_area_sqm,
            (
                (250, "lt_250"),
                (500, "250_500"),
                (1000, "500_1000"),
                (2000, "1000_2000"),
            ),
            "gte_2000",
        ),
        image_count_bucket=_bucket_number(
            record.image_count,
            (
                (1, "0"),
                (6, "1_5"),
                (16, "6_15"),
                (31, "16_30"),
            ),
            "gt_30",
        ),
        has_lift=record.has_lift,
        has_balcony=record.has_balcony,
        has_garage=record.has_garage,
        has_basement=record.has_basement,
        has_separate_kitchen=record.has_separate_kitchen,
        has_air_conditioning=record.has_air_conditioning,
        has_garden=record.has_garden,
        amenity_count=record.amenity_count,
        has_coordinates=keep_grid and record.has_coordinates,
        is_price_outlier=record.is_price_outlier,
        price_per_sqm_source=record.price_per_sqm_source,
        public_target_price_pln=_round_to_step(record.ml_target_price_pln, 10_000),
        public_target_price_per_sqm_pln=_round_to_step(
            record.ml_target_price_per_sqm_pln,
            100,
        ),
        public_rent_pln=_round_to_step(record.rent_pln, 50),
        processed_at=processed_at,
    )


def build_public_data_quality(
    records: list[PublicListingFeature],
    *,
    source_records_count: int,
    min_group_size: int,
    processed_at: str,
) -> list[PublicDataQuality]:
    public_count = len(records)

    return [
        _quality_metric(
            "source_records_count",
            float(source_records_count),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "public_records_count",
            float(public_count),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "min_group_size",
            float(min_group_size),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_public_city",
            _share(record.city is not None for record in records),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_public_geo_grid",
            _share(
                record.geo_lat_grid is not None and record.geo_lon_grid is not None
                for record in records
            ),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "share_with_public_price_target",
            _share(record.public_target_price_pln is not None for record in records),
            public_count,
            processed_at=processed_at,
        ),
        _quality_metric(
            "distinct_public_cities_count",
            float(len({record.city for record in records if record.city})),
            public_count,
            processed_at=processed_at,
        ),
    ]


def save_public_tables(
    tables: PublicTables,
    *,
    output_dir: Path = PUBLIC_DATA_DIR,
    processed_at: datetime | None = None,
) -> PublicOutputPaths:
    snapshot_time = processed_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot_time.strftime("%Y%m%dT%H%M%S%fZ")
    output_paths = PublicOutputPaths(
        ml_features=output_dir / f"estate_public_ml_features_{timestamp}.csv",
        data_quality=output_dir / f"estate_public_data_quality_{timestamp}.csv",
    )
    _write_model_csv(
        output_paths.ml_features,
        tables.ml_features,
        PublicListingFeature,
    )
    _write_model_csv(
        output_paths.data_quality,
        tables.data_quality,
        PublicDataQuality,
    )

    return output_paths


def _parse_gold_row(row: dict[str, str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    bool_fields = {
        "has_lift",
        "has_balcony",
        "has_garage",
        "has_basement",
        "has_separate_kitchen",
        "has_air_conditioning",
        "has_garden",
        "has_coordinates",
        "is_price_outlier",
    }
    int_fields = {
        "rooms",
        "floor",
        "building_floors_num",
        "build_year",
        "image_count",
        "building_age_years",
        "amenity_count",
    }
    float_fields = {
        "latitude",
        "longitude",
        "price_pln",
        "price_per_sqm_pln",
        "rent_pln",
        "area_sqm",
        "terrain_area_sqm",
        "total_monthly_cost_pln",
        "floor_ratio",
        "ml_target_price_pln",
        "ml_target_price_per_sqm_pln",
    }

    for key, value in row.items():
        if key in bool_fields:
            parsed[key] = value.lower() == "true" if value else False

        elif value == "":
            parsed[key] = 0 if key in {"image_count", "amenity_count"} else None

        elif key in int_fields:
            parsed[key] = int(value)

        elif key in float_fields:
            parsed[key] = float(value)

        else:
            parsed[key] = value

    return parsed


def _city_key(
    record: GoldListingFeature,
) -> tuple[str | None, str | None, str | None]:
    return record.voivodeship, record.city, record.estate_type


def _grid_key(
    record: GoldListingFeature,
) -> tuple[str | None, str | None, float | None, float | None]:
    lat_grid, lon_grid = _rounded_grid(record.latitude, record.longitude)

    return record.voivodeship, record.estate_type, lat_grid, lon_grid


def _rounded_grid(
    latitude: float | None,
    longitude: float | None,
) -> tuple[float | None, float | None]:
    if latitude is None or longitude is None:
        return None, None

    return round(latitude, 1), round(longitude, 1)


def _bucket_number(
    value: float | int | None,
    thresholds: tuple[tuple[float, str], ...],
    fallback: str,
) -> str | None:
    if value is None:
        return None

    for upper_bound, label in thresholds:
        if value < upper_bound:
            return label

    return fallback


def _round_to_step(value: float | None, step: int) -> float | None:
    if value is None:
        return None

    return float(round(value / step) * step)


def _share(values: Any) -> float:
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
) -> PublicDataQuality:
    return PublicDataQuality(
        metric=metric,
        value=value,
        records_count=records_count,
        processed_at=processed_at,
    )


def _write_model_csv(
    output_path: Path,
    records: list[T],
    model_type: type[Any],
) -> None:
    fieldnames = list(model_type.model_fields)
    logger.info("Writing public CSV with %s records to %s", len(records), output_path)

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
    run_gold_to_public()
