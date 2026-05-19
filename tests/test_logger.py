"""Tests for application logger configuration."""

from __future__ import annotations

import logging

from src.utils.logger import get_logger


def test_get_logger_returns_configured_logger() -> None:
    logger = get_logger(
        "test_logger",
        level="DEBUG",
        log_to_file=False,
        propagate=False,
    )

    assert logger.level == logging.DEBUG
    assert logger.propagate is False
    assert logger.handlers
