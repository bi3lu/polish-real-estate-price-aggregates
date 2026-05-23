"""Pagination and orchestration for real estate ingestion."""

from __future__ import annotations

import queue
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any

from _thread import LockType

from src.config.globals import (
    ESTATE_TYPES,
    MAX_PAGE,
    RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    VOIVODESHIPS,
)
from src.config.types import IngestionProgressCallback, SearchShardStrategy
from src.ingestion.parsing import (
    enrich_listing_item,
    extract_listing_external_id,
    extract_listing_items,
    get_estate_info,
)
from src.ingestion.transport import build_listing_url, fetch_next_data_json
from src.models.estate import Estate
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SearchShard:
    """Additional source filters used to split large listing searches."""

    key: str
    query_params: Mapping[str, str]


@dataclass(frozen=True)
class _WorkerFinished:
    """Completion marker emitted by threaded ingestion workers."""

    estate_type: str
    voivodeship: str
    count: int
    error: Exception | None = None


_BASE_SEARCH_SHARD = SearchShard(key="base", query_params={})
_PRICE_SHARDS: tuple[SearchShard, ...] = (
    SearchShard(
        key="price-lt-300k",
        query_params={"search[filter_float_price:to]": "300000"},
    ),
    SearchShard(
        key="price-300k-400k",
        query_params={
            "search[filter_float_price:from]": "300000",
            "search[filter_float_price:to]": "400000",
        },
    ),
    SearchShard(
        key="price-400k-500k",
        query_params={
            "search[filter_float_price:from]": "400000",
            "search[filter_float_price:to]": "500000",
        },
    ),
    SearchShard(
        key="price-500k-600k",
        query_params={
            "search[filter_float_price:from]": "500000",
            "search[filter_float_price:to]": "600000",
        },
    ),
    SearchShard(
        key="price-600k-750k",
        query_params={
            "search[filter_float_price:from]": "600000",
            "search[filter_float_price:to]": "750000",
        },
    ),
    SearchShard(
        key="price-750k-1000k",
        query_params={
            "search[filter_float_price:from]": "750000",
            "search[filter_float_price:to]": "1000000",
        },
    ),
    SearchShard(
        key="price-1000k-1500k",
        query_params={
            "search[filter_float_price:from]": "1000000",
            "search[filter_float_price:to]": "1500000",
        },
    ),
    SearchShard(
        key="price-gte-1500k",
        query_params={"search[filter_float_price:from]": "1500000"},
    ),
)
_MARKET_SHARDS: tuple[tuple[str, str], ...] = (
    ("market-primary", "primary"),
    ("market-secondary", "secondary"),
)


def build_search_shards(strategy: str) -> tuple[SearchShard, ...]:
    """Build source search shards for large result sets."""
    if strategy == "none":
        return (_BASE_SEARCH_SHARD,)

    if strategy == "price":
        return _PRICE_SHARDS

    if strategy == "market-price":
        return tuple(
            SearchShard(
                key=f"{market_key}__{price_shard.key}",
                query_params={
                    "search[filter_enum_market][0]": market_value,
                    **dict(price_shard.query_params),
                },
            )
            for market_key, market_value in _MARKET_SHARDS
            for price_shard in _PRICE_SHARDS
        )

    raise ValueError(
        "Unsupported search shard strategy: "
        f"{strategy}. Allowed values: none, price, market-price"
    )


def ingest_estates_for(
    estate_type: str,
    voivodeship: str,
    *,
    max_page: int = MAX_PAGE,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids: Iterable[str] = (),
    start_page: int = 1,
    duplicate_page_stop_threshold: int = RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    query_params: Mapping[str, str] | None = None,
    checkpoint_key: str | None = None,
    progress_callback: IngestionProgressCallback | None = None,
) -> list[Estate]:
    """Ingest listings for a single estate type and voivodeship.

    Args:
        estate_type: Estate type slug.
        voivodeship: Voivodeship slug.
        max_page: Highest listing page to request.
        fetcher: Callable used to fetch listing pages.
        detail_fetcher: Optional callable used to fetch listing detail pages.
        existing_external_ids: Existing ids skipped during resume.
        start_page: First page to process.
        duplicate_page_stop_threshold: Consecutive duplicate-only pages allowed
            before stopping resume pagination.
        query_params: Additional listing search query parameters.
        checkpoint_key: Optional target key used in progress checkpoints.
        progress_callback: Optional callback invoked after each completed page.

    Returns:
        Ingested estate records.
    """
    return list(
        iter_estates_for(
            estate_type,
            voivodeship,
            max_page=max_page,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids=existing_external_ids,
            start_page=start_page,
            duplicate_page_stop_threshold=duplicate_page_stop_threshold,
            query_params=query_params,
            checkpoint_key=checkpoint_key,
            progress_callback=progress_callback,
        )
    )


def iter_estates_for(
    estate_type: str,
    voivodeship: str,
    *,
    max_page: int = MAX_PAGE,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids: Iterable[str] = (),
    start_page: int = 1,
    duplicate_page_stop_threshold: int = RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    query_params: Mapping[str, str] | None = None,
    checkpoint_key: str | None = None,
    progress_callback: IngestionProgressCallback | None = None,
) -> Iterable[Estate]:
    """Yield listings for a single estate type and voivodeship.

    Args:
        estate_type: Estate type slug.
        voivodeship: Voivodeship slug.
        max_page: Highest listing page to request.
        fetcher: Callable used to fetch listing pages.
        detail_fetcher: Optional callable used to fetch listing detail pages.
        existing_external_ids: Existing ids skipped during resume.
        start_page: First page to process.
        duplicate_page_stop_threshold: Consecutive duplicate-only pages allowed
            before stopping resume pagination.
        query_params: Additional listing search query parameters.
        checkpoint_key: Optional target key used in progress checkpoints.
        progress_callback: Optional callback invoked after each completed page.

    Yields:
        Estate records discovered on listing pages.

    Raises:
        ValueError: If filters or ``start_page`` are invalid.
    """
    if estate_type not in ESTATE_TYPES:
        raise ValueError(f"Unsupported estate type: {estate_type}")

    if voivodeship not in VOIVODESHIPS:
        raise ValueError(f"Unsupported voivodeship: {voivodeship}")

    if start_page < 1:
        raise ValueError("start_page must be greater than or equal to 1")

    if duplicate_page_stop_threshold < 0:
        raise ValueError(
            "duplicate_page_stop_threshold must be greater than or equal to 0"
        )

    total_estates_count = 0
    seen_external_ids: set[str] = {
        str(external_id) for external_id in existing_external_ids
    }
    existing_external_ids_count = len(seen_external_ids)
    duplicate_only_page_count = 0
    seen_page_signatures: set[tuple[str, ...]] = set()
    target_key = checkpoint_key or estate_type
    logger.info(
        "Streaming ingestion started for estate_type=%s voivodeship=%s target=%s "
        "max_page=%s start_page=%s existing_ids=%s query_params=%s",
        estate_type,
        voivodeship,
        target_key,
        max_page,
        start_page,
        existing_external_ids_count,
        dict(query_params or {}),
    )

    for page in range(start_page, max_page + 1):
        listing_url = build_listing_url(
            estate_type,
            voivodeship,
            page=page,
            query_params=query_params,
        )
        logger.info(
            "Fetching listing page %s for estate_type=%s voivodeship=%s target=%s",
            page,
            estate_type,
            voivodeship,
            target_key,
        )
        next_data_json = fetcher(listing_url)
        listing_items = extract_listing_items(next_data_json)

        if not listing_items:
            _mark_page_completed(
                progress_callback,
                estate_type=target_key,
                voivodeship=voivodeship,
                page=page,
            )
            logger.info(
                "No listing items found on page %s for estate_type=%s "
                "voivodeship=%s; stopping pagination",
                page,
                estate_type,
                voivodeship,
            )
            break

        page_signature = _listing_page_signature(listing_items)
        page_signature_key = tuple(sorted(page_signature))

        if page_signature and page_signature_key in seen_page_signatures:
            logger.warning(
                "Page %s for estate_type=%s voivodeship=%s target=%s repeated "
                "a previously seen listing page signature; stopping pagination",
                page,
                estate_type,
                voivodeship,
                target_key,
            )
            break

        if page_signature:
            seen_page_signatures.add(page_signature_key)

        page_estates_count = 0
        page_duplicate_count = 0

        for listing_item in listing_items:
            listing_external_id = extract_listing_external_id(listing_item)

            if (
                listing_external_id is not None
                and listing_external_id in seen_external_ids
            ):
                page_duplicate_count += 1
                continue

            enriched_item = enrich_listing_item(
                listing_item,
                detail_fetcher=detail_fetcher,
            )
            estate = get_estate_info(
                enriched_item,
                estate_type=estate_type,
                voivodeship=voivodeship,
            )

            if estate is None:
                logger.warning(
                    "Skipping listing item without usable external id for "
                    "estate_type=%s voivodeship=%s page=%s",
                    estate_type,
                    voivodeship,
                    page,
                )
                continue

            if estate.external_id in seen_external_ids:
                page_duplicate_count += 1
                continue

            seen_external_ids.add(estate.external_id)
            page_estates_count += 1
            total_estates_count += 1
            yield estate

        logger.info(
            "Processed page %s for estate_type=%s voivodeship=%s: "
            "items=%s estates=%s duplicates=%s total=%s",
            page,
            estate_type,
            voivodeship,
            len(listing_items),
            page_estates_count,
            page_duplicate_count,
            total_estates_count,
        )
        _mark_page_completed(
            progress_callback,
            estate_type=target_key,
            voivodeship=voivodeship,
            page=page,
        )

        if page_estates_count > 0:
            duplicate_only_page_count = 0
            continue

        if page_duplicate_count > 0:
            duplicate_only_page_count += 1

            if duplicate_page_stop_threshold == 0:
                logger.info(
                    "Page %s for estate_type=%s voivodeship=%s target=%s "
                    "contained only duplicates (%s); continuing pagination "
                    "(duplicate-only stop disabled)",
                    page,
                    estate_type,
                    voivodeship,
                    target_key,
                    page_duplicate_count,
                )
                continue

            if duplicate_only_page_count < duplicate_page_stop_threshold:
                logger.info(
                    "Page %s for estate_type=%s voivodeship=%s target=%s "
                    "contained only duplicates (%s); continuing resume pagination "
                    "(duplicate_only_pages=%s/%s)",
                    page,
                    estate_type,
                    voivodeship,
                    target_key,
                    page_duplicate_count,
                    duplicate_only_page_count,
                    duplicate_page_stop_threshold,
                )
                continue

            logger.warning(
                "Page %s for estate_type=%s voivodeship=%s target=%s contained "
                "no new listings (duplicates=%s duplicate_only_pages=%s); "
                "stopping pagination",
                page,
                estate_type,
                voivodeship,
                target_key,
                page_duplicate_count,
                duplicate_only_page_count,
            )
            break

        logger.warning(
            "Page %s for estate_type=%s voivodeship=%s contained no usable "
            "listings; stopping pagination",
            page,
            estate_type,
            voivodeship,
        )
        break

    logger.info(
        "Streaming ingestion finished for estate_type=%s voivodeship=%s target=%s "
        "total=%s",
        estate_type,
        voivodeship,
        target_key,
        total_estates_count,
    )


def iter_estates(
    *,
    estate_types: Iterable[str] = ESTATE_TYPES,
    voivodeships: Iterable[str] = VOIVODESHIPS,
    max_page: int = MAX_PAGE,
    workers: int = 1,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids_by_voivodeship: Mapping[str, Iterable[str]] | None = None,
    start_pages_by_target: Mapping[str, Mapping[str, int]] | None = None,
    duplicate_page_stop_threshold: int = RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    search_shard_strategy: SearchShardStrategy = "none",
    progress_callback: IngestionProgressCallback | None = None,
) -> Iterable[Estate]:
    """Yield listings for all requested estate type and voivodeship combinations.

    Args:
        estate_types: Estate type slugs to process.
        voivodeships: Voivodeship slugs to process.
        max_page: Highest listing page to request for each target.
        workers: Number of worker threads. Values above one use threaded mode.
        fetcher: Callable used to fetch listing pages.
        detail_fetcher: Optional callable used to fetch listing detail pages.
        existing_external_ids_by_voivodeship: Existing ids grouped by voivodeship.
        start_pages_by_target: Last completed pages grouped by voivodeship and
            estate type.
        duplicate_page_stop_threshold: Consecutive duplicate-only pages allowed
            before stopping resume pagination.
        search_shard_strategy: Strategy used to split large source searches.
        progress_callback: Optional callback invoked after each completed page.

    Yields:
        Estate records for all requested targets.
    """
    search_shards = build_search_shards(search_shard_strategy)

    if workers > 1:
        yield from iter_estates_threaded(
            estate_types=estate_types,
            voivodeships=voivodeships,
            max_page=max_page,
            workers=workers,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids_by_voivodeship=existing_external_ids_by_voivodeship,
            start_pages_by_target=start_pages_by_target,
            duplicate_page_stop_threshold=duplicate_page_stop_threshold,
            search_shard_strategy=search_shard_strategy,
            progress_callback=progress_callback,
        )
        return

    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))
    seen_ids_by_voivodeship = _build_seen_ids_by_voivodeship(
        selected_voivodeships,
        existing_external_ids_by_voivodeship,
    )
    total_estates_count = 0

    logger.info(
        "Streaming ingestion started for estate_types=%s voivodeships=%s max_page=%s "
        "shard_strategy=%s shards=%s",
        ", ".join(selected_estate_types),
        ", ".join(selected_voivodeships),
        max_page,
        search_shard_strategy,
        len(search_shards),
    )

    for estate_type in selected_estate_types:
        for voivodeship in selected_voivodeships:
            seen_ids = seen_ids_by_voivodeship.setdefault(voivodeship, set())

            for shard in search_shards:
                target_key = _target_key(estate_type, shard)

                for estate in iter_estates_for(
                    estate_type,
                    voivodeship,
                    max_page=max_page,
                    fetcher=fetcher,
                    detail_fetcher=detail_fetcher,
                    existing_external_ids=seen_ids,
                    start_page=_target_start_page(
                        start_pages_by_target,
                        estate_type=target_key,
                        voivodeship=voivodeship,
                    ),
                    duplicate_page_stop_threshold=duplicate_page_stop_threshold,
                    query_params=shard.query_params,
                    checkpoint_key=target_key,
                    progress_callback=progress_callback,
                ):
                    if estate.external_id in seen_ids:
                        continue

                    seen_ids.add(estate.external_id)
                    total_estates_count += 1
                    yield estate

    logger.info(
        "Streaming ingestion finished for all filters total=%s", total_estates_count
    )


def iter_estates_threaded(
    *,
    estate_types: Iterable[str] = ESTATE_TYPES,
    voivodeships: Iterable[str] = VOIVODESHIPS,
    max_page: int = MAX_PAGE,
    workers: int = 4,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids_by_voivodeship: Mapping[str, Iterable[str]] | None = None,
    start_pages_by_target: Mapping[str, Mapping[str, int]] | None = None,
    duplicate_page_stop_threshold: int = RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    search_shard_strategy: SearchShardStrategy = "none",
    progress_callback: IngestionProgressCallback | None = None,
) -> Iterable[Estate]:
    """Yield listings using worker threads split by filter combinations.

    Args:
        estate_types: Estate type slugs to process.
        voivodeships: Voivodeship slugs to process.
        max_page: Highest listing page to request for each target.
        workers: Requested number of worker threads.
        fetcher: Callable used to fetch listing pages.
        detail_fetcher: Optional callable used to fetch listing detail pages.
        existing_external_ids_by_voivodeship: Existing ids grouped by voivodeship.
        start_pages_by_target: Last completed pages grouped by voivodeship and
            estate type.
        duplicate_page_stop_threshold: Consecutive duplicate-only pages allowed
            before stopping resume pagination.
        search_shard_strategy: Strategy used to split large source searches.
        progress_callback: Optional callback invoked after each completed page.

    Yields:
        Estate records emitted by worker threads.

    Raises:
        ValueError: If ``workers`` is lower than one.
        RuntimeError: If a worker fails while processing a target.
    """
    if workers < 1:
        raise ValueError("workers must be greater than or equal to 1")

    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))
    search_shards = build_search_shards(search_shard_strategy)
    ingestion_targets = tuple(
        (estate_type, voivodeship, shard)
        for estate_type in selected_estate_types
        for voivodeship in selected_voivodeships
        for shard in search_shards
    )

    if not ingestion_targets:
        return

    seen_ids_by_voivodeship = _build_seen_ids_by_voivodeship(
        selected_voivodeships,
        existing_external_ids_by_voivodeship,
    )
    seen_ids_lock = Lock()
    max_workers = min(workers, len(ingestion_targets))
    output_queue: queue.Queue[Estate | _WorkerFinished] = queue.Queue(
        maxsize=max_workers * 100
    )
    total_estates_count = 0

    logger.info(
        "Threaded streaming ingestion started: estate_types=%s voivodeships=%s "
        "max_page=%s workers=%s active_workers=%s shard_strategy=%s shards=%s",
        ", ".join(selected_estate_types),
        ", ".join(selected_voivodeships),
        max_page,
        workers,
        max_workers,
        search_shard_strategy,
        len(search_shards),
    )

    def ingest_target(
        estate_type: str,
        voivodeship: str,
        shard: SearchShard,
    ) -> int:
        count = 0
        target_key = _target_key(estate_type, shard)

        try:
            for estate in iter_estates_for(
                estate_type,
                voivodeship,
                max_page=max_page,
                fetcher=fetcher,
                detail_fetcher=detail_fetcher,
                existing_external_ids=_snapshot_seen_ids(
                    seen_ids_by_voivodeship,
                    seen_ids_lock,
                    voivodeship,
                ),
                start_page=_target_start_page(
                    start_pages_by_target,
                    estate_type=target_key,
                    voivodeship=voivodeship,
                ),
                duplicate_page_stop_threshold=duplicate_page_stop_threshold,
                query_params=shard.query_params,
                checkpoint_key=target_key,
                progress_callback=progress_callback,
            ):
                if not _remember_seen_id(
                    seen_ids_by_voivodeship,
                    seen_ids_lock,
                    voivodeship,
                    estate.external_id,
                ):
                    continue

                output_queue.put(estate)
                count += 1

        except Exception as exc:
            output_queue.put(
                _WorkerFinished(
                    estate_type=target_key,
                    voivodeship=voivodeship,
                    count=count,
                    error=exc,
                )
            )
            raise

        output_queue.put(
            _WorkerFinished(
                estate_type=target_key,
                voivodeship=voivodeship,
                count=count,
            )
        )
        return count

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="estate-ingestion",
    ) as executor:
        futures = [
            executor.submit(ingest_target, estate_type, voivodeship, shard)
            for estate_type, voivodeship, shard in ingestion_targets
        ]
        remaining_targets = len(futures)

        try:
            while remaining_targets:
                item = output_queue.get()

                if isinstance(item, _WorkerFinished):
                    remaining_targets -= 1

                    if item.error is not None:
                        for future in futures:
                            future.cancel()

                        logger.error(
                            "Threaded ingestion failed for estate_type=%s "
                            "voivodeship=%s after %s records: %s",
                            item.estate_type,
                            item.voivodeship,
                            item.count,
                            item.error,
                        )
                        raise RuntimeError(
                            "Threaded ingestion failed for "
                            f"estate_type={item.estate_type} "
                            f"voivodeship={item.voivodeship}"
                        ) from item.error

                    logger.info(
                        "Threaded ingestion worker finished for estate_type=%s "
                        "voivodeship=%s records=%s",
                        item.estate_type,
                        item.voivodeship,
                        item.count,
                    )
                    continue

                total_estates_count += 1
                yield item

        finally:
            for future in futures:
                future.cancel()

        for future in futures:
            future.result()

    logger.info(
        "Threaded streaming ingestion finished for all filters total=%s",
        total_estates_count,
    )


def ingest_estates(
    *,
    estate_types: Iterable[str] = ESTATE_TYPES,
    voivodeships: Iterable[str] = VOIVODESHIPS,
    max_page: int = MAX_PAGE,
    workers: int = 1,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids_by_voivodeship: Mapping[str, Iterable[str]] | None = None,
    start_pages_by_target: Mapping[str, Mapping[str, int]] | None = None,
    duplicate_page_stop_threshold: int = RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
    search_shard_strategy: SearchShardStrategy = "none",
    progress_callback: IngestionProgressCallback | None = None,
) -> list[Estate]:
    """Ingest listings for all requested estate type and voivodeship combinations.

    Args:
        estate_types: Estate type slugs to process.
        voivodeships: Voivodeship slugs to process.
        max_page: Highest listing page to request for each target.
        workers: Number of worker threads.
        fetcher: Callable used to fetch listing pages.
        detail_fetcher: Optional callable used to fetch listing detail pages.
        existing_external_ids_by_voivodeship: Existing ids grouped by voivodeship.
        start_pages_by_target: Last completed pages grouped by voivodeship and
            estate type.
        duplicate_page_stop_threshold: Consecutive duplicate-only pages allowed
            before stopping resume pagination.
        search_shard_strategy: Strategy used to split large source searches.
        progress_callback: Optional callback invoked after each completed page.

    Returns:
        Ingested estate records.
    """
    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))

    logger.info(
        "Ingestion started for estate_types=%s voivodeships=%s max_page=%s workers=%s",
        ", ".join(selected_estate_types),
        ", ".join(selected_voivodeships),
        max_page,
        workers,
    )

    estates = list(
        iter_estates(
            estate_types=selected_estate_types,
            voivodeships=selected_voivodeships,
            max_page=max_page,
            workers=workers,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids_by_voivodeship=existing_external_ids_by_voivodeship,
            start_pages_by_target=start_pages_by_target,
            duplicate_page_stop_threshold=duplicate_page_stop_threshold,
            search_shard_strategy=search_shard_strategy,
            progress_callback=progress_callback,
        )
    )

    logger.info("Ingestion finished for all filters total=%s", len(estates))

    return estates


def _target_start_page(
    start_pages_by_target: Mapping[str, Mapping[str, int]] | None,
    *,
    estate_type: str,
    voivodeship: str,
) -> int:
    if start_pages_by_target is None:
        return 1

    last_completed_page = start_pages_by_target.get(voivodeship, {}).get(estate_type)

    if not isinstance(last_completed_page, int) or last_completed_page < 1:
        return 1

    return last_completed_page + 1


def _target_key(estate_type: str, shard: SearchShard) -> str:
    if shard.key == _BASE_SEARCH_SHARD.key:
        return estate_type

    return f"{estate_type}__{shard.key}"


def _listing_page_signature(
    listing_items: Iterable[Mapping[str, Any]],
) -> tuple[str, ...]:
    signature: list[str] = []

    for index, listing_item in enumerate(listing_items):
        external_id = extract_listing_external_id(listing_item)

        if external_id is not None:
            signature.append(external_id)
            continue

        fallback_value = (
            listing_item.get("id")
            or listing_item.get("url")
            or listing_item.get("href")
            or listing_item.get("slug")
            or listing_item.get("title")
            or f"item-{index}"
        )
        signature.append(str(fallback_value))

    return tuple(signature)


def _build_seen_ids_by_voivodeship(
    voivodeships: Iterable[str],
    existing_external_ids_by_voivodeship: Mapping[str, Iterable[str]] | None,
) -> dict[str, set[str]]:
    existing_ids = existing_external_ids_by_voivodeship or {}

    return {
        voivodeship: {
            str(external_id) for external_id in existing_ids.get(voivodeship, ())
        }
        for voivodeship in voivodeships
    }


def _snapshot_seen_ids(
    seen_ids_by_voivodeship: dict[str, set[str]],
    lock: LockType,
    voivodeship: str,
) -> set[str]:
    with lock:
        return set(seen_ids_by_voivodeship.setdefault(voivodeship, set()))


def _remember_seen_id(
    seen_ids_by_voivodeship: dict[str, set[str]],
    lock: LockType,
    voivodeship: str,
    external_id: str,
) -> bool:
    with lock:
        seen_ids = seen_ids_by_voivodeship.setdefault(voivodeship, set())

        if external_id in seen_ids:
            return False

        seen_ids.add(external_id)
        return True


def _mark_page_completed(
    progress_callback: IngestionProgressCallback | None,
    *,
    estate_type: str,
    voivodeship: str,
    page: int,
) -> None:
    if progress_callback is None:
        return

    progress_callback(estate_type, voivodeship, page)
