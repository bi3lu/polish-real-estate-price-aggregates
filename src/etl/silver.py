"""Bronze-to-silver ETL transformations for real estate listings."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.config.globals import (
    ADDITIONAL_FEATURES,
    BRONZE_DATA_DIR,
    LIST_SEPARATOR,
    SILVER_DATA_DIR,
)
from src.models.estate import Estate
from src.models.silver_estate import SilverEstate
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_bronze_to_silver(
    *,
    bronze_path: Path | None = None,
    bronze_dir: Path = BRONZE_DATA_DIR,
    silver_dir: Path = SILVER_DATA_DIR,
    processed_at: datetime | None = None,
) -> Path:
    """Run the bronze-to-silver ETL stage.

    Args:
        bronze_path: Optional explicit bronze snapshot path. When omitted, the
            latest available bronze snapshot is loaded from ``bronze_dir``.
        bronze_dir: Directory containing bronze snapshots.
        silver_dir: Directory where the silver CSV snapshot is written.
        processed_at: Optional timestamp used for deterministic output names and
            record metadata.

    Returns:
        Path to the written silver CSV snapshot.
    """
    snapshot_time = processed_at or datetime.now(timezone.utc)

    if bronze_path is None:
        logger.info("Silver ETL started for bronze directory %s", bronze_dir)
        bronze_payload = load_bronze_directory_snapshot(bronze_dir)

    else:
        logger.info("Silver ETL started for bronze snapshot %s", bronze_path)
        bronze_payload = load_bronze_snapshot(bronze_path)

    silver_records = transform_bronze_payload(
        bronze_payload,
        processed_at=snapshot_time,
    )
    output_path = save_silver_snapshot(
        silver_records,
        output_dir=silver_dir,
        processed_at=snapshot_time,
    )
    logger.info(
        "Silver ETL finished: records=%s output_path=%s",
        len(silver_records),
        output_path,
    )

    return output_path


def find_latest_bronze_snapshot(bronze_dir: Path = BRONZE_DATA_DIR) -> Path:
    """Find the latest bronze snapshot or canonical manifest.

    Args:
        bronze_dir: Directory containing bronze snapshot files.

    Returns:
        Path to the latest bronze snapshot or manifest.

    Raises:
        FileNotFoundError: If no bronze snapshots are present.
    """
    canonical_manifest = bronze_dir / "estate_snapshot_manifest.json"

    if canonical_manifest.exists():
        return canonical_manifest

    snapshots = sorted(
        [
            *bronze_dir.glob("estate_snapshot_manifest_*.json"),
            *bronze_dir.glob("estate_snapshot_*.json"),
            *bronze_dir.glob("estate_snapshot_*.jsonl"),
            *bronze_dir.glob("*/estate_snapshot_*.json"),
            *bronze_dir.glob("*/estate_snapshot_*.jsonl"),
        ]
    )

    if not snapshots:
        raise FileNotFoundError(f"No bronze snapshots found in {bronze_dir}")

    return snapshots[-1]


def load_bronze_directory_snapshot(
    bronze_dir: Path = BRONZE_DATA_DIR,
) -> dict[str, Any]:
    """Load a complete bronze directory as one snapshot payload.

    Args:
        bronze_dir: Directory containing canonical voivodeship snapshots or
            legacy bronze snapshots.

    Returns:
        Bronze payload with merged metadata and listing data.
    """
    snapshot_paths = _find_canonical_voivodeship_snapshots(bronze_dir)

    if not snapshot_paths:
        snapshot_paths = [find_latest_bronze_snapshot(bronze_dir)]

    data: list[dict[str, Any]] = []
    voivodeships: list[str] = []
    estate_types: set[str] = set()
    scraped_at: str | None = None
    updated_at: str | None = None
    max_page: int | None = None

    for snapshot_path in snapshot_paths:
        payload = load_bronze_snapshot(snapshot_path)
        child_data = payload.get("data", [])

        if isinstance(child_data, list):
            data.extend(item for item in child_data if isinstance(item, dict))

        for voivodeship in payload.get("voivodeships", []):
            if isinstance(voivodeship, str) and voivodeship not in voivodeships:
                voivodeships.append(voivodeship)

        for item in child_data if isinstance(child_data, list) else []:
            if not isinstance(item, dict):
                continue

            voivodeship = item.get("voivodeship")

            if isinstance(voivodeship, str) and voivodeship not in voivodeships:
                voivodeships.append(voivodeship)

        for estate_type in payload.get("estate_types", []):
            if isinstance(estate_type, str):
                estate_types.add(estate_type)

        scraped_at = _latest_timestamp(
            scraped_at,
            _normalize_text(payload.get("scraped_at")),
        )
        updated_at = _latest_timestamp(
            updated_at,
            _normalize_text(payload.get("updated_at")),
        )

        if isinstance(payload.get("max_page"), int):
            max_page = payload["max_page"]

    return {
        "scraped_at": scraped_at or updated_at,
        "updated_at": updated_at,
        "estate_types": sorted(estate_types),
        "voivodeships": voivodeships,
        "max_page": max_page,
        "count": len(data),
        "data": data,
    }


def _find_canonical_voivodeship_snapshots(bronze_dir: Path) -> list[Path]:
    snapshots: list[Path] = []

    if not bronze_dir.exists():
        return snapshots

    for voivodeship_dir in sorted(
        path for path in bronze_dir.iterdir() if path.is_dir()
    ):
        snapshot_path = (
            voivodeship_dir / f"estate_snapshot_{voivodeship_dir.name}.jsonl"
        )

        if snapshot_path.exists():
            snapshots.append(snapshot_path)

    return snapshots


def _latest_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second

    if second is None:
        return first

    return max(first, second)


def load_bronze_snapshot(bronze_path: Path) -> dict[str, Any]:
    """Load a bronze snapshot from JSON, JSONL, or manifest format.

    Args:
        bronze_path: Snapshot file to load.

    Returns:
        Normalized bronze payload containing metadata and a ``data`` list.

    Raises:
        ValueError: If the snapshot root or JSONL rows have an unsupported shape.
    """
    if bronze_path.suffix == ".jsonl":
        return _load_bronze_jsonl_snapshot(bronze_path)

    payload = json.loads(bronze_path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError(f"Bronze snapshot root must be an object: {bronze_path}")

    if isinstance(payload.get("files"), dict):
        return _load_bronze_manifest(payload, manifest_path=bronze_path)

    return payload


def _load_bronze_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    data: list[dict[str, Any]] = []
    files = manifest.get("files", {})

    if not isinstance(files, dict):
        raise ValueError(
            f"Bronze manifest field 'files' must be an object: {manifest_path}"
        )

    for file_info in files.values():
        if not isinstance(file_info, dict):
            continue

        path_value = file_info.get("path")

        if not isinstance(path_value, str):
            continue

        snapshot_path = Path(path_value)

        if not snapshot_path.is_absolute():
            snapshot_path = manifest_path.parent / snapshot_path

        child_payload = load_bronze_snapshot(snapshot_path)
        child_data = child_payload.get("data", [])

        if isinstance(child_data, list):
            data.extend(item for item in child_data if isinstance(item, dict))

    return {
        **{key: value for key, value in manifest.items() if key != "files"},
        "count": len(data),
        "data": data,
    }


def _load_bronze_jsonl_snapshot(bronze_path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    data: list[dict[str, Any]] = []

    with bronze_path.open(encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            stripped_line = line.strip()

            if not stripped_line:
                continue

            record = json.loads(stripped_line)

            if not isinstance(record, dict):
                raise ValueError(
                    f"JSONL record must be an object in {bronze_path}:{line_number}"
                )

            record_type = record.get("record_type")

            if record_type == "metadata":
                metadata = {
                    key: value for key, value in record.items() if key != "record_type"
                }
                continue

            if record_type == "estate":
                estate_data = record.get("data")

                if isinstance(estate_data, dict):
                    data.append(estate_data)
                    continue

            raise ValueError(f"Unsupported JSONL record in {bronze_path}:{line_number}")

    return {
        **metadata,
        "count": len(data),
        "data": data,
    }


def transform_bronze_payload(
    bronze_payload: dict[str, Any],
    *,
    processed_at: datetime | None = None,
) -> list[SilverEstate]:
    """Transform a bronze payload into normalized silver records.

    Args:
        bronze_payload: Bronze snapshot payload containing raw listing objects.
        processed_at: Optional timestamp assigned to produced silver records.

    Returns:
        Deduplicated silver records keyed by source and external listing id.

    Raises:
        ValueError: If the bronze payload ``data`` field is not a list.
    """
    raw_items = bronze_payload.get("data", [])

    if not isinstance(raw_items, list):
        raise ValueError("Bronze snapshot field 'data' must be a list")

    snapshot_time = processed_at or datetime.now(timezone.utc)
    bronze_scraped_at = _normalize_text(bronze_payload.get("scraped_at"))
    records_by_id: dict[str, SilverEstate] = {}

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            logger.warning("Skipping non-object bronze item")
            continue

        try:
            bronze_estate = Estate.model_validate(raw_item)

        except ValidationError as exc:
            logger.warning("Skipping invalid bronze estate item: %s", exc)
            continue

        silver_estate = normalize_estate(
            bronze_estate,
            bronze_scraped_at=bronze_scraped_at,
            processed_at=snapshot_time,
        )

        if silver_estate is None:
            logger.warning("Skipping bronze item without external_id")
            continue

        records_by_id[silver_estate.record_id] = silver_estate

    return list(records_by_id.values())


def normalize_estate(
    estate: Estate,
    *,
    bronze_scraped_at: str | None = None,
    processed_at: datetime | None = None,
) -> SilverEstate | None:
    """Normalize one raw estate listing into the silver schema.

    Args:
        estate: Raw listing model produced by the scraper.
        bronze_scraped_at: Optional source scrape timestamp propagated from the
            bronze snapshot.
        processed_at: Optional processing timestamp for deterministic tests.

    Returns:
        A normalized silver record, or ``None`` when the listing has no usable
        external id.
    """
    snapshot_time = processed_at or datetime.now(timezone.utc)
    source = _normalize_slug(estate.source) or "estate_service"
    external_id = _normalize_text(estate.external_id)

    if external_id is None:
        return None

    attributes = _normalize_attributes(estate.attributes)
    images = _normalize_images(estate.images)
    price_pln = _normalize_non_negative_float(
        estate.price
        if estate.price is not None
        else _attribute_value(attributes, "price")
    )
    price_per_sqm_pln = _normalize_non_negative_float(
        estate.price_per_sqm
        if estate.price_per_sqm is not None
        else _attribute_value(attributes, "price_per_m", "price_per_sqm")
    )
    area_sqm = _normalize_non_negative_float(
        estate.area_sqm
        if estate.area_sqm is not None
        else _attribute_value(attributes, "m")
    )
    latitude = _normalize_float(estate.latitude)
    longitude = _normalize_float(estate.longitude)
    location = _normalize_location(
        location=estate.location,
        street=estate.street,
        district=estate.district,
        city=estate.city,
    )

    return SilverEstate(
        record_id=f"{source}:{external_id}",
        source=source,
        external_id=external_id,
        url=_normalize_text(estate.url),
        title=_normalize_text(estate.title),
        estate_type=_normalize_slug(estate.estate_type),
        voivodeship=_normalize_slug(estate.voivodeship),
        city=_normalize_text(estate.city),
        district=_normalize_text(estate.district),
        street=_normalize_text(estate.street),
        location=location,
        latitude=latitude,
        longitude=longitude,
        price_pln=price_pln,
        price_per_sqm_pln=price_per_sqm_pln,
        rent_pln=_normalize_non_negative_float(_attribute_value(attributes, "rent")),
        area_sqm=area_sqm,
        terrain_area_sqm=_normalize_non_negative_float(
            _attribute_value(attributes, "terrain_area")
        ),
        rooms=_normalize_non_negative_int(
            estate.rooms
            if estate.rooms is not None
            else _attribute_value(attributes, "rooms_num")
        ),
        floor=(
            estate.floor
            if estate.floor is not None
            else _normalize_floor(_attribute_value(attributes, "floor_no"))
        ),
        building_floors_num=_normalize_non_negative_int(
            _attribute_value(attributes, "building_floors_num")
        ),
        market=_normalize_slug(
            estate.market
            if estate.market is not None
            else _attribute_value(attributes, "market")
        ),
        building_type=_normalize_slug(
            estate.building_type
            if estate.building_type is not None
            else _attribute_value(attributes, "building_type")
        ),
        building_material=_normalize_slug(
            _attribute_value(attributes, "building_material")
        ),
        building_ownership=_normalize_slug(
            _attribute_value(attributes, "building_ownership")
        ),
        build_year=_normalize_non_negative_int(
            _attribute_value(attributes, "build_year")
        ),
        construction_status=_normalize_slug(
            _attribute_value(attributes, "construction_status")
        ),
        heating=_normalize_slug(_attribute_value(attributes, "heating")),
        windows_type=_normalize_slug(_attribute_value(attributes, "windows_type")),
        energy_certificate=_normalize_slug(
            _attribute_value(attributes, "energy_certificate")
        ),
        seller_name=_normalize_text(estate.seller_name),
        seller_type=_normalize_slug(estate.seller_type),
        seller_id=_normalize_text(_attribute_value(attributes, "seller_id")),
        advertiser_type=_normalize_slug(
            _attribute_value(attributes, "advertiser_type")
        ),
        user_type=_normalize_slug(_attribute_value(attributes, "user_type")),
        has_lift=_contains_any(attributes, ("lift", "extras_types"), ("y", "lift")),
        has_balcony=_contains_any(attributes, ("extras_types",), ("balcony",)),
        has_garage=_contains_any(attributes, ("extras_types",), ("garage",)),
        has_basement=_contains_any(attributes, ("extras_types",), ("basement",)),
        has_separate_kitchen=_contains_any(
            attributes,
            ("extras_types",),
            ("separate_kitchen",),
        ),
        has_air_conditioning=_contains_any(
            attributes,
            ("extras_types", "equipment_types"),
            ("air_conditioning",),
        ),
        has_garden=_contains_any(attributes, ("extras_types",), ("garden",)),
        security_types=_normalize_list_attribute(attributes, "security_types"),
        media_types=_normalize_list_attribute(attributes, "media_types"),
        equipment_types=_normalize_list_attribute(attributes, "equipment_types"),
        extras_types=_normalize_list_attribute(attributes, "extras_types"),
        additional_features=_normalize_additional_features(attributes),
        image_count=len(images),
        first_image_url=images[0] if images else None,
        has_price=price_pln is not None,
        has_location=location is not None,
        has_coordinates=latitude is not None and longitude is not None,
        bronze_scraped_at=bronze_scraped_at,
        processed_at=snapshot_time.isoformat(),
    )


def save_silver_snapshot(
    records: list[SilverEstate],
    *,
    output_dir: Path = SILVER_DATA_DIR,
    processed_at: datetime | None = None,
) -> Path:
    """Write silver records to a timestamped CSV snapshot.

    Args:
        records: Silver records to serialize.
        output_dir: Directory where the CSV snapshot is written.
        processed_at: Optional timestamp used in the output filename.

    Returns:
        Path to the written CSV file.
    """
    snapshot_time = processed_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _build_silver_filename(snapshot_time)
    logger.info("Writing silver CSV with %s records to %s", len(records), output_path)

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(SilverEstate.model_fields),
            extrasaction="raise",
        )
        writer.writeheader()

        for record in records:
            writer.writerow(_serialize_csv_row(record))

    return output_path


def _build_silver_filename(processed_at: datetime) -> str:
    timestamp = processed_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"estate_silver_{timestamp}.csv"


def _serialize_csv_row(record: SilverEstate) -> dict[str, Any]:
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


def _normalize_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None

    text = str(value).strip()

    if not text:
        return None

    return " ".join(text.split())


def _normalize_slug(value: Any) -> str | None:
    text = _normalize_value_token(value)

    if text is None:
        return None

    return text.lower().replace(" ", "_").replace("-", "_")


def _normalize_location(
    *,
    location: str | None,
    street: str | None,
    district: str | None,
    city: str | None,
) -> str | None:
    normalized_location = _normalize_text(location)

    if normalized_location is not None:
        return normalized_location

    return _normalize_text(
        ", ".join(
            part
            for part in (
                _normalize_text(street),
                _normalize_text(district),
                _normalize_text(city),
            )
            if part is not None
        )
    )


def _normalize_float(value: Any) -> float | None:
    scalar_value = _first_scalar(value)

    if scalar_value is None or isinstance(scalar_value, bool):
        return None

    try:
        return float(str(scalar_value).replace(",", "."))

    except (TypeError, ValueError):
        return None


def _normalize_non_negative_float(value: Any) -> float | None:
    normalized_value = _normalize_float(value)

    if normalized_value is None or normalized_value < 0:
        return None

    return normalized_value


def _normalize_non_negative_int(value: Any) -> int | None:
    normalized_value = _normalize_float(value)

    if normalized_value is None or normalized_value < 0:
        return None

    return int(normalized_value)


def _normalize_floor(value: Any) -> int | None:
    text_value = _normalize_value_token(value)

    if text_value is None:
        return None

    if text_value.startswith("floor_"):
        text_value = text_value.removeprefix("floor_")

    return _normalize_non_negative_int(text_value)


def _normalize_images(images: list[str]) -> list[str]:
    normalized_images = [
        normalized_image
        for image in images
        if (normalized_image := _normalize_text(image)) is not None
    ]

    return list(dict.fromkeys(normalized_images))


def _normalize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    normalized_attributes: dict[str, Any] = {}

    for key, value in sorted(attributes.items()):
        normalized_key = _normalize_slug(key)

        if normalized_key is not None:
            normalized_attributes[normalized_key] = value

    return normalized_attributes


def _attribute_value(attributes: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        normalized_key = _normalize_slug(key)

        if normalized_key in attributes:
            return attributes[normalized_key]

    return None


def _normalize_list_attribute(attributes: dict[str, Any], key: str) -> str | None:
    value = _attribute_value(attributes, key)
    normalized_values = _normalize_value_tokens(value)

    if not normalized_values:
        return None

    return LIST_SEPARATOR.join(dict.fromkeys(normalized_values))


def _normalize_additional_features(attributes: dict[str, Any]) -> str | None:
    features: list[str] = []

    for key in ADDITIONAL_FEATURES:
        features.extend(_normalize_value_tokens(_attribute_value(attributes, key)))

    if not features:
        return None

    return LIST_SEPARATOR.join(dict.fromkeys(features))


def _contains_any(
    attributes: dict[str, Any],
    keys: tuple[str, ...],
    expected_values: tuple[str, ...],
) -> bool:
    expected_set = {_normalize_slug(value) for value in expected_values}

    for key in keys:
        values = _normalize_value_tokens(_attribute_value(attributes, key))

        if any(value in expected_set for value in values):
            return True

    return False


def _normalize_value_tokens(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        tokens: list[str] = []

        for item in value:
            tokens.extend(_normalize_value_tokens(item))

        return tokens

    normalized_value = _normalize_value_token(value)

    if normalized_value is None:
        return []

    return [normalized_value]


def _normalize_value_token(value: Any) -> str | None:
    scalar_value = _first_scalar(value)
    text_value = _normalize_text(scalar_value)

    if text_value is None:
        return None

    if "::" in text_value:
        text_value = text_value.rsplit("::", maxsplit=1)[-1]

    return text_value.lower().replace(" ", "_").replace("-", "_")


def _first_scalar(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            scalar_value = _first_scalar(item)

            if scalar_value is not None:
                return scalar_value

        return None

    return value


if __name__ == "__main__":
    run_bronze_to_silver()
