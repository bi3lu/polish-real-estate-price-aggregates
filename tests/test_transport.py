"""Tests for HTTP transport retry and cooldown behavior."""

from __future__ import annotations

import urllib.error
import urllib.request
from email.message import Message

import pytest

from src.ingestion.transport import SourceBlockedError, fetch_next_data_json


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def test_fetch_next_data_json_cools_down_and_retries_after_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    responses: list[BaseException | _Response] = [
        _http_error(403),
        _Response('{"ok": true}'),
    ]

    def urlopen(
        request: urllib.request.Request,
        *,
        timeout: int,
    ) -> _Response:
        response = responses.pop(0)

        if isinstance(response, BaseException):
            raise response

        return response

    monkeypatch.setattr("src.ingestion.transport.urllib.request.urlopen", urlopen)
    monkeypatch.setattr(
        "src.ingestion.transport.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    payload = fetch_next_data_json(
        "https://example.invalid/listing",
        retries=1,
        block_retries=1,
        block_cooldown_seconds=2,
        block_cooldown_max_seconds=10,
        block_jitter_seconds=0,
        throttle=None,
    )

    assert payload == {"ok": True}
    assert sleeps == [2]


def test_fetch_next_data_json_honors_retry_after_for_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    responses: list[BaseException | _Response] = [
        _http_error(429, headers={"Retry-After": "7"}),
        _Response('{"ok": true}'),
    ]

    def urlopen(
        request: urllib.request.Request,
        *,
        timeout: int,
    ) -> _Response:
        response = responses.pop(0)

        if isinstance(response, BaseException):
            raise response

        return response

    monkeypatch.setattr("src.ingestion.transport.urllib.request.urlopen", urlopen)
    monkeypatch.setattr(
        "src.ingestion.transport.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    payload = fetch_next_data_json(
        "https://example.invalid/listing",
        retries=1,
        block_retries=1,
        block_cooldown_seconds=2,
        block_cooldown_max_seconds=10,
        block_jitter_seconds=0,
        throttle=None,
    )

    assert payload == {"ok": True}
    assert sleeps == [7]


def test_fetch_next_data_json_raises_after_block_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def urlopen(
        request: urllib.request.Request,
        *,
        timeout: int,
    ) -> _Response:
        nonlocal calls
        calls += 1
        raise _http_error(403)

    monkeypatch.setattr("src.ingestion.transport.urllib.request.urlopen", urlopen)

    with pytest.raises(SourceBlockedError) as exc_info:
        fetch_next_data_json(
            "https://example.invalid/listing",
            retries=1,
            block_retries=2,
            block_cooldown_seconds=0,
            block_cooldown_max_seconds=0,
            block_jitter_seconds=0,
            throttle=None,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.attempts == 2
    assert calls == 3


def _http_error(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
) -> urllib.error.HTTPError:
    message = Message()

    for key, value in (headers or {}).items():
        message[key] = value

    return urllib.error.HTTPError(
        "https://example.invalid/listing",
        status_code,
        "blocked",
        message,
        None,
    )
