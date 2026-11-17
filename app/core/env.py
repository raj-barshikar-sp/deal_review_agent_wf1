"""Read and update the local .env file."""

import os

from app.config import ENV_PATH


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env() -> None:
    """Load .env without overriding variables already set in the process."""
    if not ENV_PATH.exists():
        return
    for key, value in parse_env(ENV_PATH.read_text()).items():
        os.environ.setdefault(key, value)


def setting(*names: str) -> str:
    """First non-empty value among names: process env first, then .env."""
    file_values = parse_env(ENV_PATH.read_text()) if ENV_PATH.exists() else {}
    for name in names:
        current = os.environ.get(name, "").strip()
        if current:
            return current
        stored = file_values.get(name, "").strip()
        if stored:
            return stored
    return ""


def update_env_file(updates: dict[str, str]) -> None:
    """Set keys in .env, replacing existing lines and appending new ones."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    kept = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            kept.append(f"{key}={remaining.pop(key)}")
        else:
            kept.append(line)
    for key, value in remaining.items():
        kept.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(kept) + "\n")
