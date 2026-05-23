"""HTTP and Next.js transport helpers for real estate ingestion."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from threading import Lock
from typing import Any, cast

from src.config.globals import (
    HEADERS,
    MAIN_URL,
    REQUEST_BLOCK_BACKOFF_MULTIPLIER,
    REQUEST_BLOCK_COOLDOWN_MAX_SECONDS,
    REQUEST_BLOCK_COOLDOWN_SECONDS,
    REQUEST_BLOCK_JITTER_SECONDS,
    REQUEST_BLOCK_RETRIES,
    REQUEST_BLOCK_STATUS_CODES,
    REQUEST_RETRIES,
    REQUEST_RETRY_BACKOFF_MULTIPLIER,
    REQUEST_RETRY_MAX_SLEEP_SECONDS,
    REQUEST_RETRY_SLEEP_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from src.config.source_config import SourceDefinition
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SourceBlockedError(RuntimeError):
    """Raised when source anti-abuse responses outlast configured cooldowns."""

    def __init__(
        self,
        url: str,
        *,
        status_code: int,
        attempts: int,
    ) -> None:
        super().__init__(
            f"Source returned HTTP {status_code} for {url} after {attempts} "
            "cooldown attempts"
        )
        self.url = url
        self.status_code = status_code
        self.attempts = attempts


class RequestThrottle:
    """Shared cooldown gate used by concurrent request workers."""

    def __init__(self, *, rate_limit_seconds: float = 0.0) -> None:
        self._lock = Lock()
        self._blocked_until = 0.0
        self._next_allowed_at = 0.0
        self._rate_limit_seconds = max(0.0, rate_limit_seconds)

    def wait_if_needed(self) -> None:
        """Sleep while a source-wide cooldown is active."""
        while True:
            with self._lock:
                sleep_seconds = self._blocked_until - time.monotonic()

            if sleep_seconds <= 0:
                break

            logger.warning(
                "Source cooldown active; sleeping %.1f seconds before next request",
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

        if self._rate_limit_seconds <= 0:
            return

        while True:
            with self._lock:
                now = time.monotonic()
                sleep_seconds = self._next_allowed_at - now

                if sleep_seconds <= 0:
                    self._next_allowed_at = now + self._rate_limit_seconds
                    return

            time.sleep(sleep_seconds)

    def register_block(self, cooldown_seconds: float) -> None:
        """Extend the shared cooldown window."""
        if cooldown_seconds <= 0:
            return

        with self._lock:
            self._blocked_until = max(
                self._blocked_until,
                time.monotonic() + cooldown_seconds,
            )


DEFAULT_REQUEST_THROTTLE = RequestThrottle()


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
    query_params: Mapping[str, str] | None = None,
    source: SourceDefinition | None = None,
) -> str:
    """Build a listing URL for a sale search page.

    Args:
        estate_type: Listing type slug.
        voivodeship: Voivodeship slug.
        page: One-based listing page number.
        main_url: Base listing search URL.
        query_params: Additional search filter query parameters.

    Returns:
        Fully qualified listing URL.

    Raises:
        ValueError: If ``page`` is lower than one.
    """
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")

    if source is not None:
        path_url = source.search_url_template.format(
            page=page,
            estate_type=estate_type,
            property_type=estate_type,
            voivodeship=voivodeship,
            source_id=source.source_id,
        )
        return _append_query_params(path_url, query_params)

    base_url = main_url.rstrip("/") + "/"
    path_url = urllib.parse.urljoin(base_url, f"{estate_type}/{voivodeship}")
    query_values = {
        "viewType": "listing",
        "page": str(page),
        **dict(query_params or {}),
    }
    query = urllib.parse.urlencode(query_values)

    return f"{path_url}?{query}"


def _append_query_params(
    url: str,
    query_params: Mapping[str, str] | None,
) -> str:
    if not query_params:
        return url

    parsed_url = urllib.parse.urlsplit(url)
    existing_query_values = urllib.parse.parse_qsl(
        parsed_url.query,
        keep_blank_values=True,
    )
    query = urllib.parse.urlencode([*existing_query_values, *query_params.items()])

    return urllib.parse.urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            query,
            parsed_url.fragment,
        )
    )


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
    retry_backoff_multiplier: float = REQUEST_RETRY_BACKOFF_MULTIPLIER,
    retry_max_sleep_seconds: float = REQUEST_RETRY_MAX_SLEEP_SECONDS,
    block_status_codes: frozenset[int] = REQUEST_BLOCK_STATUS_CODES,
    block_retries: int = REQUEST_BLOCK_RETRIES,
    block_cooldown_seconds: float = REQUEST_BLOCK_COOLDOWN_SECONDS,
    block_cooldown_max_seconds: float = REQUEST_BLOCK_COOLDOWN_MAX_SECONDS,
    block_backoff_multiplier: float = REQUEST_BLOCK_BACKOFF_MULTIPLIER,
    block_jitter_seconds: float = REQUEST_BLOCK_JITTER_SECONDS,
    throttle: RequestThrottle | None = DEFAULT_REQUEST_THROTTLE,
) -> dict[str, Any]:
    """Fetch JSON or embedded Next.js data from a page.

    Args:
        url: Page URL to request.
        headers: HTTP request headers.
        timeout_seconds: Socket timeout in seconds.
        retries: Number of request attempts.
        retry_sleep_seconds: Delay between failed attempts.
        retry_backoff_multiplier: Exponential backoff multiplier for retries.
        retry_max_sleep_seconds: Maximum delay between failed attempts.
        block_status_codes: HTTP status codes treated as source throttling.
        block_retries: Number of cooldown attempts allowed for source blocks.
        block_cooldown_seconds: Initial cooldown for source block responses.
        block_cooldown_max_seconds: Maximum cooldown after backoff.
        block_backoff_multiplier: Multiplier used between block cooldowns.
        block_jitter_seconds: Random jitter added to block cooldowns.
        throttle: Optional shared throttle used across concurrent workers.

    Returns:
        Parsed JSON object from the response.

    Raises:
        RuntimeError: If all request attempts fail.
    """
    last_error: BaseException | None = None
    attempt = 0
    block_attempt = 0

    while attempt < retries:
        if throttle is not None:
            throttle.wait_if_needed()

        attempt += 1
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

            if exc.code in block_status_codes:
                block_attempt += 1

                if block_attempt > block_retries:
                    raise SourceBlockedError(
                        url,
                        status_code=exc.code,
                        attempts=block_attempt - 1,
                    ) from exc

                cooldown_seconds = _block_cooldown_seconds(
                    exc,
                    attempt=block_attempt,
                    base_seconds=block_cooldown_seconds,
                    max_seconds=block_cooldown_max_seconds,
                    multiplier=block_backoff_multiplier,
                    jitter_seconds=block_jitter_seconds,
                )
                logger.warning(
                    "Source returned HTTP %s for %s; cooldown %.1f seconds "
                    "before retrying blocked request (%s/%s)",
                    exc.code,
                    url,
                    cooldown_seconds,
                    block_attempt,
                    block_retries,
                )

                if throttle is None:
                    time.sleep(cooldown_seconds)

                else:
                    throttle.register_block(cooldown_seconds)
                    throttle.wait_if_needed()

                attempt = 0
                continue

            logger.warning(
                "Fetching listing data failed on attempt %s/%s for %s: %s",
                attempt,
                retries,
                url,
                exc,
            )

            if attempt < retries:
                time.sleep(
                    _retry_sleep_seconds(
                        attempt=attempt,
                        base_seconds=retry_sleep_seconds,
                        backoff_multiplier=retry_backoff_multiplier,
                        max_seconds=retry_max_sleep_seconds,
                    )
                )

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
                time.sleep(
                    _retry_sleep_seconds(
                        attempt=attempt,
                        base_seconds=retry_sleep_seconds,
                        backoff_multiplier=retry_backoff_multiplier,
                        max_seconds=retry_max_sleep_seconds,
                    )
                )

    raise RuntimeError(f"Could not fetch listing data for {url}") from last_error


def _block_cooldown_seconds(
    exc: urllib.error.HTTPError,
    *,
    attempt: int,
    base_seconds: float,
    max_seconds: float,
    multiplier: float,
    jitter_seconds: float,
) -> float:
    retry_after_seconds = _retry_after_seconds(exc)

    if retry_after_seconds is not None:
        cooldown_seconds = retry_after_seconds

    else:
        cooldown_seconds = base_seconds * (multiplier ** max(attempt - 1, 0))

    if jitter_seconds > 0:
        cooldown_seconds += random.uniform(0, jitter_seconds)

    return max(0.0, min(cooldown_seconds, max_seconds))


def _retry_sleep_seconds(
    *,
    attempt: int,
    base_seconds: float,
    backoff_multiplier: float,
    max_seconds: float,
) -> float:
    if base_seconds <= 0:
        return 0.0

    multiplier = max(1.0, backoff_multiplier)
    sleep_seconds = base_seconds * (multiplier ** max(attempt - 1, 0))
    return max(0.0, min(sleep_seconds, max_seconds))


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    retry_after = exc.headers.get("Retry-After")

    if retry_after is None:
        return None

    try:
        return max(0.0, float(retry_after))

    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(retry_after)

    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)

    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
