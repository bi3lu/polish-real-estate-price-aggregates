"""Environment-file loading helpers for project configuration."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def _read_env_file(env_file: Path = ENV_FILE) -> dict[str, str]:
    """Read simple key-value pairs from an environment file.

    Args:
        env_file: Path to a dotenv-style file.

    Returns:
        Mapping of parsed environment variable names to string values.
    """
    if not env_file.exists():
        return {}

    env_vars: dict[str, str] = {}

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()

        if (
            not stripped_line
            or stripped_line.startswith("#")
            or "=" not in stripped_line
        ):
            continue

        key, value = stripped_line.split("=", maxsplit=1)
        env_vars[key.strip()] = value.strip().strip("'\"")

    return env_vars


def normalize_url(url: str) -> str:
    """Normalize project URLs loaded from environment-like sources.

    Args:
        url: Raw URL value.

    Returns:
        URL stripped of leading and trailing whitespace.
    """
    return url.strip()


def get_required_env_file_value(key: str) -> str:
    """Return a required value from the project environment file.

    Args:
        key: Environment variable name to read.

    Returns:
        Normalized environment value.

    Raises:
        RuntimeError: If the requested key is missing from the environment file.
    """
    env_file_vars = _read_env_file()
    raw_value = env_file_vars.get(key)

    if raw_value is None:
        raise RuntimeError(f"Missing required .env variable: {key}")

    return normalize_url(raw_value)


def get_env_file_value(key: str, default: str) -> str:
    """Return a value from the environment file or a default.

    Args:
        key: Environment variable name to read.
        default: Value used when the key is missing or empty.

    Returns:
        Normalized configured value.
    """
    env_file_vars = _read_env_file()
    raw_value = env_file_vars.get(key) or default
    return normalize_url(raw_value)
