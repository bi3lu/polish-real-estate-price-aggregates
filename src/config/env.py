from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def _read_env_file(env_file: Path = ENV_FILE) -> dict[str, str]:
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
    """Normalizes project URLs loaded from environment-like sources."""
    normalized_url = url.strip()

    if normalized_url.startswith("ttps://"):
        normalized_url = f"h{normalized_url}"

    return normalized_url


def get_required_env_file_value(key: str) -> str:
    env_file_vars = _read_env_file()
    raw_value = env_file_vars.get(key)

    if raw_value is None:
        raise RuntimeError(f"Missing required .env variable: {key}")

    return normalize_url(raw_value)


def get_env_file_value(key: str, default: str) -> str:
    env_file_vars = _read_env_file()
    raw_value = env_file_vars.get(key) or default

    return normalize_url(raw_value)
