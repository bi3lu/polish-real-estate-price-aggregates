"""Tests for the public market ranking CLI."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from src.analytics.market_ranking import (
    MarketRankingOptions,
    build_market_ranking,
    find_latest_public_ml_features,
    load_public_market_records,
    run_cli,
)


def test_find_latest_public_ml_features_returns_latest_snapshot(tmp_path: Path) -> None:
    older = tmp_path / "estate_public_ml_features_20260515T120000000000Z.csv"
    newer = tmp_path / "estate_public_ml_features_20260515T130000000000Z.csv"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")

    assert find_latest_public_ml_features(tmp_path) == newer


def test_build_market_ranking_groups_and_sorts_public_records(tmp_path: Path) -> None:
    public_path = _write_public_features(
        tmp_path,
        [
            {
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "public_target_price_pln": "500000",
                "public_target_price_per_sqm_pln": "10000",
            },
            {
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "public_target_price_pln": "700000",
                "public_target_price_per_sqm_pln": "14000",
            },
            {
                "estate_type": "dom",
                "voivodeship": "opolskie",
                "city": "",
                "public_target_price_pln": "400000",
                "public_target_price_per_sqm_pln": "5000",
            },
        ],
    )
    records = load_public_market_records(public_path)

    ranking = build_market_ranking(
        records,
        options=MarketRankingOptions(
            input_path=public_path,
            group_by="voivodeship",
            voivodeships=(),
            estate_types=(),
            min_records=1,
            limit=10,
            sort_by="median_price_per_sqm_pln",
            ascending=False,
            output_format="table",
            include_suppressed_location=False,
        ),
    )

    assert [row.group for row in ranking] == ["mazowieckie", "opolskie"]
    assert ranking[0].records_count == 2
    assert ranking[0].median_price_per_sqm_pln == 12000
    assert ranking[0].median_price_pln == 600000
    assert ranking[0].share_with_price_per_sqm == 1


def test_city_ranking_skips_suppressed_locations_by_default(tmp_path: Path) -> None:
    public_path = _write_public_features(
        tmp_path,
        [
            {
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "public_target_price_pln": "500000",
                "public_target_price_per_sqm_pln": "10000",
            },
            {
                "estate_type": "dom",
                "voivodeship": "opolskie",
                "city": "",
                "public_target_price_pln": "400000",
                "public_target_price_per_sqm_pln": "5000",
            },
        ],
    )
    records = load_public_market_records(public_path)

    ranking = build_market_ranking(
        records,
        options=MarketRankingOptions(
            input_path=public_path,
            group_by="city",
            voivodeships=(),
            estate_types=(),
            min_records=1,
            limit=10,
            sort_by="median_price_per_sqm_pln",
            ascending=False,
            output_format="table",
            include_suppressed_location=False,
        ),
    )

    assert [row.group for row in ranking] == ["Warszawa"]


def test_run_cli_outputs_json_with_filters(tmp_path: Path) -> None:
    public_path = _write_public_features(
        tmp_path,
        [
            {
                "estate_type": "mieszkanie",
                "voivodeship": "mazowieckie",
                "city": "Warszawa",
                "public_target_price_pln": "500000",
                "public_target_price_per_sqm_pln": "10000",
            },
            {
                "estate_type": "dom",
                "voivodeship": "opolskie",
                "city": "Opole",
                "public_target_price_pln": "400000",
                "public_target_price_per_sqm_pln": "5000",
            },
        ],
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--input",
            str(public_path),
            "--group-by",
            "voivodeship_estate_type",
            "--estate-type",
            "mieszkanie",
            "--format",
            "json",
            "--min-records",
            "1",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())

    assert exit_code == 0
    assert len(payload) == 1
    assert payload[0]["group"] == "mazowieckie/mieszkanie"


def _write_public_features(
    tmp_path: Path,
    rows: list[dict[str, str]],
) -> Path:
    public_path = tmp_path / "estate_public_ml_features_20260515T120000000000Z.csv"

    with public_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "estate_type",
                "voivodeship",
                "city",
                "public_target_price_pln",
                "public_target_price_per_sqm_pln",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return public_path
