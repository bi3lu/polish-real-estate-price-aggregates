"""Tests for bronze snapshot storage and resume checkpoints."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from src.config.globals import BRONZE_STREAM_CHECKPOINT_INTERVAL
from src.ingestion.models import RawListingObservation
from src.utils.storage import (
    load_bronze_external_ids_by_voivodeship,
    load_bronze_page_checkpoints,
    save_estates_to_bronze,
    stream_estates_to_bronze,
)


def test_save_estates_to_bronze_writes_snapshot_json(tmp_path: Path) -> None:
    output_path = save_estates_to_bronze(
        [
            RawListingObservation(
                external_id="listing-1",
                title="Pierwsza oferta",
                estate_type="mieszkanie",
                voivodeship="mazowieckie",
            )
        ],
        estate_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_page=2,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
        adapter_types_by_source_id={"source_a": "embedded_json_listing_site"},
    )

    assert output_path == tmp_path / "manifest.json"

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    source_manifest_path = (
        tmp_path / "source_a" / "2026-05-15T12-30-45Z" / "manifest.json"
    )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))

    assert payload["updated_at"] == "2026-05-15T12:30:45+00:00"
    assert payload["run_manifests"]["source_a"]["path"] == str(source_manifest_path)
    assert source_manifest["source_id"] == "source_a"
    assert source_manifest["run_id"] == "2026-05-15T12-30-45Z"
    assert source_manifest["started_at"] == "2026-05-15T12:30:45Z"
    assert source_manifest["finished_at"] == "2026-05-15T12:30:45Z"
    assert payload["estate_types"] == ["mieszkanie"]
    assert payload["voivodeships"] == ["mazowieckie"]
    assert payload["max_page"] == 2
    assert payload["new_records_count"] == 1
    assert source_manifest["records_raw"] == 1
    assert source_manifest["records_canonical"] == 1


def test_stream_estates_to_bronze_writes_jsonl_incrementally(tmp_path: Path) -> None:
    output_path, count = stream_estates_to_bronze(
        iter(
            [
                RawListingObservation(
                    external_id="listing-1",
                    title="Pierwsza oferta",
                    estate_type="mieszkanie",
                    voivodeship="mazowieckie",
                ),
                RawListingObservation(
                    external_id="listing-2",
                    title="Druga oferta",
                    estate_type="dom",
                    voivodeship="pomorskie",
                ),
            ]
        ),
        estate_types=("mieszkanie", "dom"),
        voivodeships=("mazowieckie", "pomorskie"),
        max_page=2,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
        adapter_types_by_source_id={"source_a": "embedded_json_listing_site"},
    )

    assert count == 2
    assert output_path == tmp_path / "manifest.json"

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    source_path = Path(manifest["files"]["source_a"]["path"])
    source_manifest_path = (
        tmp_path / "source_a" / "2026-05-15T12-30-45Z" / "manifest.json"
    )
    assert source_path == (
        tmp_path / "source_a" / "2026-05-15T12-30-45Z" / "observations.jsonl"
    )
    assert manifest["run_manifests"]["source_a"]["path"] == str(source_manifest_path)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_lines = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
    ]

    assert source_manifest["pages_requested"] == 8
    assert source_manifest["pages_succeeded"] == 8
    assert source_manifest["adapter_type"] == "embedded_json_listing_site"
    assert all(line["record_type"] == "estate" for line in source_lines)
    assert [line["data"]["external_id"] for line in source_lines] == [
        "listing-1",
        "listing-2",
    ]


def test_stream_estates_to_bronze_skips_existing_external_ids(
    tmp_path: Path,
) -> None:
    existing_dir = tmp_path / "mazowieckie"
    existing_dir.mkdir()
    existing_path = existing_dir / "estate_snapshot_mazowieckie.jsonl"
    existing_path.write_text(
        "\n".join(
            [
                json.dumps({"record_type": "metadata"}),
                json.dumps(
                    {
                        "record_type": "estate",
                        "data": {
                            "external_id": "listing-1",
                            "voivodeship": "mazowieckie",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    output_path, count = stream_estates_to_bronze(
        iter(
            [
                RawListingObservation(
                    external_id="listing-1",
                    voivodeship="mazowieckie",
                ),
                RawListingObservation(
                    external_id="listing-2",
                    voivodeship="mazowieckie",
                ),
            ]
        ),
        estate_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_page=1,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    source_path = Path(manifest["files"]["source_a"]["path"])
    source_lines = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
    ]

    assert count == 1
    assert manifest["duplicates_skipped"] == 1
    assert manifest["files"]["source_a"]["new_records_count"] == 1
    assert all(line["record_type"] == "estate" for line in source_lines)
    assert [line["data"]["external_id"] for line in source_lines] == ["listing-2"]
    assert load_bronze_external_ids_by_voivodeship(tmp_path)["mazowieckie"] == {
        "source_a:listing-1",
        "source_a:listing-2",
    }


def test_stream_estates_to_bronze_persists_partial_records_on_error(
    tmp_path: Path,
) -> None:
    def estates() -> Iterable[RawListingObservation]:
        yield RawListingObservation(
            external_id="listing-1",
            voivodeship="malopolskie",
        )
        raise RuntimeError("HTTP Error 403: Forbidden")

    try:
        stream_estates_to_bronze(
            estates(),
            estate_types=("mieszkanie",),
            voivodeships=("malopolskie",),
            max_page=1,
            output_dir=tmp_path,
            scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
        )

    except RuntimeError:
        pass

    canonical_path = (
        tmp_path / "source_a" / "2026-05-15T12-30-45Z" / "observations.jsonl"
    )
    lines = [
        json.loads(line)
        for line in canonical_path.read_text(encoding="utf-8").splitlines()
    ]

    assert lines[0]["record_type"] == "estate"
    assert lines[0]["data"]["external_id"] == "listing-1"


def test_stream_estates_to_bronze_checkpoints_during_iteration(
    tmp_path: Path,
) -> None:
    canonical_path = (
        tmp_path / "source_a" / "2026-05-15T12-30-45Z" / "observations.jsonl"
    )
    checkpoint_seen = False

    def estates() -> Iterable[RawListingObservation]:
        nonlocal checkpoint_seen

        for index in range(BRONZE_STREAM_CHECKPOINT_INTERVAL):
            yield RawListingObservation(
                external_id=f"listing-{index}",
                voivodeship="malopolskie",
            )

        checkpoint_seen = canonical_path.exists()
        yield RawListingObservation(
            external_id="listing-after-checkpoint",
            voivodeship="malopolskie",
        )

    output_path, count = stream_estates_to_bronze(
        estates(),
        estate_types=("mieszkanie",),
        voivodeships=("malopolskie",),
        max_page=1,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
    )
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    lines = [
        json.loads(line)
        for line in canonical_path.read_text(encoding="utf-8").splitlines()
    ]

    assert checkpoint_seen is True
    assert count == BRONZE_STREAM_CHECKPOINT_INTERVAL + 1
    assert manifest["files"]["source_a"]["new_records_count"] == count
    assert all(line["record_type"] == "estate" for line in lines)
    assert len(lines) == count


def test_stream_estates_to_bronze_writes_page_checkpoints(
    tmp_path: Path,
) -> None:
    output_path, _ = stream_estates_to_bronze(
        iter(
            [
                RawListingObservation(
                    external_id="listing-1",
                    estate_type="mieszkanie",
                    voivodeship="malopolskie",
                )
            ]
        ),
        estate_types=("mieszkanie", "dom"),
        voivodeships=("malopolskie",),
        max_page=100,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
        page_checkpoints_by_voivodeship={
            "malopolskie": {
                "mieszkanie": 37,
                "dom": 12,
            }
        },
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))

    assert manifest["page_checkpoints"]["malopolskie"]["mieszkanie"] == {
        "last_completed_page": 37,
        "next_page": 38,
        "updated_at": "2026-05-15T12:30:45+00:00",
    }
    assert load_bronze_page_checkpoints(tmp_path) == {
        "malopolskie": {
            "dom": 12,
            "mieszkanie": 37,
        }
    }
