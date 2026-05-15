from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.globals import BRONZE_DATA_DIR
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


def _build_snapshot_filename(scraped_at: datetime) -> str:
    timestamp = scraped_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"estate_snapshot_{timestamp}.json"
