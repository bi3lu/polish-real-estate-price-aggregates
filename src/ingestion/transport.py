"""HTTP and Next.js transport helpers for real estate ingestion."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from html import unescape
from html.parser import HTMLParser
from typing import Any, cast

from src.config.globals import (
    HEADERS,
    MAIN_URL,
    REQUEST_RETRIES,
    REQUEST_RETRY_SLEEP_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class _NextDataHTMLParser(HTMLParser):
    """HTML parser that extracts the Next.js ``__NEXT_DATA__`` script body."""

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
    """Build a listing URL for a sale search page.

    Args:
        estate_type: Listing type slug.
        voivodeship: Voivodeship slug.
        page: One-based listing page number.
        main_url: Base listing search URL.

    Returns:
        Fully qualified listing URL.

    Raises:
        ValueError: If ``page`` is lower than one.
    """
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")

    base_url = main_url.rstrip("/") + "/"
    path_url = urllib.parse.urljoin(base_url, f"{estate_type}/{voivodeship}")
    query = urllib.parse.urlencode({"viewType": "listing", "page": page})

    return f"{path_url}?{query}"


def extract_next_data_from_html(html_content: str) -> dict[str, Any]:
    """Extract and parse Next.js data embedded in an HTML page.

    Args:
        html_content: HTML response body.

    Returns:
        Parsed ``__NEXT_DATA__`` JSON object.

    Raises:
        ValueError: If the script is missing or the JSON root is not an object.
        json.JSONDecodeError: If the embedded JSON cannot be parsed.
    """
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
    """Fetch JSON or embedded Next.js data from a page.

    Args:
        url: Page URL to request.
        headers: HTTP request headers.
        timeout_seconds: Socket timeout in seconds.
        retries: Number of request attempts.
        retry_sleep_seconds: Delay between failed attempts.

    Returns:
        Parsed JSON object from the response.

    Raises:
        RuntimeError: If all request attempts fail.
    """
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
