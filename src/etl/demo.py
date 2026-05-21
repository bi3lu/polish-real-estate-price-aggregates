"""Offline demo pipeline built from local fixture records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from src.config.globals import DEMO_BASE_DIR, DEMO_MIN_GROUP_SIZE, DEMO_PROCESSED_AT
from src.etl.gold import GoldOutputPaths, run_silver_to_gold
from src.etl.public import PublicOutputPaths, run_gold_to_public
from src.etl.silver import run_bronze_to_silver
from src.models.estate import Estate
from src.utils.storage import save_estates_to_bronze


@dataclass(frozen=True)
class DemoOutputPaths:
    """Filesystem paths written by the offline demo pipeline."""

    bronze: Path
    silver: Path
    gold: GoldOutputPaths
    public: PublicOutputPaths


def run_demo_pipeline(
    *,
    base_dir: Path = DEMO_BASE_DIR,
    processed_at: datetime = DEMO_PROCESSED_AT,
) -> DemoOutputPaths:
    """Run the complete ETL pipeline using local fixture listings only."""
    bronze_dir = base_dir / "bronze"
    silver_dir = base_dir / "silver"
    gold_dir = base_dir / "gold"
    public_dir = base_dir / "public"
    estates = build_demo_estates()

    bronze_path = save_estates_to_bronze(
        estates,
        estate_types=("dom", "kawalerka", "mieszkanie"),
        voivodeships=("dolnoslaskie", "malopolskie", "mazowieckie"),
        max_page=1,
        output_dir=bronze_dir,
        scraped_at=processed_at,
    )
    silver_path = run_bronze_to_silver(
        bronze_path=bronze_path,
        silver_dir=silver_dir,
        processed_at=processed_at,
    )
    gold_paths = run_silver_to_gold(
        silver_path=silver_path,
        gold_dir=gold_dir,
        processed_at=processed_at,
    )
    public_paths = run_gold_to_public(
        gold_ml_features_path=gold_paths.ml_features,
        public_dir=public_dir,
        min_group_size=DEMO_MIN_GROUP_SIZE,
        processed_at=processed_at,
    )

    return DemoOutputPaths(
        bronze=bronze_path,
        silver=silver_path,
        gold=gold_paths,
        public=public_paths,
    )


def build_demo_estates() -> list[Estate]:
    """Return a small, deterministic fixture dataset for offline demos."""
    return [
        _estate(
            external_id="demo-waw-m-001",
            title="Demo mieszkanie z balkonem",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            street="Demo Street",
            price=720000,
            price_per_sqm=14400,
            area_sqm=50,
            rooms=3,
            floor=2,
            building_floors_num=6,
            build_year=2012,
            latitude=52.19,
            longitude=21.01,
            extras=("balcony", "basement"),
        ),
        _estate(
            external_id="demo-waw-m-002",
            title="Demo mieszkanie blisko metra",
            estate_type="mieszkanie",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Mokotow",
            street="Fixture Avenue",
            price=810000,
            price_per_sqm=15000,
            area_sqm=54,
            rooms=3,
            floor=4,
            building_floors_num=8,
            build_year=2018,
            latitude=52.2,
            longitude=21.02,
            extras=("balcony", "garage"),
        ),
        _estate(
            external_id="demo-waw-k-001",
            title="Demo kawalerka kompaktowa",
            estate_type="kawalerka",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Wola",
            street="Sample Road",
            price=480000,
            price_per_sqm=17100,
            area_sqm=28,
            rooms=1,
            floor=5,
            building_floors_num=10,
            build_year=2020,
            latitude=52.23,
            longitude=20.98,
            extras=("air_conditioning",),
        ),
        _estate(
            external_id="demo-waw-k-002",
            title="Demo kawalerka inwestycyjna",
            estate_type="kawalerka",
            voivodeship="mazowieckie",
            city="Warszawa",
            district="Wola",
            street="Example Lane",
            price=510000,
            price_per_sqm=17000,
            area_sqm=30,
            rooms=1,
            floor=3,
            building_floors_num=7,
            build_year=2016,
            latitude=52.24,
            longitude=20.99,
            extras=("balcony",),
        ),
        _estate(
            external_id="demo-krk-m-001",
            title="Demo mieszkanie w Krakowie",
            estate_type="mieszkanie",
            voivodeship="malopolskie",
            city="Kraków",
            district="Debniki",
            street="Demo Krakow",
            price=690000,
            price_per_sqm=13800,
            area_sqm=50,
            rooms=2,
            floor=1,
            building_floors_num=4,
            build_year=2008,
            latitude=50.02,
            longitude=19.9,
            extras=("balcony", "separate_kitchen"),
        ),
        _estate(
            external_id="demo-krk-m-002",
            title="Demo mieszkanie rodzinne",
            estate_type="mieszkanie",
            voivodeship="malopolskie",
            city="Kraków",
            district="Debniki",
            street="Fixture Krakow",
            price=930000,
            price_per_sqm=13200,
            area_sqm=70.5,
            rooms=4,
            floor=2,
            building_floors_num=5,
            build_year=2010,
            latitude=50.03,
            longitude=19.91,
            extras=("balcony", "garage", "basement"),
        ),
        _estate(
            external_id="demo-wro-dom-001",
            title="Demo dom pod Wroclawiem",
            estate_type="dom",
            voivodeship="dolnoslaskie",
            city="Wrocław",
            district=None,
            street=None,
            price=1450000,
            price_per_sqm=9062,
            area_sqm=160,
            rooms=5,
            floor=None,
            building_floors_num=2,
            build_year=2005,
            latitude=51.08,
            longitude=17.02,
            extras=("garage", "garden"),
            terrain_area_sqm=550,
        ),
        _estate(
            external_id="demo-wro-dom-002",
            title="Demo dom z ogrodem",
            estate_type="dom",
            voivodeship="dolnoslaskie",
            city="Wrocław",
            district=None,
            street=None,
            price=1680000,
            price_per_sqm=9333,
            area_sqm=180,
            rooms=5,
            floor=None,
            building_floors_num=2,
            build_year=2015,
            latitude=51.09,
            longitude=17.03,
            extras=("garage", "garden", "air_conditioning"),
            terrain_area_sqm=720,
        ),
    ]


def _estate(
    *,
    external_id: str,
    title: str,
    estate_type: str,
    voivodeship: str,
    city: str,
    district: str | None,
    street: str | None,
    price: float,
    price_per_sqm: float,
    area_sqm: float,
    rooms: int,
    floor: int | None,
    building_floors_num: int,
    build_year: int,
    latitude: float,
    longitude: float,
    extras: tuple[str, ...],
    terrain_area_sqm: float | None = None,
) -> Estate:
    attributes: dict[str, Any] = {
        "Build_year": str(build_year),
        "Building_floors_num": str(building_floors_num),
        "Construction_status": ["ready_to_use"],
        "Extras_types": list(extras),
        "MarketType": "secondary",
        "Media_types": ["internet", "electricity"],
        "Rent": 650 if estate_type != "dom" else 0,
        "Rooms_num": [str(rooms)],
        "user_type": "agency",
    }

    if terrain_area_sqm is not None:
        attributes["Terrain_area"] = str(terrain_area_sqm)

    return Estate(
        source="demo_fixture",
        external_id=external_id,
        url=f"https://example.invalid/demo/{external_id}",
        title=title,
        estate_type=estate_type,
        voivodeship=voivodeship,
        price=price,
        price_per_sqm=price_per_sqm,
        area_sqm=area_sqm,
        rooms=rooms,
        location=", ".join(part for part in (street, district, city) if part),
        city=city,
        district=district,
        street=street,
        market="SECONDARY",
        floor=floor,
        building_type="detached" if estate_type == "dom" else "block",
        seller_name="Demo Agency",
        seller_type="agency",
        latitude=latitude,
        longitude=longitude,
        images=[
            f"https://example.invalid/demo/{external_id}/image-1.jpg",
            f"https://example.invalid/demo/{external_id}/image-2.jpg",
        ],
        attributes=attributes,
    )


def _paths_payload(paths: DemoOutputPaths) -> dict[str, Any]:
    return {
        "bronze": str(paths.bronze),
        "silver": str(paths.silver),
        "gold": {
            "ml_features": str(paths.gold.ml_features),
            "geo_aggregates": str(paths.gold.geo_aggregates),
            "segment_aggregates": str(paths.gold.segment_aggregates),
            "data_quality": str(paths.gold.data_quality),
        },
        "public": {
            "ml_features": str(paths.public.ml_features),
            "data_quality": str(paths.public.data_quality),
        },
    }


def main(stdout: TextIO | None = None) -> int:
    """CLI entry point for ``python -m src.etl.demo``."""
    output = stdout

    if output is None:
        import sys

        output = sys.stdout

    paths = run_demo_pipeline()
    json.dump(
        {
            "base_dir": str(DEMO_BASE_DIR),
            "records": len(build_demo_estates()),
            "outputs": _paths_payload(paths),
        },
        output,
        ensure_ascii=False,
        indent=2,
    )
    output.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
