"""Logger factory helpers with optional console colors and file logging."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path


class ColorFormatter(logging.Formatter):
    """Formatter that colorizes log level names for console output."""

    COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }

    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with a colorized level name.

        Args:
            record: Log record to format.

        Returns:
            Formatted log line.
        """
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


@dataclass(frozen=True)
class DefaultFormat:
    """Default log message and date format constants."""

    DEFAULT_MSG_FORMAT = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )

    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LoggerFactory:
    """Factory for consistently configured application loggers."""

    @classmethod
    def get_logger(
        cls,
        name: str,
        *,
        level: int | str = logging.INFO,
        use_colors: bool = True,
        log_to_file: bool = True,
        log_file: str | Path = "logs/app.log",
        propagate: bool = False,
    ) -> logging.Logger:
        """Return a configured logger for the given name.

        Args:
            name: Logger name.
            level: Logging level name or numeric value.
            use_colors: Whether console output should colorize level names.
            log_to_file: Whether to add a file handler.
            log_file: File path used when ``log_to_file`` is enabled.
            propagate: Whether the logger should propagate to parent loggers.

        Returns:
            Configured logger.
        """
        logger = logging.getLogger(name)
        logger.setLevel(cls._parse_level(level))
        logger.propagate = propagate

        if cls._is_configured(logger):
            return logger

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(cls._parse_level(level))
        console_handler.setFormatter(cls._get_formatter(use_colors=use_colors))

        logger.addHandler(console_handler)

        if log_to_file:
            file_handler = cls._create_file_handler(
                log_file=log_file,
                level=level,
            )
            logger.addHandler(file_handler)

        logger._custom_logger_configured = True  # type: ignore[attr-defined]

        return logger

    @classmethod
    def _get_formatter(cls, *, use_colors: bool) -> logging.Formatter:
        formatter_class = ColorFormatter if use_colors else logging.Formatter

        return formatter_class(
            fmt=DefaultFormat.DEFAULT_MSG_FORMAT,
            datefmt=DefaultFormat.DEFAULT_DATE_FORMAT,
        )

    @classmethod
    def _create_file_handler(
        cls,
        *,
        log_file: str | Path,
        level: int | str,
    ) -> logging.FileHandler:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(cls._parse_level(level))
        file_handler.setFormatter(
            logging.Formatter(
                fmt=DefaultFormat.DEFAULT_MSG_FORMAT,
                datefmt=DefaultFormat.DEFAULT_DATE_FORMAT,
            )
        )

        return file_handler

    @staticmethod
    def _parse_level(level: int | str) -> int:
        if isinstance(level, int):
            return level

        parsed_level = logging.getLevelName(level.upper())

        if isinstance(parsed_level, int):
            return parsed_level

        raise ValueError(
            f"Invalid logging level: {level!r}. "
            "Use e.g. 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'."
        )

    @staticmethod
    def _is_configured(logger: logging.Logger) -> bool:
        return bool(getattr(logger, "_custom_logger_configured", False))


def get_logger(
    name: str,
    *,
    level: int | str = logging.INFO,
    use_colors: bool = True,
    log_to_file: bool = False,
    log_file: str | Path = "logs/app.log",
    propagate: bool = False,
) -> logging.Logger:
    """Return a configured application logger.

    Args:
        name: Logger name.
        level: Logging level name or numeric value.
        use_colors: Whether console output should colorize level names.
        log_to_file: Whether to add a file handler.
        log_file: File path used when ``log_to_file`` is enabled.
        propagate: Whether the logger should propagate to parent loggers.

    Returns:
        Configured logger.
    """
    return LoggerFactory.get_logger(
        name=name,
        level=level,
        use_colors=use_colors,
        log_to_file=log_to_file,
        log_file=log_file,
        propagate=propagate,
    )
