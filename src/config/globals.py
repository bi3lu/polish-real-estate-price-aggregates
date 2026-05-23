"""Global variables and constants for the project."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from src.config.env import PROJECT_ROOT, get_env_file_value

#######################################################################################
# Estate globals:
#######################################################################################

SERVICE_SOURCE: str = get_env_file_value("SERVICE_SOURCE", "estate_service")

#######################################################################################
# Estate normalization maps:
#######################################################################################

ROOMS_NUM_MAP: dict[str, int] = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
}

FLOOR_MAP: dict[str, int] = {
    "GROUND": 0,
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
    "EIGHTH": 8,
    "NINTH": 9,
    "TENTH": 10,
    "ELEVENTH": 11,
    "TWELFTH": 12,
    "THIRTEENTH": 13,
    "FOURTEENTH": 14,
    "FIFTEENTH": 15,
}

#######################################################################################
# Estate filters and feature groups:
#######################################################################################

VOIVODESHIPS: frozenset[str] = frozenset(
    {
        "dolnoslaskie",
        "kujawsko--pomorskie",
        "lubelskie",
        "lubuskie",
        "lodzkie",
        "malopolskie",
        "mazowieckie",
        "opolskie",
        "podkarpackie",
        "podlaskie",
        "pomorskie",
        "slaskie",
        "swietokrzyskie",
        "warminsko--mazurskie",
        "wielkopolskie",
        "zachodniopomorskie",
    }
)

ESTATE_TYPES: frozenset[str] = frozenset(
    {
        "mieszkanie",
        "dom",
        "kawalerka",
    }
)

ADDITIONAL_FEATURES: frozenset[str] = frozenset(
    {
        "informacje_dodatkowe",
        "media",
        "wyposazenie",
        "zabezpieczenia",
        "przestrzen_dodatkowa",
        "udogodnienia",
    }
)

#######################################################################################
# HTTP globals:
#######################################################################################

MAIN_URL: str = get_env_file_value("MAIN_URL", "https://example.invalid/results/")
ESTATE_URL: str = get_env_file_value("ESTATE_URL", "https://example.invalid/estate/")

#######################################################################################
# Ingestion pagination and resume limits:
#######################################################################################

MAX_PAGE: int = 1001
RESUME_DUPLICATE_PAGE_STOP_THRESHOLD = 0
DEFAULT_SEARCH_SHARD_STRATEGY = "market-price"

#######################################################################################
# HTTP retry and timeout settings:
#######################################################################################

REQUEST_TIMEOUT_SECONDS: int = 30
REQUEST_RETRIES: int = 3
REQUEST_RETRY_SLEEP_SECONDS: float = 1.0
REQUEST_BLOCK_STATUS_CODES: frozenset[int] = frozenset({403, 429})
REQUEST_BLOCK_RETRIES: int = 96
REQUEST_BLOCK_COOLDOWN_SECONDS: float = 300.0
REQUEST_BLOCK_COOLDOWN_MAX_SECONDS: float = 1800.0
REQUEST_BLOCK_BACKOFF_MULTIPLIER: float = 1.5
REQUEST_BLOCK_JITTER_SECONDS: float = 30.0

#######################################################################################
# HTTP request headers:
#######################################################################################

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) " "Gecko/20100101 Firefox/126.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/json;q=0.8,*/*;q=0.7"
    ),
    "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

#######################################################################################
# Data directories:
#######################################################################################

BRONZE_DATA_DIR: Path = PROJECT_ROOT / "data" / "bronze"
SILVER_DATA_DIR: Path = PROJECT_ROOT / "data" / "silver"
GOLD_DATA_DIR: Path = PROJECT_ROOT / "data" / "gold"
PUBLIC_DATA_DIR: Path = PROJECT_ROOT / "data" / "public"
DEMO_BASE_DIR = PROJECT_ROOT / "data" / "demo"

#######################################################################################
# Parsing helpers:
#######################################################################################

NUMBER_RE = re.compile(r"\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?|\d+(?:[,.]\d+)?")
LIST_SEPARATOR = "|"

#######################################################################################
# ETL defaults:
#######################################################################################

DEFAULT_WORKERS = 4
DEFAULT_MIN_GROUP_SIZE = 10

#######################################################################################
# Bronze stream settings:
#######################################################################################

BRONZE_STREAM_CHECKPOINT_INTERVAL = 25

#######################################################################################
# Demo settings:
#######################################################################################

DEMO_PROCESSED_AT = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
DEMO_MIN_GROUP_SIZE = 2

#######################################################################################
# Market ranking settings:
#######################################################################################

RANKING_FIELDNAMES = (
    "rank",
    "group",
    "records_count",
    "median_price_per_sqm_pln",
    "avg_price_per_sqm_pln",
    "q25_price_per_sqm_pln",
    "q75_price_per_sqm_pln",
    "median_price_pln",
    "share_with_price_per_sqm",
    "share_with_total_price",
)
