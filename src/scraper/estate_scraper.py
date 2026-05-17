"""Scraper for real estate listings."""

from __future__ import annotations

import json
import queue
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, cast

from src.config.globals import (
    ESTATE_TYPES,
    ESTATE_URL,
    FLOOR_MAP,
    HEADERS,
    MAIN_URL,
    MAX_PAGE,
    NUMBER_RE,
    REQUEST_RETRIES,
    REQUEST_RETRY_SLEEP_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    ROOMS_NUM_MAP,
    SERVICE_SOURCE,
    VOIVODESHIPS,
    RESUME_DUPLICATE_PAGE_STOP_THRESHOLD,
)
from src.models.estate import Estate
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class _WorkerFinished:
    estate_type: str
    voivodeship: str
    count: int
    error: Exception | None = None


class _NextDataHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._is_next_data = False
        self._chunks: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "script":
            return

        script_attrs = dict(attrs)
        self._is_next_data = script_attrs.get("id") == "__NEXT_DATA__"

    def handle_data(self, data: str) -> None:
        if self._is_next_data:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._is_next_data = False

    @property
    def next_data(self) -> str:
        return "".join(self._chunks).strip()


def build_listing_url(
    estate_type: str,
    voivodeship: str,
    *,
    page: int = 1,
    main_url: str = MAIN_URL,
) -> str:
    """Builds a listing URL for a sale search page."""
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")

    base_url = main_url.rstrip("/") + "/"
    path_url = urllib.parse.urljoin(base_url, f"{estate_type}/{voivodeship}")
    query = urllib.parse.urlencode({"viewType": "listing", "page": page})

    return f"{path_url}?{query}"


def extract_next_data_from_html(html_content: str) -> dict[str, Any]:
    """Extracts and parses Next.js data embedded in a page."""
    parser = _NextDataHTMLParser()
    parser.feed(html_content)

    if not parser.next_data:
        raise ValueError("Could not find __NEXT_DATA__ script in response HTML")

    parsed_json = json.loads(unescape(parser.next_data))

    if not isinstance(parsed_json, dict):
        raise ValueError("__NEXT_DATA__ JSON root is not an object")

    return cast(dict[str, Any], parsed_json)


def fetch_next_data_json(
    url: str,
    *,
    headers: Mapping[str, str] = HEADERS,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    retries: int = REQUEST_RETRIES,
    retry_sleep_seconds: float = REQUEST_RETRY_SLEEP_SECONDS,
) -> dict[str, Any]:
    """Fetches JSON data from a listing page."""
    last_error: BaseException | None = None

    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=dict(headers))

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_text = response.read().decode("utf-8", errors="replace")

            stripped_response = response_text.lstrip()

            if stripped_response.startswith("{"):
                parsed_json = json.loads(stripped_response)

                if not isinstance(parsed_json, dict):
                    raise ValueError("JSON response root is not an object")

                return cast(dict[str, Any], parsed_json)

            return extract_next_data_from_html(response_text)

        except urllib.error.HTTPError as exc:
            last_error = exc

            if exc.code == 404:
                raise RuntimeError(f"Could not fetch listing data for {url}") from exc

            logger.warning(
                "Fetching listing data failed on attempt %s/%s for %s: %s",
                attempt,
                retries,
                url,
                exc,
            )

            if attempt < retries:
                time.sleep(retry_sleep_seconds)

        except (
            TimeoutError,
            urllib.error.URLError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            logger.warning(
                "Fetching listing data failed on attempt %s/%s for %s: %s",
                attempt,
                retries,
                url,
                exc,
            )

            if attempt < retries:
                time.sleep(retry_sleep_seconds)

    raise RuntimeError(f"Could not fetch listing data for {url}") from last_error


def extract_listing_items(next_data_json: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extracts listing items from Next.js data."""
    item_paths = (
        ("props", "pageProps", "data", "searchAds", "items"),
        ("props", "pageProps", "searchAds", "items"),
        ("pageProps", "data", "searchAds", "items"),
        ("pageProps", "searchAds", "items"),
        ("data", "searchAds", "items"),
        ("searchAds", "items"),
    )

    for path in item_paths:
        value = _get_nested_value(next_data_json, path)

        if isinstance(value, list):
            return [
                cast(dict[str, Any], item) for item in value if isinstance(item, dict)
            ]

    return []


def extract_estate_detail(next_data_json: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extracts a single listing detail object from Next.js data."""
    detail_paths = (
        ("props", "pageProps", "ad"),
        ("pageProps", "ad"),
        ("ad",),
    )

    for path in detail_paths:
        value = _get_nested_value(next_data_json, path)

        if isinstance(value, dict):
            return cast(dict[str, Any], value)

    return None


def get_estate_info(
    estate_data: Mapping[str, Any],
    estate_type: str | None = None,
    voivodeship: str | None = None,
) -> Estate | None:
    """Extracts relevant details from a single listing item."""
    if not isinstance(estate_data, Mapping):
        return None

    attributes = _extract_attributes(estate_data)
    external_id = _as_text(
        _first_direct_value(
            estate_data,
            ("id", "adId", "estateId", "externalId", "offerId"),
        )
    )
    title = _as_text(_first_direct_value(estate_data, ("title", "name", "headline")))
    slug = _as_text(_first_direct_value(estate_data, ("slug", "urlSlug")))
    url = _build_estate_url(
        _as_text(_first_direct_value(estate_data, ("url", "href", "link"))),
        slug=slug,
        external_id=external_id,
    )

    if external_id is None:
        external_id = _fallback_external_id(url=url, slug=slug, title=title)

    if external_id is None:
        return None

    city = _extract_location_text(
        estate_data,
        direct_keys=("city", "cityName"),
        location_levels=("city_or_village", "city", "town", "village"),
    )
    district = _extract_location_text(
        estate_data,
        direct_keys=("district", "districtName"),
        location_levels=("district",),
    )
    street = _extract_location_text(
        estate_data,
        direct_keys=("street", "streetName"),
        location_levels=("street",),
    )
    location = _extract_location(
        estate_data, city=city, district=district, street=street
    )

    return Estate(
        source=SERVICE_SOURCE,
        external_id=external_id,
        url=url,
        title=title,
        estate_type=estate_type,
        voivodeship=voivodeship,
        price=_extract_number(
            estate_data,
            attributes,
            ("totalPrice", "price", "priceValue", "amount"),
        ),
        price_per_sqm=_extract_number(
            estate_data,
            attributes,
            ("pricePerSquareMeter", "pricePerSqm", "price_per_sqm", "pricePerMeter"),
        ),
        area_sqm=_extract_number(
            estate_data,
            attributes,
            ("areaInSquareMeters", "area", "surface", "area_sqm", "m"),
        ),
        rooms=_extract_rooms(estate_data, attributes),
        location=location,
        city=city,
        district=district,
        street=street,
        market=_extract_text(
            estate_data,
            attributes,
            ("market", "marketType", "market_type", "MarketType"),
        ),
        floor=_extract_floor(estate_data, attributes),
        building_type=_extract_text(
            estate_data,
            attributes,
            (
                "buildingType",
                "building_type",
                "typeOfBuilding",
                "Building_type",
                "building_type",
            ),
        ),
        seller_name=_extract_seller_name(estate_data),
        seller_type=_extract_seller_type(estate_data),
        latitude=_parse_float(_recursive_find_value(estate_data, ("latitude", "lat"))),
        longitude=_parse_float(
            _recursive_find_value(estate_data, ("longitude", "lng", "lon"))
        ),
        images=_extract_images(estate_data),
        attributes=attributes,
    )


def scrape_estates_for(
    estate_type: str,
    voivodeship: str,
    *,
    max_page: int = MAX_PAGE,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids: Iterable[str] = (),
) -> list[Estate]:
    """Scrapes listings for a single estate type and voivodeship."""
    return list(
        iter_estates_for(
            estate_type,
            voivodeship,
            max_page=max_page,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids=existing_external_ids,
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
) -> Iterable[Estate]:
    """Yields listings for a single estate type and voivodeship."""
    if estate_type not in ESTATE_TYPES:
        raise ValueError(f"Unsupported estate type: {estate_type}")

    if voivodeship not in VOIVODESHIPS:
        raise ValueError(f"Unsupported voivodeship: {voivodeship}")

    total_estates_count = 0
    seen_external_ids: set[str] = {
        str(external_id) for external_id in existing_external_ids
    }
    existing_external_ids_count = len(seen_external_ids)
    duplicate_only_page_count = 0
    duplicate_page_stop_threshold = (
        RESUME_DUPLICATE_PAGE_STOP_THRESHOLD if existing_external_ids_count else 1
    )
    logger.info(
        "Streaming scrape started for estate_type=%s voivodeship=%s max_page=%s "
        "existing_ids=%s",
        estate_type,
        voivodeship,
        max_page,
        existing_external_ids_count,
    )

    for page in range(1, max_page + 1):
        listing_url = build_listing_url(estate_type, voivodeship, page=page)
        logger.info(
            "Fetching listing page %s for estate_type=%s voivodeship=%s",
            page,
            estate_type,
            voivodeship,
        )
        next_data_json = fetcher(listing_url)
        listing_items = extract_listing_items(next_data_json)

        if not listing_items:
            logger.info(
                "No listing items found on page %s for estate_type=%s "
                "voivodeship=%s; stopping pagination",
                page,
                estate_type,
                voivodeship,
            )
            break

        page_estates_count = 0
        page_duplicate_count = 0

        for listing_item in listing_items:
            listing_external_id = _extract_listing_external_id(listing_item)

            if (
                listing_external_id is not None
                and listing_external_id in seen_external_ids
            ):
                page_duplicate_count += 1
                continue

            enriched_item = _enrich_listing_item(
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

        if page_estates_count > 0:
            duplicate_only_page_count = 0
            continue

        if page_duplicate_count > 0:
            duplicate_only_page_count += 1

            if duplicate_only_page_count < duplicate_page_stop_threshold:
                logger.info(
                    "Page %s for estate_type=%s voivodeship=%s contained only "
                    "duplicates (%s); continuing resume pagination "
                    "(duplicate_only_pages=%s/%s)",
                    page,
                    estate_type,
                    voivodeship,
                    page_duplicate_count,
                    duplicate_only_page_count,
                    duplicate_page_stop_threshold,
                )
                continue

            logger.warning(
                "Page %s for estate_type=%s voivodeship=%s contained no new "
                "listings (duplicates=%s duplicate_only_pages=%s); stopping "
                "pagination",
                page,
                estate_type,
                voivodeship,
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
        "Streaming scrape finished for estate_type=%s voivodeship=%s total=%s",
        estate_type,
        voivodeship,
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
) -> Iterable[Estate]:
    """Yields listings for all requested estate types and voivodeships."""
    if workers > 1:
        yield from iter_estates_threaded(
            estate_types=estate_types,
            voivodeships=voivodeships,
            max_page=max_page,
            workers=workers,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids_by_voivodeship=existing_external_ids_by_voivodeship,
        )
        return

    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))
    total_estates_count = 0

    logger.info(
        "Streaming scrape started for estate_types=%s voivodeships=%s max_page=%s",
        ", ".join(selected_estate_types),
        ", ".join(selected_voivodeships),
        max_page,
    )

    for estate_type in selected_estate_types:
        for voivodeship in selected_voivodeships:
            for estate in iter_estates_for(
                estate_type,
                voivodeship,
                max_page=max_page,
                fetcher=fetcher,
                detail_fetcher=detail_fetcher,
                existing_external_ids=(
                    existing_external_ids_by_voivodeship or {}
                ).get(voivodeship, ()),
            ):
                total_estates_count += 1
                yield estate

    logger.info(
        "Streaming scrape finished for all filters total=%s", total_estates_count
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
) -> Iterable[Estate]:
    """Yields listings using worker threads split by filter combinations."""
    if workers < 1:
        raise ValueError("workers must be greater than or equal to 1")

    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))
    scrape_targets = tuple(
        (estate_type, voivodeship)
        for estate_type in selected_estate_types
        for voivodeship in selected_voivodeships
    )

    if not scrape_targets:
        return

    max_workers = min(workers, len(scrape_targets))
    output_queue: queue.Queue[Estate | _WorkerFinished] = queue.Queue(
        maxsize=max_workers * 100
    )
    total_estates_count = 0

    logger.info(
        "Threaded streaming scrape started: estate_types=%s voivodeships=%s "
        "max_page=%s workers=%s active_workers=%s",
        ", ".join(selected_estate_types),
        ", ".join(selected_voivodeships),
        max_page,
        workers,
        max_workers,
    )

    def scrape_target(estate_type: str, voivodeship: str) -> int:
        count = 0

        try:
            for estate in iter_estates_for(
                estate_type,
                voivodeship,
                max_page=max_page,
                fetcher=fetcher,
                detail_fetcher=detail_fetcher,
                existing_external_ids=(
                    existing_external_ids_by_voivodeship or {}
                ).get(voivodeship, ()),
            ):
                output_queue.put(estate)
                count += 1

        except Exception as exc:
            output_queue.put(
                _WorkerFinished(
                    estate_type=estate_type,
                    voivodeship=voivodeship,
                    count=count,
                    error=exc,
                )
            )
            raise

        output_queue.put(
            _WorkerFinished(
                estate_type=estate_type,
                voivodeship=voivodeship,
                count=count,
            )
        )
        return count

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="estate-scraper",
    ) as executor:
        futures = [
            executor.submit(scrape_target, estate_type, voivodeship)
            for estate_type, voivodeship in scrape_targets
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
                            "Threaded scrape failed for estate_type=%s "
                            "voivodeship=%s after %s records: %s",
                            item.estate_type,
                            item.voivodeship,
                            item.count,
                            item.error,
                        )
                        raise RuntimeError(
                            "Threaded scrape failed for "
                            f"estate_type={item.estate_type} "
                            f"voivodeship={item.voivodeship}"
                        ) from item.error

                    logger.info(
                        "Threaded scrape worker finished for estate_type=%s "
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
        "Threaded streaming scrape finished for all filters total=%s",
        total_estates_count,
    )


def scrape_estates(
    *,
    estate_types: Iterable[str] = ESTATE_TYPES,
    voivodeships: Iterable[str] = VOIVODESHIPS,
    max_page: int = MAX_PAGE,
    workers: int = 1,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_next_data_json,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None = fetch_next_data_json,
    existing_external_ids_by_voivodeship: Mapping[str, Iterable[str]] | None = None,
) -> list[Estate]:
    """Scrapes listings for all requested estate types and voivodeships."""
    selected_estate_types = tuple(sorted(estate_types))
    selected_voivodeships = tuple(sorted(voivodeships))

    logger.info(
        "Scraping started for estate_types=%s voivodeships=%s max_page=%s workers=%s",
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
        )
    )

    logger.info("Scraping finished for all filters total=%s", len(estates))

    return estates


def _enrich_listing_item(
    listing_item: Mapping[str, Any],
    *,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None,
) -> Mapping[str, Any]:
    if detail_fetcher is None:
        return listing_item

    listing_url = _build_estate_url(
        _as_text(_first_direct_value(listing_item, ("url", "href", "link"))),
        slug=_as_text(_first_direct_value(listing_item, ("slug", "urlSlug"))),
        external_id=_as_text(
            _first_direct_value(
                listing_item,
                ("id", "adId", "estateId", "externalId", "offerId"),
            )
        ),
    )

    if listing_url is None:
        return listing_item

    try:
        detail_json = detail_fetcher(listing_url)
        detail_item = extract_estate_detail(detail_json)

    except RuntimeError as exc:
        logger.debug("Fetching listing detail failed for %s: %s", listing_url, exc)
        return listing_item

    if detail_item is None:
        logger.warning(
            "Listing detail did not contain a detail object for %s", listing_url
        )
        return listing_item

    return _merge_listing_with_detail(listing_item, detail_item)


def _merge_listing_with_detail(
    listing_item: Mapping[str, Any],
    detail_item: Mapping[str, Any],
) -> dict[str, Any]:
    merged_item = dict(listing_item)
    merged_item.update(detail_item)

    for key in ("href", "url", "link"):
        if key in listing_item and key not in merged_item:
            merged_item[key] = listing_item[key]

    return merged_item


def _extract_listing_external_id(listing_item: Mapping[str, Any]) -> str | None:
    return _as_text(
        _first_direct_value(
            listing_item,
            ("id", "adId", "estateId", "externalId", "offerId"),
        )
    )


def _get_nested_value(data: Mapping[str, Any], path: Sequence[str]) -> Any:
    current_value: Any = data

    for key in path:
        if not isinstance(current_value, Mapping):
            return None

        current_value = current_value.get(key)

    return current_value


def _first_found_value(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    direct_value = _first_direct_value(data, keys)

    if direct_value is not None:
        return direct_value

    return _recursive_find_value(data, keys)


def _first_direct_value(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in data:
            return data[key]

    return None


def _recursive_find_value(data: Any, keys: Sequence[str]) -> Any:
    key_set = set(keys)

    if isinstance(data, Mapping):
        for key, value in data.items():
            if key in key_set:
                return value

        for value in data.values():
            nested_value = _recursive_find_value(value, keys)

            if nested_value is not None:
                return nested_value

    if isinstance(data, list):
        for item in data:
            nested_value = _recursive_find_value(item, keys)

            if nested_value is not None:
                return nested_value

    return None


def _extract_attributes(estate_data: Mapping[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}

    for key in (
        "attributes",
        "characteristics",
        "params",
        "properties",
        "features",
        "featuresByCategory",
        "featuresWithoutCategory",
        "additionalInformation",
        "target",
    ):
        value = estate_data.get(key)

        if value is not None:
            _merge_attributes(attributes, value)

    return attributes


def _merge_attributes(attributes: dict[str, Any], value: Any) -> None:
    if isinstance(value, Mapping):
        attribute_key = _as_text(
            _first_existing_key(value, ("key", "name", "label", "code"))
        )

        if attribute_key is not None:
            attribute_value = _first_existing_key(
                value,
                ("value", "values", "displayValue", "localizedValue"),
            )
            attributes[attribute_key] = attribute_value
            return

        category_label = _as_text(value.get("label"))
        category_values = value.get("values")

        if category_label is not None and category_values is not None:
            attributes[category_label] = category_values
            return

        for nested_key, nested_value in value.items():
            if isinstance(nested_key, str):
                attributes[nested_key] = nested_value

        return

    if isinstance(value, list):
        for item in value:
            _merge_attributes(attributes, item)


def _first_existing_key(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in data:
            return data[key]

    return None


def _extract_number(
    estate_data: Mapping[str, Any],
    attributes: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    raw_value = _first_found_value(estate_data, keys)

    if raw_value is None:
        raw_value = _find_attribute_value(attributes, keys)

    return _parse_float(raw_value)


def _extract_text(
    estate_data: Mapping[str, Any],
    attributes: Mapping[str, Any],
    keys: Sequence[str],
) -> str | None:
    raw_value = _first_found_value(estate_data, keys)

    if raw_value is None:
        raw_value = _find_attribute_value(attributes, keys)

    return _as_text(raw_value)


def _extract_seller_name(estate_data: Mapping[str, Any]) -> str | None:
    for container_key in ("contactDetails", "agency", "owner", "advertOwner"):
        container_value = estate_data.get(container_key)

        if isinstance(container_value, Mapping):
            seller_name = _as_text(container_value.get("name"))

            if seller_name is not None:
                return seller_name

    return _as_text(
        _first_found_value(
            estate_data,
            ("sellerName", "advertiserName", "agencyName", "ownerName"),
        )
    )


def _extract_seller_type(estate_data: Mapping[str, Any]) -> str | None:
    for container_key in ("contactDetails", "agency", "owner", "advertOwner"):
        container_value = estate_data.get(container_key)

        if isinstance(container_value, Mapping):
            seller_type = _as_text(container_value.get("type"))

            if seller_type is not None:
                return seller_type

    return _as_text(
        _first_found_value(
            estate_data,
            ("sellerType", "advertiserType", "ownerType", "advertType"),
        )
    )


def _extract_location_text(
    estate_data: Mapping[str, Any],
    *,
    direct_keys: Sequence[str],
    location_levels: Sequence[str],
) -> str | None:
    direct_value = _as_text(_recursive_find_value(estate_data, direct_keys))

    if direct_value is not None:
        return direct_value

    return _extract_location_level_name(estate_data, location_levels)


def _extract_location_level_name(
    estate_data: Mapping[str, Any],
    location_levels: Sequence[str],
) -> str | None:
    locations = _recursive_find_value(estate_data, ("locations",))

    if not isinstance(locations, list):
        return None

    allowed_levels = set(location_levels)

    for location in locations:
        if not isinstance(location, Mapping):
            continue

        location_level = _as_text(location.get("locationLevel"))

        if location_level in allowed_levels:
            return _as_text(location.get("name")) or _as_text(location.get("fullName"))

    return None


def _find_attribute_value(attributes: Mapping[str, Any], keys: Sequence[str]) -> Any:
    normalized_keys = {_normalize_attribute_key(key) for key in keys}

    for key, value in attributes.items():
        normalized_key = _normalize_attribute_key(key)

        if normalized_key in normalized_keys:
            return value

        for wanted_key in normalized_keys:
            if normalized_key.endswith(wanted_key) or wanted_key.endswith(
                normalized_key
            ):
                return value

    return None


def _normalize_attribute_key(key: str) -> str:
    return key.replace("_", "").replace("-", "").replace(" ", "").lower()


def _extract_rooms(
    estate_data: Mapping[str, Any],
    attributes: Mapping[str, Any],
) -> int | None:
    raw_value = _first_found_value(
        estate_data,
        ("roomsNumber", "rooms_num", "rooms", "numberOfRooms"),
    )

    if raw_value is None:
        raw_value = _find_attribute_value(
            attributes,
            ("roomsNumber", "rooms_num", "rooms", "numberOfRooms"),
        )

    text_value = _as_text(raw_value)

    if text_value is not None:
        mapped_value = ROOMS_NUM_MAP.get(text_value.upper())

        if mapped_value is not None:
            return mapped_value

    parsed_value = _parse_float(raw_value)

    if parsed_value is None:
        return None

    return int(parsed_value)


def _extract_floor(
    estate_data: Mapping[str, Any],
    attributes: Mapping[str, Any],
) -> int | None:
    raw_value = _first_found_value(estate_data, ("floor", "floorNumber"))

    if raw_value is None:
        raw_value = _find_attribute_value(attributes, ("floor", "floorNumber"))

    text_value = _as_text(raw_value)

    if text_value is not None:
        mapped_value = FLOOR_MAP.get(text_value.upper())

        if mapped_value is not None:
            return mapped_value

    parsed_value = _parse_float(raw_value)

    if parsed_value is None:
        return None

    return int(parsed_value)


def _parse_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, Mapping):
        nested_value = _first_existing_key(
            value,
            ("value", "amount", "number", "displayValue"),
        )
        return _parse_float(nested_value)

    if isinstance(value, list) and value:
        return _parse_float(value[0])

    if not isinstance(value, str):
        return None

    match = NUMBER_RE.search(value)

    if match is None:
        return None

    normalized_number = match.group(0).replace(" ", "").replace("\u00a0", "")
    normalized_number = normalized_number.replace(",", ".")

    return float(normalized_number)


def _extract_location(
    estate_data: Mapping[str, Any],
    *,
    city: str | None,
    district: str | None,
    street: str | None,
) -> str | None:
    location_value = _first_found_value(estate_data, ("location", "address"))
    location_text = _as_text(location_value)

    if location_text is not None:
        return location_text

    return (
        ", ".join(
            part for part in (street, district, city) if part is not None and part != ""
        )
        or None
    )


def _extract_images(estate_data: Mapping[str, Any]) -> list[str]:
    images_value = _first_found_value(estate_data, ("images", "photos", "pictures"))
    image_urls: list[str] = []

    _collect_image_urls(images_value, image_urls)

    return list(dict.fromkeys(image_urls))


def _collect_image_urls(value: Any, image_urls: list[str]) -> None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            image_urls.append(value)

        return

    if isinstance(value, Mapping):
        for key in ("url", "href", "src", "large", "medium", "thumbnail"):
            nested_value = value.get(key)

            if nested_value is not None:
                _collect_image_urls(nested_value, image_urls)

        for nested_value in value.values():
            if isinstance(nested_value, (list, dict)):
                _collect_image_urls(nested_value, image_urls)

        return

    if isinstance(value, list):
        for item in value:
            _collect_image_urls(item, image_urls)


def _build_estate_url(
    url: str | None,
    *,
    slug: str | None,
    external_id: str | None,
) -> str | None:
    raw_url = url or slug or external_id

    if raw_url is None:
        return None

    if raw_url.startswith(("http://", "https://")):
        return _normalize_estate_url(raw_url)

    if raw_url.startswith("/"):
        return _normalize_estate_url(
            urllib.parse.urljoin(_url_origin(ESTATE_URL), raw_url)
        )

    if raw_url.startswith("pl/"):
        return _normalize_estate_url(
            urllib.parse.urljoin(_url_origin(ESTATE_URL).rstrip("/") + "/", raw_url)
        )

    return _normalize_estate_url(
        urllib.parse.urljoin(ESTATE_URL.rstrip("/") + "/", raw_url)
    )


def _normalize_estate_url(url: str) -> str:
    normalized_url = url.replace("[lang]/ad/", "")
    normalized_url = normalized_url.replace("/ad/", "/")
    parsed_url = urllib.parse.urlsplit(normalized_url)
    base_path = urllib.parse.urlsplit(ESTATE_URL).path.strip("/")
    path_parts = [part for part in parsed_url.path.strip("/").split("/") if part]
    base_parts = [part for part in base_path.split("/") if part]

    if path_parts[: len(base_parts)] == base_parts:
        slug_parts = path_parts[len(base_parts) :]

        if len(slug_parts) > 1:
            normalized_path = "/" + "/".join([*base_parts, slug_parts[-1]])
            normalized_url = urllib.parse.urlunsplit(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    normalized_path,
                    parsed_url.query,
                    parsed_url.fragment,
                )
            )

    return normalized_url


def _url_origin(url: str) -> str:
    parsed_url = urllib.parse.urlsplit(url)

    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError("Configured URL must include scheme and host")

    return urllib.parse.urlunsplit((parsed_url.scheme, parsed_url.netloc, "", "", ""))


def _fallback_external_id(
    *,
    url: str | None,
    slug: str | None,
    title: str | None,
) -> str | None:
    for value in (url, slug, title):
        text_value = _as_text(value)

        if text_value:
            return text_value.rstrip("/").rsplit("/", maxsplit=1)[-1]

    return None


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (str, int, float)):
        text_value = str(value).strip()

        if text_value:
            return text_value

    if isinstance(value, list) and value:
        return _as_text(value[0])

    if isinstance(value, Mapping):
        for key in ("name", "fullName", "displayName", "value", "label"):
            nested_text_value = _as_text(value.get(key))

            if nested_text_value is not None:
                return nested_text_value

    return None


if __name__ == "__main__":
    scraped_estates = scrape_estates()
    logger.info("Scraped %s estates", len(scraped_estates))
