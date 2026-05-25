"""Global variables and constants for the project."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#######################################################################################
# Estate globals:
#######################################################################################

DEFAULT_SOURCE_ID: str = "source_a"

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

MAIN_URL: str = "https://example-listing-site.local/search"
ESTATE_URL: str = "https://example-listing-site.local"

#######################################################################################
# Ingestion pagination and resume limits:
#######################################################################################

MAX_PAGE: int = 3
INGESTION_HARD_MAX_PAGES_PER_RUN: int = 50
RESUME_DUPLICATE_PAGE_STOP_THRESHOLD = 0
DEFAULT_SEARCH_SHARD_STRATEGY = "market-price"

#######################################################################################
# HTTP retry and timeout settings:
#######################################################################################

REQUEST_TIMEOUT_SECONDS: int = 30
REQUEST_RETRIES: int = 3
REQUEST_RETRY_SLEEP_SECONDS: float = 1.0
REQUEST_RETRY_BACKOFF_MULTIPLIER: float = 2.0
REQUEST_RETRY_MAX_SLEEP_SECONDS: float = 30.0
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
        "PolishRealEstateResearchBot/1.0 "
        "(non-commercial research; +https://github.com/bi3lu/polish-real-estate-price-aggregates)"
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

DEFAULT_WORKERS = 3
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
