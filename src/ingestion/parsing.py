"""Payload parsing and raw listing model extraction for ingestion."""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from src.config.globals import (
    DEFAULT_SOURCE_ID,
    ESTATE_URL,
    FLOOR_MAP,
    NUMBER_RE,
    ROOMS_NUM_MAP,
)
from src.ingestion.models import RawListingObservation
from src.utils.logger import get_logger

logger = get_logger(__name__)


def extract_listing_items(next_data_json: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract listing item objects from known Next.js response shapes.

    Args:
        next_data_json: Parsed Next.js JSON payload.

    Returns:
        Listing item dictionaries, or an empty list when no supported path exists.
    """
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

    return _find_listing_items_recursively(next_data_json)


def _find_listing_items_recursively(data: Any) -> list[dict[str, Any]]:
    candidate_lists: list[list[dict[str, Any]]] = []

    def collect(value: Any, *, parent_key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                collect(nested_value, parent_key=str(key))

            return

        if isinstance(value, list):
            listing_items = [
                cast(dict[str, Any], item)
                for item in value
                if isinstance(item, dict) and _looks_like_listing_item(item)
            ]

            if listing_items and parent_key in {"items", "ads", "results"}:
                candidate_lists.append(listing_items)

            for item in value:
                collect(item, parent_key=parent_key)

    collect(data)

    if not candidate_lists:
        return []

    return max(candidate_lists, key=len)


def _looks_like_listing_item(item: Mapping[str, Any]) -> bool:
    has_identifier = any(
        key in item for key in ("id", "adId", "estateId", "externalId", "offerId")
    )
    has_listing_field = any(
        key in item
        for key in (
            "title",
            "name",
            "headline",
            "href",
            "url",
            "link",
            "slug",
            "urlSlug",
        )
    )

    return has_identifier and has_listing_field


def extract_estate_detail(next_data_json: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract a single listing detail object from known Next.js response shapes.

    Args:
        next_data_json: Parsed listing detail JSON payload.

    Returns:
        Detail object when present, otherwise ``None``.
    """
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
    *,
    source_id: str = DEFAULT_SOURCE_ID,
    detail_base_url: str = ESTATE_URL,
) -> RawListingObservation | None:
    """Extract normalized estate details from a listing payload.

    Args:
        estate_data: Raw listing or detail payload.
        estate_type: Optional estate type assigned from the ingestion target.
        voivodeship: Optional voivodeship assigned from the ingestion target.

    Returns:
        Raw listing model, or ``None`` when no stable external id can be derived.
    """
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
        detail_base_url=detail_base_url,
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

    return RawListingObservation(
        source_id=source_id,
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


def enrich_listing_item(
    listing_item: Mapping[str, Any],
    *,
    detail_fetcher: Callable[[str], Mapping[str, Any]] | None,
    detail_base_url: str = ESTATE_URL,
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
        detail_base_url=detail_base_url,
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


def extract_listing_external_id(listing_item: Mapping[str, Any]) -> str | None:
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
    detail_base_url: str = ESTATE_URL,
) -> str | None:
    raw_url = url or slug or external_id

    if raw_url is None:
        return None

    if raw_url.startswith(("http://", "https://")):
        return _normalize_estate_url(raw_url, detail_base_url=detail_base_url)

    if raw_url.startswith("/"):
        return _normalize_estate_url(
            urllib.parse.urljoin(_url_origin(detail_base_url), raw_url),
            detail_base_url=detail_base_url,
        )

    if raw_url.startswith("pl/"):
        return _normalize_estate_url(
            urllib.parse.urljoin(
                _url_origin(detail_base_url).rstrip("/") + "/",
                raw_url,
            ),
            detail_base_url=detail_base_url,
        )

    return _normalize_estate_url(
        urllib.parse.urljoin(detail_base_url.rstrip("/") + "/", raw_url),
        detail_base_url=detail_base_url,
    )


def _normalize_estate_url(url: str, *, detail_base_url: str = ESTATE_URL) -> str:
    normalized_url = url.replace("[lang]/ad/", "")
    normalized_url = normalized_url.replace("/ad/", "/")
    parsed_url = urllib.parse.urlsplit(normalized_url)
    base_path = urllib.parse.urlsplit(detail_base_url).path.strip("/")
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
