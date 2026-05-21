"""Compatibility facade for real estate ingestion utilities."""

from __future__ import annotations

from src.ingestion.parsing import (
    extract_estate_detail,
    extract_listing_items,
    get_estate_info,
)
from src.ingestion.pipeline import (
    IngestionProgressCallback,
    ingest_estates,
    ingest_estates_for,
    iter_estates,
    iter_estates_for,
    iter_estates_threaded,
)
from src.ingestion.transport import (
    build_listing_url,
    extract_next_data_from_html,
    fetch_next_data_json,
)
from src.utils.logger import get_logger

__all__ = [
    "IngestionProgressCallback",
    "build_listing_url",
    "extract_estate_detail",
    "extract_listing_items",
    "extract_next_data_from_html",
    "fetch_next_data_json",
    "get_estate_info",
    "ingest_estates",
    "ingest_estates_for",
    "iter_estates",
    "iter_estates_for",
    "iter_estates_threaded",
]

logger = get_logger(__name__)


if __name__ == "__main__":
    ingested_estates = ingest_estates()
    logger.info("Ingested %s estates", len(ingested_estates))
