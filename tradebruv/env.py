from __future__ import annotations

import os
from pathlib import Path
from typing import Any


ENV_EXAMPLE_PATH = Path(".env.example")
LOCAL_ENV_PATH = Path(".env")
LOCAL_ENV_WARNING = (
    "Local-only feature. Do not enable TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR if this app is deployed "
    "or reachable by anyone else."
)


def load_local_env(path: Path = LOCAL_ENV_PATH) -> None:
    """Load .env for local development without requiring python-dotenv."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _fallback_load_dotenv(path)
    else:
        load_dotenv(path, override=False)


def local_env_editor_enabled() -> bool:
    return _truthy(os.getenv("TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR"))


def read_env_template(path: Path = ENV_EXAMPLE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "content": "",
            "keys": [],
            "warning": LOCAL_ENV_WARNING,
        }
    content = path.read_text(encoding="utf-8")
    return {
        "exists": True,
        "path": str(path),
        "content": content,
        "keys": _keys_from_content(content),
        "warning": LOCAL_ENV_WARNING,
    }


def create_local_env_from_template(
    *,
    template_path: Path = ENV_EXAMPLE_PATH,
    env_path: Path = LOCAL_ENV_PATH,
) -> dict[str, Any]:
    if env_path.exists():
        return {"created": False, "exists": True, "path": str(env_path), "message": ".env already exists."}
    if not template_path.exists():
        raise FileNotFoundError(f"Missing template: {template_path}")
    env_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"created": True, "exists": True, "path": str(env_path), "message": ".env created from .env.example."}


def update_local_env(values: dict[str, str], *, env_path: Path = LOCAL_ENV_PATH) -> dict[str, Any]:
    if not local_env_editor_enabled():
        raise PermissionError("TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR is not true.")
    cleaned = {
        key.strip(): str(value).strip()
        for key, value in values.items()
        if _valid_env_key(key.strip()) and str(value).strip()
    }
    existing = _read_env_file(env_path) if env_path.exists() else {}
    existing.update(cleaned)
    env_path.write_text(_render_env_file(existing), encoding="utf-8")
    for key, value in cleaned.items():
        os.environ.setdefault(key, value)
    return {
        "updated": True,
        "path": str(env_path),
        "updated_keys": sorted(cleaned),
        "message": "Local .env updated. Restart the backend so every provider sees the new values.",
        "warning": LOCAL_ENV_WARNING,
    }


def _fallback_load_dotenv(path: Path) -> None:
    for key, value in _read_env_file(path).items():
        os.environ.setdefault(key, value)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not _valid_env_key(key):
            continue
        values[key] = _unquote(raw_value.strip())
    return values


def _render_env_file(values: dict[str, str]) -> str:
    lines = [f"{key}={_quote_if_needed(value)}" for key, value in sorted(values.items())]
    return "\n".join(lines) + "\n"


def _keys_from_content(content: str) -> list[str]:
    keys: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if _valid_env_key(key):
            keys.append(key)
    return keys


def _valid_env_key(key: str) -> bool:
    return bool(key) and key.replace("_", "").isalnum() and key[0].isalpha()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _quote_if_needed(value: str) -> str:
    if not value or any(char.isspace() for char in value) or "#" in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
