"""Storage helpers for writing and resuming bronze real estate snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.globals import BRONZE_DATA_DIR, BRONZE_STREAM_CHECKPOINT_INTERVAL
from src.models.estate import Estate
from src.utils.logger import get_logger

logger = get_logger(__name__)


def save_estates_to_bronze(
    estates: list[Estate],
    *,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
    output_dir: Path = BRONZE_DATA_DIR,
    scraped_at: datetime | None = None,
) -> Path:
    """Write estates to a single JSON bronze snapshot.

    Args:
        estates: Estate records to serialize.
        estate_types: Estate type filters represented in the snapshot.
        voivodeships: Voivodeship filters represented in the snapshot.
        max_page: Maximum page used during ingestion.
        output_dir: Directory where the snapshot is written.
        scraped_at: Optional ingestion timestamp used in metadata and filename.

    Returns:
        Path to the written JSON snapshot.
    """
    snapshot_time = scraped_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _build_snapshot_filename(snapshot_time)
    logger.info(
        "Writing bronze snapshot with %s records to %s", len(estates), output_path
    )

    payload: dict[str, Any] = {
        "scraped_at": snapshot_time.isoformat(),
        "estate_types": list(estate_types),
        "voivodeships": list(voivodeships),
        "max_page": max_page,
        "count": len(estates),
        "data": [estate.model_dump(mode="json") for estate in estates],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def stream_estates_to_bronze(
    estates: Iterable[Estate],
    *,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
    output_dir: Path = BRONZE_DATA_DIR,
    scraped_at: datetime | None = None,
    page_checkpoints_by_voivodeship: dict[str, dict[str, int]] | None = None,
) -> tuple[Path, int]:
    """Stream estates into canonical per-voivodeship JSONL bronze files.

    Args:
        estates: Estate records to persist.
        estate_types: Estate type filters represented in the manifest.
        voivodeships: Voivodeship filters represented in the manifest.
        max_page: Maximum page used during ingestion.
        output_dir: Directory where JSONL files and manifest are written.
        scraped_at: Optional ingestion timestamp used in manifest metadata.
        page_checkpoints_by_voivodeship: Completed ingestion pages to persist for
            resume support.

    Returns:
        Tuple containing the manifest path and number of newly written records.

    Raises:
        BaseException: Re-raises any exception encountered while consuming the
            estate iterable after flushing pending records.
    """
    snapshot_time = scraped_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _build_stream_manifest_filename()
    existing_manifest = _load_stream_manifest(output_path)
    paths_by_voivodeship: dict[str, Path] = {}
    pending_records_by_voivodeship: dict[str, list[dict[str, Any]]] = {}
    new_counts_by_voivodeship: dict[str, int] = {}
    normalized_paths: set[Path] = set()
    seen_external_ids = load_bronze_external_ids_by_voivodeship(output_dir)
    count = 0
    duplicate_count = 0
    caught_error: BaseException | None = None
    logger.info("Streaming bronze records by voivodeship under %s", output_dir)

    try:
        for estate in estates:
            voivodeship = estate.voivodeship or "unknown"
            external_id = str(estate.external_id)
            voivodeship_seen_ids = seen_external_ids.setdefault(voivodeship, set())

            if external_id in voivodeship_seen_ids:
                duplicate_count += 1
                continue

            pending_records_by_voivodeship.setdefault(voivodeship, []).append(
                estate.model_dump(mode="json")
            )
            new_counts_by_voivodeship[voivodeship] = (
                new_counts_by_voivodeship.get(voivodeship, 0) + 1
            )
            voivodeship_seen_ids.add(external_id)
            count += 1

            if count % 100 == 0:
                logger.info(
                    "Streamed %s new bronze records under %s",
                    count,
                    output_dir,
                )

            pending_count = len(pending_records_by_voivodeship[voivodeship])

            if pending_count >= BRONZE_STREAM_CHECKPOINT_INTERVAL:
                voivodeship_path = _append_voivodeship_checkpoint(
                    output_dir=output_dir,
                    voivodeship=voivodeship,
                    records=pending_records_by_voivodeship[voivodeship],
                    normalized_paths=normalized_paths,
                )
                paths_by_voivodeship[voivodeship] = voivodeship_path
                pending_records_by_voivodeship[voivodeship] = []
                logger.info(
                    "Checkpointed %s pending bronze records for voivodeship=%s to %s",
                    pending_count,
                    voivodeship,
                    voivodeship_path,
                )

    except BaseException as exc:
        caught_error = exc

    target_voivodeships = set(voivodeships) | set(pending_records_by_voivodeship)

    for voivodeship in sorted(target_voivodeships):
        pending_records = pending_records_by_voivodeship.get(voivodeship, [])
        voivodeship_path = _canonical_voivodeship_snapshot_path(
            output_dir,
            voivodeship,
        )

        if (
            not pending_records
            and voivodeship not in paths_by_voivodeship
            and not voivodeship_path.exists()
        ):
            continue

        if pending_records:
            voivodeship_path = _append_voivodeship_checkpoint(
                output_dir=output_dir,
                voivodeship=voivodeship,
                records=pending_records,
                normalized_paths=normalized_paths,
            )
            pending_records_by_voivodeship[voivodeship] = []

        paths_by_voivodeship[voivodeship] = voivodeship_path

    manifest: dict[str, Any] = {
        "updated_at": snapshot_time.isoformat(),
        "estate_types": list(estate_types),
        "voivodeships": list(voivodeships),
        "max_page": max_page,
        "new_records_count": count,
        "duplicates_skipped": duplicate_count,
        "page_checkpoints": _build_page_checkpoints(
            existing_manifest.get("page_checkpoints"),
            page_checkpoints_by_voivodeship,
            updated_at=snapshot_time,
        ),
        "files": {
            voivodeship: {
                "path": str(path),
                "new_records_count": new_counts_by_voivodeship.get(voivodeship, 0),
                "total_records_count": len(seen_external_ids.get(voivodeship, set())),
            }
            for voivodeship, path in sorted(paths_by_voivodeship.items())
        },
    }
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "Finished bronze streaming: new_records=%s duplicates=%s manifest=%s",
        count,
        duplicate_count,
        output_path,
    )

    if caught_error is not None:
        raise caught_error

    return output_path, count


def load_bronze_page_checkpoints(
    bronze_dir: Path = BRONZE_DATA_DIR,
) -> dict[str, dict[str, int]]:
    """Load last completed pages grouped by voivodeship and estate type.

    Args:
        bronze_dir: Directory containing the canonical bronze manifest.

    Returns:
        Last completed page numbers grouped by voivodeship and estate type.
    """
    manifest = _load_stream_manifest(bronze_dir / _build_stream_manifest_filename())
    checkpoints = manifest.get("page_checkpoints")

    if not isinstance(checkpoints, dict):
        return {}

    return _extract_page_checkpoint_values(checkpoints)


def load_bronze_external_ids_by_voivodeship(
    bronze_dir: Path = BRONZE_DATA_DIR,
) -> dict[str, set[str]]:
    """Load external ids already present in bronze snapshots.

    Args:
        bronze_dir: Directory containing bronze snapshots.

    Returns:
        External listing ids grouped by voivodeship.
    """
    external_ids: dict[str, set[str]] = {}

    if not bronze_dir.exists():
        return external_ids

    for snapshot_path in sorted(
        [
            *bronze_dir.glob("estate_snapshot_*.json"),
            *bronze_dir.glob("estate_snapshot_*.jsonl"),
            *bronze_dir.glob("*/estate_snapshot_*.json"),
            *bronze_dir.glob("*/estate_snapshot_*.jsonl"),
        ]
    ):
        for estate_data in _iter_bronze_estate_payloads(snapshot_path):
            external_id = estate_data.get("external_id")
            voivodeship = estate_data.get("voivodeship")

            if external_id is None or voivodeship is None:
                continue

            external_ids.setdefault(str(voivodeship), set()).add(str(external_id))

    return external_ids


def _load_stream_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    except json.JSONDecodeError:
        logger.warning("Could not parse bronze manifest %s", manifest_path)
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _build_page_checkpoints(
    existing_checkpoints: Any,
    current_pages: dict[str, dict[str, int]] | None,
    *,
    updated_at: datetime,
) -> dict[str, dict[str, dict[str, Any]]]:
    merged_pages = _extract_page_checkpoint_values(existing_checkpoints)

    for voivodeship, pages_by_estate_type in (current_pages or {}).items():
        if not isinstance(pages_by_estate_type, dict):
            continue

        for estate_type, page in pages_by_estate_type.items():
            if not isinstance(page, int) or page < 1:
                continue

            previous_page = merged_pages.get(voivodeship, {}).get(estate_type, 0)
            merged_pages.setdefault(voivodeship, {})[estate_type] = max(
                previous_page,
                page,
            )

    updated_at_value = updated_at.isoformat()

    return {
        voivodeship: {
            estate_type: {
                "last_completed_page": page,
                "next_page": page + 1,
                "updated_at": updated_at_value,
            }
            for estate_type, page in sorted(pages_by_estate_type.items())
        }
        for voivodeship, pages_by_estate_type in sorted(merged_pages.items())
    }


def _extract_page_checkpoint_values(checkpoints: Any) -> dict[str, dict[str, int]]:
    pages: dict[str, dict[str, int]] = {}

    if not isinstance(checkpoints, dict):
        return pages

    for voivodeship, estate_type_checkpoints in checkpoints.items():
        if not isinstance(voivodeship, str) or not isinstance(
            estate_type_checkpoints,
            dict,
        ):
            continue

        for estate_type, checkpoint in estate_type_checkpoints.items():
            if not isinstance(estate_type, str):
                continue

            page: int | None = None

            if isinstance(checkpoint, int):
                page = checkpoint

            elif isinstance(checkpoint, dict):
                raw_page = checkpoint.get("last_completed_page")

                if isinstance(raw_page, int):
                    page = raw_page

            if page is None or page < 1:
                continue

            pages.setdefault(voivodeship, {})[estate_type] = page

    return pages


def _iter_bronze_estate_payloads(snapshot_path: Path) -> Iterable[dict[str, Any]]:
    if snapshot_path.suffix == ".jsonl":
        with snapshot_path.open(encoding="utf-8") as input_file:
            for line in input_file:
                stripped_line = line.strip()

                if not stripped_line:
                    continue

                record = json.loads(stripped_line)

                if not isinstance(record, dict):
                    continue

                if record.get("record_type") != "estate":
                    continue

                estate_data = record.get("data")

                if isinstance(estate_data, dict):
                    yield estate_data

        return

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        return

    data = payload.get("data", [])

    if not isinstance(data, list):
        return

    for item in data:
        if isinstance(item, dict):
            yield item


def _append_voivodeship_checkpoint(
    *,
    output_dir: Path,
    voivodeship: str,
    records: list[dict[str, Any]],
    normalized_paths: set[Path] | None = None,
) -> Path:
    voivodeship_path = _canonical_voivodeship_snapshot_path(
        output_dir,
        voivodeship,
    )
    voivodeship_path.parent.mkdir(parents=True, exist_ok=True)

    if normalized_paths is not None and voivodeship_path not in normalized_paths:
        _ensure_estate_jsonl_only(voivodeship_path)
        normalized_paths.add(voivodeship_path)

    _ensure_trailing_newline(voivodeship_path)

    with voivodeship_path.open("a", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(
                json.dumps(
                    {
                        "record_type": "estate",
                        "data": record,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    return voivodeship_path


def _ensure_estate_jsonl_only(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    changed = False

    with (
        path.open(encoding="utf-8") as input_file,
        temp_path.open(
            "w",
            encoding="utf-8",
        ) as output_file,
    ):
        for line in input_file:
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                record = json.loads(stripped_line)

            except json.JSONDecodeError:
                changed = True
                continue

            if isinstance(record, dict) and record.get("record_type") == "estate":
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            changed = True

    if changed:
        temp_path.replace(path)
        return

    temp_path.unlink()


def _ensure_trailing_newline(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("rb+") as output_file:
        output_file.seek(-1, 2)

        if output_file.read(1) != b"\n":
            output_file.write(b"\n")


def _canonical_voivodeship_snapshot_path(
    output_dir: Path,
    voivodeship: str,
) -> Path:
    return output_dir / voivodeship / _build_canonical_voivodeship_filename(voivodeship)


def _build_snapshot_filename(scraped_at: datetime) -> str:
    timestamp = scraped_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"estate_snapshot_{timestamp}.json"


def _build_canonical_voivodeship_filename(voivodeship: str) -> str:
    return f"estate_snapshot_{voivodeship}.jsonl"


def _build_stream_manifest_filename() -> str:
    return "estate_snapshot_manifest.json"
