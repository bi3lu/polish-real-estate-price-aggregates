"""Global variables and constants for the project."""

from __future__ import annotations

import re
from pathlib import Path

from src.config.env import PROJECT_ROOT, get_required_env_file_value

#######################################################################################
# Estate globals:
#######################################################################################

SERVICE_SOURCE: str = get_required_env_file_value("SERVICE_SOURCE")

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

#######################################################################################
# HTTP globals:
#######################################################################################

MAX_PAGE: int = 1001

REQUEST_TIMEOUT_SECONDS: int = 30
REQUEST_RETRIES: int = 3
REQUEST_RETRY_SLEEP_SECONDS: float = 1.0

MAIN_URL: str = get_required_env_file_value("MAIN_URL")
ESTATE_URL: str = get_required_env_file_value("ESTATE_URL")

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
# Other globals:
#######################################################################################

BRONZE_DATA_DIR: Path = PROJECT_ROOT / "data" / "bronze"
SILVER_DATA_DIR: Path = PROJECT_ROOT / "data" / "silver"
GOLD_DATA_DIR: Path = PROJECT_ROOT / "data" / "gold"

NUMBER_RE = re.compile(r"\d+(?:[\s\u00a0]\d{3})*(?:[,.]\d+)?|\d+(?:[,.]\d+)?")
