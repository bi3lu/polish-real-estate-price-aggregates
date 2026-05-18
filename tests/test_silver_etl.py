from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src.etl.silver import (
    find_latest_bronze_snapshot,
    load_bronze_directory_snapshot,
    load_bronze_snapshot,
    normalize_estate,
    run_bronze_to_silver,
    transform_bronze_payload,
)
from src.models.estate import Estate


def test_normalize_estate_returns_flat_silver_record() -> None:
    silver_estate = normalize_estate(
        Estate(
            source="Otodom",
            external_id=" 123 ",
            url=" https://example.invalid/offer ",
            title="  Duże   mieszkanie  ",
            estate_type="Mieszkanie",
            voivodeship="Mazowieckie",
            city=" Warszawa ",
            district=" Mokotów ",
            street=" Puławska ",
            price=750000,
            price_per_sqm=15000,
            area_sqm=50,
            rooms=3,
            floor=2,
            market="SECONDARY",
            building_type="BLOCK",
            seller_name=" Biuro Testowe ",
            seller_type="AGENCY",
            latitude=52.1,
            longitude=21.2,
            images=[
                " https://example.invalid/one.jpg ",
                "https://example.invalid/one.jpg",
                "https://example.invalid/two.jpg",
            ],
            attributes={
                "Building_material": ["building_material::brick"],
                "Building_ownership": ["full_ownership"],
                "Build_year": "2002",
                "Construction_status": ["ready_to_use"],
                "Heating": ["urban"],
                "Windows_type": ["plastic"],
                "Energy_certificate": ["a"],
                "Rent": 850,
                "Terrain_area": 120,
                "Building_floors_num": "4",
                "seller_id": "112",
                "advertiser_type": ["advertiser_type::agency"],
                "user_type": "agency",
                "Extras_types": [
                    "balcony",
                    "garage",
                    "basement",
                    "separate_kitchen",
                    "air_conditioning",
                ],
                "Security_types": ["entryphone", "monitoring"],
                "Media_types": ["internet", "phone"],
                "Equipment_types": ["fridge", "washing_machine"],
                "Informacje dodatkowe": ["balkon", "piwnica"],
            },
        ),
        bronze_scraped_at="2026-05-15T12:00:00+00:00",
        processed_at=datetime(2026, 5, 15, 13, 0, tzinfo=timezone.utc),
    )

    assert silver_estate is not None
    assert silver_estate.record_id == "otodom:123"
    assert silver_estate.source == "otodom"
    assert silver_estate.title == "Duże mieszkanie"
    assert silver_estate.estate_type == "mieszkanie"
    assert silver_estate.voivodeship == "mazowieckie"
    assert silver_estate.location == "Puławska, Mokotów, Warszawa"
    assert silver_estate.price_pln == 750000
    assert silver_estate.price_per_sqm_pln == 15000
    assert silver_estate.rent_pln == 850
    assert silver_estate.area_sqm == 50
    assert silver_estate.terrain_area_sqm == 120
    assert silver_estate.rooms == 3
    assert silver_estate.floor == 2
    assert silver_estate.building_floors_num == 4
    assert silver_estate.market == "secondary"
    assert silver_estate.building_type == "block"
    assert silver_estate.building_material == "brick"
    assert silver_estate.build_year == 2002
    assert silver_estate.construction_status == "ready_to_use"
    assert silver_estate.heating == "urban"
    assert silver_estate.seller_id == "112"
    assert silver_estate.advertiser_type == "agency"
    assert silver_estate.has_balcony is True
    assert silver_estate.has_garage is True
    assert silver_estate.has_basement is True
    assert silver_estate.has_separate_kitchen is True
    assert silver_estate.has_air_conditioning is True
    assert silver_estate.security_types == "entryphone|monitoring"
    assert silver_estate.media_types == "internet|phone"
    assert silver_estate.equipment_types == "fridge|washing_machine"
    assert silver_estate.extras_types == (
        "balcony|garage|basement|separate_kitchen|air_conditioning"
    )
    assert silver_estate.additional_features == "balkon|piwnica"
    assert silver_estate.image_count == 2
    assert silver_estate.first_image_url == "https://example.invalid/one.jpg"
    assert silver_estate.has_price is True
    assert silver_estate.has_location is True
    assert silver_estate.has_coordinates is True
    assert silver_estate.bronze_scraped_at == "2026-05-15T12:00:00+00:00"
    assert silver_estate.processed_at == "2026-05-15T13:00:00+00:00"


def test_transform_bronze_payload_skips_invalid_items_and_deduplicates() -> None:
    records = transform_bronze_payload(
        {
            "scraped_at": "2026-05-15T12:00:00+00:00",
            "data": [
                {
                    "source": "estate_service",
                    "external_id": "same-id",
                    "title": "Older title",
                },
                {
                    "source": "estate_service",
                    "external_id": "same-id",
                    "title": "Newer title",
                    "price": 100,
                },
                "not-an-object",
            ],
        },
        processed_at=datetime(2026, 5, 15, 13, 0, tzinfo=timezone.utc),
    )

    assert len(records) == 1
    assert records[0].record_id == "estate_service:same-id"
    assert records[0].title == "Newer title"
    assert records[0].price_pln == 100
    assert records[0].bronze_scraped_at == "2026-05-15T12:00:00+00:00"


def test_find_latest_bronze_snapshot_returns_latest_snapshot(tmp_path: Path) -> None:
    older = tmp_path / "estate_snapshot_20260515T120000000000Z.json"
    newer = tmp_path / "estate_snapshot_20260515T130000000000Z.jsonl"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    assert find_latest_bronze_snapshot(tmp_path) == newer


def test_load_bronze_snapshot_supports_streaming_jsonl(tmp_path: Path) -> None:
    bronze_path = tmp_path / "estate_snapshot_20260515T120000000000Z.jsonl"
    bronze_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "metadata",
                        "scraped_at": "2026-05-15T12:00:00+00:00",
                        "estate_types": ["mieszkanie"],
                        "voivodeships": ["mazowieckie"],
                        "max_page": 2,
                    }
                ),
                json.dumps(
                    {
                        "record_type": "estate",
                        "data": {
                            "source": "estate_service",
                            "external_id": "listing-1",
                            "title": "Oferta",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    payload = load_bronze_snapshot(bronze_path)

    assert payload["scraped_at"] == "2026-05-15T12:00:00+00:00"
    assert payload["count"] == 1
    assert payload["data"][0]["external_id"] == "listing-1"


def test_load_bronze_snapshot_supports_voivodeship_manifest(tmp_path: Path) -> None:
    bronze_path = (
        tmp_path / "mazowieckie" / "estate_snapshot_20260515T120000000000Z.jsonl"
    )
    bronze_path.parent.mkdir()
    bronze_path.write_text(
        "\n".join(
            [
                json.dumps({"record_type": "metadata"}),
                json.dumps(
                    {
                        "record_type": "estate",
                        "data": {
                            "source": "estate_service",
                            "external_id": "listing-1",
                            "voivodeship": "mazowieckie",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "estate_snapshot_manifest_20260515T120000000000Z.json"
    manifest_path.write_text(
        json.dumps(
            {
                "scraped_at": "2026-05-15T12:00:00+00:00",
                "files": {
                    "mazowieckie": {
                        "path": str(bronze_path),
                        "count": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = load_bronze_snapshot(manifest_path)

    assert payload["count"] == 1
    assert payload["data"][0]["external_id"] == "listing-1"


def test_load_bronze_directory_snapshot_reads_all_voivodeship_files(
    tmp_path: Path,
) -> None:
    for voivodeship, external_id in (
        ("malopolskie", "listing-malopolskie"),
        ("opolskie", "listing-opolskie"),
    ):
        bronze_path = tmp_path / voivodeship / f"estate_snapshot_{voivodeship}.jsonl"
        bronze_path.parent.mkdir()
        bronze_path.write_text(
            json.dumps(
                {
                    "record_type": "estate",
                    "data": {
                        "source": "estate_service",
                        "external_id": external_id,
                        "voivodeship": voivodeship,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    manifest_path = tmp_path / "estate_snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": {
                    "malopolskie": {
                        "path": str(
                            tmp_path
                            / "malopolskie"
                            / "estate_snapshot_malopolskie.jsonl"
                        )
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    payload = load_bronze_directory_snapshot(tmp_path)

    assert payload["count"] == 2
    assert sorted(item["external_id"] for item in payload["data"]) == [
        "listing-malopolskie",
        "listing-opolskie",
    ]
    assert payload["voivodeships"] == ["malopolskie", "opolskie"]


def test_run_bronze_to_silver_writes_normalized_csv(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    bronze_dir.mkdir()
    bronze_path = bronze_dir / "estate_snapshot_20260515T120000000000Z.json"
    bronze_path.write_text(
        json.dumps(
            {
                "scraped_at": "2026-05-15T12:00:00+00:00",
                "estate_types": ["mieszkanie"],
                "voivodeships": ["mazowieckie"],
                "count": 1,
                "data": [
                    {
                        "source": "estate_service",
                        "external_id": "listing-1",
                        "title": "Oferta",
                        "price": 500000,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    output_path = run_bronze_to_silver(
        bronze_dir=bronze_dir,
        silver_dir=silver_dir,
        processed_at=datetime(2026, 5, 15, 13, 0, tzinfo=timezone.utc),
    )

    assert output_path == silver_dir / "estate_silver_20260515T130000000000Z.csv"

    with output_path.open(encoding="utf-8", newline="") as output_file:
        rows = list(csv.DictReader(output_file))

    assert len(rows) == 1
    assert rows[0]["record_id"] == "estate_service:listing-1"
    assert rows[0]["price_pln"] == "500000.0"
    assert rows[0]["has_price"] == "true"
    assert rows[0]["processed_at"] == "2026-05-15T13:00:00+00:00"
    assert rows[0]["bronze_scraped_at"] == "2026-05-15T12:00:00+00:00"
