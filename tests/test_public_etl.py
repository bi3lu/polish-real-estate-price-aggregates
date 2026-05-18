from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.etl.public import (
    build_public_listing_feature,
    find_latest_gold_ml_features,
    load_gold_ml_features,
    run_gold_to_public,
    transform_gold_records_for_public,
)
from src.models.gold_estate import GoldListingFeature


def test_build_public_listing_feature_generalizes_sensitive_fields() -> None:
    feature = build_public_listing_feature(
        GoldListingFeature(
            record_id="gold_private_id",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            latitude=52.1234,
            longitude=21.9876,
            market="secondary",
            building_type="block",
            seller_type="agency",
            floor=2,
            building_floors_num=4,
            terrain_area_sqm=320,
            image_count=17,
            has_balcony=True,
            has_coordinates=True,
            price_per_sqm_source="source",
            area_bucket="50_70",
            price_bucket="500k_750k",
            rooms_bucket="3",
            building_age_years=16,
            amenity_count=1,
            geo_precision="coordinates",
            ml_target_price_pln=604321,
            ml_target_price_per_sqm_pln=12044,
            rent_pln=873,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
        city_count=10,
        grid_count=10,
        min_group_size=10,
        processed_at="2026-05-17T13:00:00+00:00",
    )

    assert feature.city == "Warszawa"
    assert feature.geo_lat_grid is None
    assert feature.geo_lon_grid is None
    assert feature.building_age_bucket == "11_25"
    assert feature.floor_bucket == "1_2"
    assert feature.building_floors_bucket == "2_4"
    assert feature.terrain_area_bucket == "250_500"
    assert feature.image_count_bucket == "16_30"
    assert feature.public_target_price_pln == 600000
    assert feature.public_target_price_per_sqm_pln == 12000
    assert feature.public_rent_pln == 850


def test_transform_gold_records_suppresses_small_location_groups() -> None:
    records = [
        GoldListingFeature(
            record_id="gold_1",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Small City",
            latitude=52.11,
            longitude=21.91,
            has_coordinates=True,
            area_bucket="35_50",
            price_bucket="300k_500k",
            rooms_bucket="2",
            amenity_count=0,
            geo_precision="coordinates",
            ml_target_price_pln=500000,
            ml_target_price_per_sqm_pln=10000,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
        GoldListingFeature(
            record_id="gold_2",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Small City",
            latitude=52.12,
            longitude=21.92,
            has_coordinates=True,
            area_bucket="35_50",
            price_bucket="300k_500k",
            rooms_bucket="2",
            amenity_count=0,
            geo_precision="coordinates",
            ml_target_price_pln=510000,
            ml_target_price_per_sqm_pln=10100,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
    ]

    tables = transform_gold_records_for_public(
        records,
        min_group_size=3,
        processed_at=datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc),
    )

    assert len(tables.ml_features) == 2
    assert tables.ml_features[0].city is None
    assert tables.ml_features[0].geo_lat_grid is None
    assert tables.ml_features[0].has_coordinates is False
    quality = {record.metric: record.value for record in tables.data_quality}
    assert quality["share_with_public_city"] == 0
    assert quality["share_with_public_geo_grid"] == 0


def test_find_latest_gold_ml_features_returns_latest_snapshot(tmp_path: Path) -> None:
    older = tmp_path / "estate_gold_ml_features_20260515T120000000000Z.csv"
    newer = tmp_path / "estate_gold_ml_features_20260515T130000000000Z.csv"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")

    assert find_latest_gold_ml_features(tmp_path) == newer


def test_load_gold_ml_features_parses_csv_types(tmp_path: Path) -> None:
    gold_path = tmp_path / "estate_gold_ml_features_20260515T120000000000Z.csv"

    with gold_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(GoldListingFeature.model_fields),
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "gold_1",
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "latitude": "52.12",
                "longitude": "21.91",
                "has_coordinates": "true",
                "has_balcony": "true",
                "image_count": "3",
                "amenity_count": "1",
                "geo_precision": "coordinates",
                "processed_at": "2026-05-17T12:00:00+00:00",
            }
        )

    records = load_gold_ml_features(gold_path)

    assert len(records) == 1
    assert records[0].latitude == 52.12
    assert records[0].has_coordinates is True
    assert records[0].has_balcony is True
    assert records[0].image_count == 3


def test_run_gold_to_public_writes_public_dataset_without_private_columns(
    tmp_path: Path,
) -> None:
    gold_dir = tmp_path / "gold"
    public_dir = tmp_path / "public"
    gold_dir.mkdir()
    gold_path = gold_dir / "estate_gold_ml_features_20260515T120000000000Z.csv"

    with gold_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(GoldListingFeature.model_fields),
        )
        writer.writeheader()

        for index in range(2):
            writer.writerow(
                {
                    "record_id": f"gold_{index}",
                    "estate_type": "mieszkanie",
                    "voivodeship": "mazowieckie",
                    "city": "Warszawa",
                    "district": "Mokotow",
                    "latitude": "52.12",
                    "longitude": "21.91",
                    "has_coordinates": "true",
                    "area_bucket": "35_50",
                    "price_bucket": "300k_500k",
                    "rooms_bucket": "2",
                    "amenity_count": "0",
                    "geo_precision": "coordinates",
                    "ml_target_price_pln": "501234.0",
                    "ml_target_price_per_sqm_pln": "10077.0",
                    "processed_at": "2026-05-17T12:00:00+00:00",
                }
            )

    output_paths = run_gold_to_public(
        gold_dir=gold_dir,
        public_dir=public_dir,
        min_group_size=2,
        processed_at=datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc),
    )

    assert output_paths.ml_features.exists()
    assert output_paths.data_quality.exists()
    assert output_paths.ml_features.name == (
        "estate_public_ml_features_20260517T130000000000Z.csv"
    )

    with output_paths.ml_features.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    assert len(rows) == 2
    assert "record_id" not in rows[0]
    assert "district" not in rows[0]
    assert "latitude" not in rows[0]
    assert "longitude" not in rows[0]
    assert rows[0]["city"] == "Warszawa"
    assert rows[0]["geo_lat_grid"] == ""
    assert rows[0]["geo_lon_grid"] == ""
    assert rows[0]["public_target_price_pln"] == "500000.0"
    assert rows[0]["public_target_price_per_sqm_pln"] == "10100.0"
