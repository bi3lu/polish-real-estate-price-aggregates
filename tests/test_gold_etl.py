"""Tests for silver-to-gold ETL transformations and outputs."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.etl.gold import (
    build_listing_feature,
    find_latest_silver_snapshot,
    load_silver_snapshot,
    run_silver_to_gold,
    transform_silver_records,
)
from src.models.silver_estate import SilverEstate


def test_build_listing_feature_derives_ml_ready_fields() -> None:
    feature = build_listing_feature(
        SilverEstate(
            record_id="otodom:1",
            source="otodom",
            external_id="1",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            latitude=52.1,
            longitude=21.1,
            price_pln=600000,
            area_sqm=50,
            rooms=3,
            floor=2,
            building_floors_num=4,
            build_year=2010,
            seller_type="agency",
            has_balcony=True,
            has_garage=True,
            has_coordinates=True,
            has_price=True,
            has_location=True,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
        processed_at="2026-05-17T13:00:00+00:00",
    )

    assert feature.price_per_sqm_pln == 12000
    assert feature.record_id.startswith("gold_")
    assert feature.record_id != "otodom:1"
    assert feature.price_per_sqm_source == "derived"
    assert feature.area_bucket == "50_70"
    assert feature.price_bucket == "500k_750k"
    assert feature.rooms_bucket == "3"
    assert feature.floor_ratio == 0.5
    assert feature.amenity_count == 2
    assert feature.geo_precision == "coordinates"
    assert feature.ml_target_price_pln == 600000
    assert feature.ml_target_price_per_sqm_pln == 12000


def test_transform_silver_records_builds_gold_tables() -> None:
    records = [
        SilverEstate(
            record_id="otodom:1",
            source="otodom",
            external_id="1",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            price_pln=600000,
            price_per_sqm_pln=12000,
            area_sqm=50,
            rooms=3,
            market="secondary",
            building_type="block",
            seller_type="agency",
            has_balcony=True,
            has_coordinates=True,
            latitude=52.1,
            longitude=21.1,
            has_price=True,
            has_location=True,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
        SilverEstate(
            record_id="otodom:2",
            source="otodom",
            external_id="2",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            price_pln=800000,
            price_per_sqm_pln=16000,
            area_sqm=50,
            rooms=3,
            market="secondary",
            building_type="block",
            seller_type="private",
            has_coordinates=False,
            has_price=True,
            has_location=True,
            processed_at="2026-05-17T12:00:00+00:00",
        ),
    ]

    tables = transform_silver_records(
        records,
        processed_at=datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc),
    )

    assert len(tables.ml_features) == 2
    assert len(tables.geo_aggregates) == 1
    assert tables.geo_aggregates[0].records_count == 2
    assert tables.geo_aggregates[0].median_price_pln == 700000
    assert tables.geo_aggregates[0].share_with_coordinates == 0.5
    assert len(tables.segment_aggregates) == 1
    assert tables.segment_aggregates[0].avg_price_per_sqm_pln == 14000
    quality = {record.metric: record.value for record in tables.data_quality}
    assert quality["records_count"] == 2
    assert quality["share_with_price"] == 1
    assert quality["share_with_coordinates"] == 0.5


def test_find_latest_silver_snapshot_returns_latest_snapshot(tmp_path: Path) -> None:
    older = tmp_path / "estate_silver_20260515T120000000000Z.csv"
    newer = tmp_path / "estate_silver_20260515T130000000000Z.csv"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")

    assert find_latest_silver_snapshot(tmp_path) == newer


def test_load_silver_snapshot_parses_csv_types(tmp_path: Path) -> None:
    silver_path = tmp_path / "estate_silver_20260515T120000000000Z.csv"

    with silver_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(SilverEstate.model_fields),
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "otodom:1",
                "source": "otodom",
                "external_id": "1",
                "price_pln": "500000.0",
                "area_sqm": "50.0",
                "rooms": "2",
                "has_price": "true",
                "has_location": "false",
                "has_coordinates": "true",
                "image_count": "3",
                "processed_at": "2026-05-17T12:00:00+00:00",
            }
        )

    records = load_silver_snapshot(silver_path)

    assert len(records) == 1
    assert records[0].price_pln == 500000
    assert records[0].rooms == 2
    assert records[0].has_coordinates is True
    assert records[0].image_count == 3


def test_run_silver_to_gold_writes_all_gold_tables(tmp_path: Path) -> None:
    silver_dir = tmp_path / "silver"
    gold_dir = tmp_path / "gold"
    silver_dir.mkdir()
    silver_path = silver_dir / "estate_silver_20260515T120000000000Z.csv"

    with silver_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(SilverEstate.model_fields),
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "otodom:1",
                "source": "otodom",
                "external_id": "1",
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "price_pln": "500000.0",
                "area_sqm": "50.0",
                "rooms": "2",
                "has_price": "true",
                "has_location": "true",
                "has_coordinates": "false",
                "image_count": "1",
                "processed_at": "2026-05-17T12:00:00+00:00",
            }
        )

    output_paths = run_silver_to_gold(
        silver_dir=silver_dir,
        gold_dir=gold_dir,
        processed_at=datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc),
    )

    assert output_paths.ml_features.exists()
    assert output_paths.geo_aggregates.exists()
    assert output_paths.segment_aggregates.exists()
    assert output_paths.data_quality.exists()
    assert output_paths.ml_features.name == (
        "estate_gold_ml_features_20260517T130000000000Z.csv"
    )

    with output_paths.ml_features.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    assert rows[0]["record_id"].startswith("gold_")
    assert rows[0]["record_id"] != "otodom:1"
    assert "source" not in rows[0]
    assert "external_id" not in rows[0]
    assert "url" not in rows[0]
    assert "title" not in rows[0]
    assert rows[0]["price_per_sqm_pln"] == "10000.0"
    assert rows[0]["geo_precision"] == "city"
