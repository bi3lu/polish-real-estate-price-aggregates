"""Storage helpers for writing and resuming bronze real estate snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.globals import BRONZE_DATA_DIR, BRONZE_STREAM_CHECKPOINT_INTERVAL
from src.ingestion.models import RawListingObservation
from src.utils.logger import get_logger

logger = get_logger(__name__)


def save_estates_to_bronze(
    estates: list[RawListingObservation],
    *,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
    output_dir: Path = BRONZE_DATA_DIR,
    scraped_at: datetime | None = None,
    adapter_types_by_source_id: Mapping[str, str] | None = None,
) -> Path:
    """Write estates to a source-partitioned bronze run snapshot.

    Args:
        estates: Raw listing observations to serialize.
        estate_types: Estate type filters represented in the snapshot.
        voivodeships: Voivodeship filters represented in the snapshot.
        max_page: Maximum page used during ingestion.
        output_dir: Directory where the snapshot is written.
        scraped_at: Optional ingestion timestamp used in metadata and filename.

    Returns:
        Path to the written JSON snapshot.
    """
    output_path, _ = stream_estates_to_bronze(
        estates,
        estate_types=estate_types,
        voivodeships=voivodeships,
        max_page=max_page,
        output_dir=output_dir,
        scraped_at=scraped_at,
        adapter_types_by_source_id=adapter_types_by_source_id,
    )
    return output_path


def stream_estates_to_bronze(
    estates: Iterable[RawListingObservation],
    *,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
    output_dir: Path = BRONZE_DATA_DIR,
    scraped_at: datetime | None = None,
    page_checkpoints_by_voivodeship: dict[str, dict[str, int]] | None = None,
    adapter_types_by_source_id: Mapping[str, str] | None = None,
) -> tuple[Path, int]:
    """Stream estates into source-id and run-id partitioned bronze files.

    Args:
        estates: Raw listing observations to persist.
        estate_types: Estate type filters represented in the manifest.
        voivodeships: Voivodeship filters represented in the manifest.
        max_page: Maximum page used during ingestion.
        output_dir: Directory where JSONL files and manifest are written.
        scraped_at: Optional ingestion timestamp used in manifest metadata.
        page_checkpoints_by_voivodeship: Completed ingestion pages to persist for
            resume support.
        adapter_types_by_source_id: Adapter type metadata keyed by source id.

    Returns:
        Tuple containing the manifest path and number of newly written records.

    Raises:
        BaseException: Re-raises any exception encountered while consuming the
            estate iterable after flushing pending records.
    """
    snapshot_time = scraped_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = _build_run_id(snapshot_time)
    output_path = output_dir / _build_stream_manifest_filename()
    existing_manifest = _load_stream_manifest(output_path)
    run_dirs_by_source: dict[str, Path] = {}
    data_paths_by_source: dict[str, Path] = {}
    pending_records_by_source: dict[str, list[dict[str, Any]]] = {}
    records_raw_by_source: dict[str, int] = {}
    records_written_by_source: dict[str, int] = {}
    duplicates_by_source: dict[str, int] = {}
    seen_external_ids = load_bronze_external_ids_by_voivodeship(output_dir)
    count = 0
    duplicate_count = 0
    caught_error: BaseException | None = None
    logger.info("Streaming bronze records by source_id under %s", output_dir)

    try:
        for estate in estates:
            source_id = estate.source_id or "source_a"
            voivodeship = estate.voivodeship or "unknown"
            external_id = _bronze_dedupe_key(
                source_id=source_id,
                external_id=estate.external_id,
            )
            voivodeship_seen_ids = seen_external_ids.setdefault(voivodeship, set())
            records_raw_by_source[source_id] = (
                records_raw_by_source.get(source_id, 0) + 1
            )

            if external_id in voivodeship_seen_ids:
                duplicates_by_source[source_id] = (
                    duplicates_by_source.get(source_id, 0) + 1
                )
                duplicate_count += 1
                continue

            pending_records_by_source.setdefault(source_id, []).append(
                estate.model_dump(mode="json")
            )
            records_written_by_source[source_id] = (
                records_written_by_source.get(source_id, 0) + 1
            )
            voivodeship_seen_ids.add(external_id)
            count += 1

            if count % 100 == 0:
                logger.info(
                    "Streamed %s new bronze records under %s",
                    count,
                    output_dir,
                )

            pending_count = len(pending_records_by_source[source_id])

            if pending_count >= BRONZE_STREAM_CHECKPOINT_INTERVAL:
                data_path = _append_source_run_checkpoint(
                    output_dir=output_dir,
                    source_id=source_id,
                    run_id=run_id,
                    records=pending_records_by_source[source_id],
                )
                run_dirs_by_source[source_id] = data_path.parent
                data_paths_by_source[source_id] = data_path
                pending_records_by_source[source_id] = []
                logger.info(
                    "Checkpointed %s pending bronze records for source_id=%s to %s",
                    pending_count,
                    source_id,
                    data_path,
                )

    except BaseException as exc:
        caught_error = exc

    target_sources = (
        set(records_raw_by_source)
        | set(pending_records_by_source)
        | set(adapter_types_by_source_id or {})
    )

    for source_id in sorted(target_sources):
        pending_records = pending_records_by_source.get(source_id, [])

        if pending_records:
            data_path = _append_source_run_checkpoint(
                output_dir=output_dir,
                source_id=source_id,
                run_id=run_id,
                records=pending_records,
            )
            pending_records_by_source[source_id] = []
            run_dirs_by_source[source_id] = data_path.parent
            data_paths_by_source[source_id] = data_path

        elif source_id not in data_paths_by_source:
            data_path = _source_run_data_path(
                output_dir,
                source_id=source_id,
                run_id=run_id,
            )
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.touch()
            run_dirs_by_source[source_id] = data_path.parent
            data_paths_by_source[source_id] = data_path

    run_manifests: dict[str, dict[str, Any]] = {}
    updated_at_value = snapshot_time.isoformat()
    merged_page_checkpoints = _build_page_checkpoints(
        existing_manifest.get("page_checkpoints"),
        page_checkpoints_by_voivodeship,
        updated_at=snapshot_time,
    )

    for source_id, run_dir in sorted(run_dirs_by_source.items()):
        data_path = data_paths_by_source[source_id]
        manifest_path = run_dir / "manifest.json"
        run_manifest = _build_source_run_manifest(
            source_id=source_id,
            run_id=run_id,
            adapter_type=(adapter_types_by_source_id or {}).get(source_id, "unknown"),
            started_at=snapshot_time,
            finished_at=snapshot_time,
            estate_types=estate_types,
            voivodeships=voivodeships,
            max_page=max_page,
            pages_requested=_estimated_pages_requested(
                estate_types=estate_types,
                voivodeships=voivodeships,
                max_page=max_page,
            ),
            pages_succeeded=_pages_succeeded(
                merged_page_checkpoints,
                default_pages=_estimated_pages_requested(
                    estate_types=estate_types,
                    voivodeships=voivodeships,
                    max_page=max_page,
                ),
            ),
            records_raw=records_raw_by_source.get(source_id, 0),
            records_canonical=records_written_by_source.get(source_id, 0),
            parser_errors=0,
            duplicates_skipped=duplicates_by_source.get(source_id, 0),
            data_path=data_path,
        )
        manifest_path.write_text(
            json.dumps(run_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        run_manifests[source_id] = {
            "path": str(manifest_path),
            "data_path": str(data_path),
            "run_id": run_id,
            "records_raw": records_raw_by_source.get(source_id, 0),
            "records_canonical": records_written_by_source.get(source_id, 0),
            "duplicates_skipped": duplicates_by_source.get(source_id, 0),
        }

    manifest: dict[str, Any] = {
        "updated_at": updated_at_value,
        "run_id": run_id,
        "estate_types": list(estate_types),
        "voivodeships": list(voivodeships),
        "max_page": max_page,
        "new_records_count": count,
        "duplicates_skipped": duplicate_count,
        "page_checkpoints": merged_page_checkpoints,
        "run_manifests": run_manifests,
        "files": {
            source_id: {
                "path": str(data_paths_by_source[source_id]),
                "new_records_count": records_written_by_source.get(source_id, 0),
                "total_records_count": records_raw_by_source.get(source_id, 0),
            }
            for source_id in sorted(data_paths_by_source)
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
    manifest_path = bronze_dir / _build_stream_manifest_filename()

    if not manifest_path.exists():
        manifest_path = bronze_dir / "estate_snapshot_manifest.json"

    manifest = _load_stream_manifest(manifest_path)
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
        path for path in bronze_dir.rglob("*.jsonl") if path.name != "manifest.json"
    ):
        for estate_data in _iter_bronze_estate_payloads(snapshot_path):
            external_id = estate_data.get("external_id")
            voivodeship = estate_data.get("voivodeship")
            source_id = estate_data.get("source_id") or estate_data.get("source")

            if external_id is None or voivodeship is None:
                continue

            external_ids.setdefault(str(voivodeship), set()).add(
                _bronze_dedupe_key(
                    source_id=str(source_id or "source_a"),
                    external_id=str(external_id),
                )
            )

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


def _append_source_run_checkpoint(
    *,
    output_dir: Path,
    source_id: str,
    run_id: str,
    records: list[dict[str, Any]],
) -> Path:
    data_path = _source_run_data_path(output_dir, source_id=source_id, run_id=run_id)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_trailing_newline(data_path)

    with data_path.open("a", encoding="utf-8") as output_file:
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

    return data_path


def _build_source_run_manifest(
    *,
    source_id: str,
    run_id: str,
    adapter_type: str,
    started_at: datetime,
    finished_at: datetime,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
    pages_requested: int,
    pages_succeeded: int,
    records_raw: int,
    records_canonical: int,
    parser_errors: int,
    duplicates_skipped: int,
    data_path: Path,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "run_id": run_id,
        "adapter_type": adapter_type,
        "started_at": _format_manifest_timestamp(started_at),
        "finished_at": _format_manifest_timestamp(finished_at),
        "pages_requested": pages_requested,
        "pages_succeeded": pages_succeeded,
        "records_raw": records_raw,
        "records_canonical": records_canonical,
        "parser_errors": parser_errors,
        "duplicates_skipped": duplicates_skipped,
        "estate_types": list(estate_types),
        "voivodeships": list(voivodeships),
        "max_page": max_page,
        "files": {
            "observations": str(data_path),
        },
    }


def _estimated_pages_requested(
    *,
    estate_types: tuple[str, ...],
    voivodeships: tuple[str, ...],
    max_page: int,
) -> int:
    return max(1, len(estate_types)) * max(1, len(voivodeships)) * max_page


def _pages_succeeded(
    page_checkpoints: dict[str, dict[str, dict[str, Any]]],
    *,
    default_pages: int,
) -> int:
    completed_pages = 0

    for checkpoints_by_target in page_checkpoints.values():
        for checkpoint in checkpoints_by_target.values():
            raw_page = checkpoint.get("last_completed_page")

            if isinstance(raw_page, int) and raw_page > 0:
                completed_pages += raw_page

    return completed_pages or default_pages


def _ensure_trailing_newline(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("rb+") as output_file:
        output_file.seek(-1, 2)

        if output_file.read(1) != b"\n":
            output_file.write(b"\n")


def _source_run_data_path(
    output_dir: Path,
    *,
    source_id: str,
    run_id: str,
) -> Path:
    return output_dir / source_id / run_id / "observations.jsonl"


def _bronze_dedupe_key(*, source_id: str, external_id: str) -> str:
    return f"{source_id}:{external_id}"


def _build_run_id(scraped_at: datetime) -> str:
    return scraped_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _format_manifest_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_stream_manifest_filename() -> str:
    return "manifest.json"
