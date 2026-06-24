from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_DIR = Path("config/editorial")


def player_display_entry(
    player_name: str,
    language: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    registry = load_display_name_registry(language, config_dir)
    players = registry.get("players")
    if not isinstance(players, dict):
        return {}
    entry = players.get(player_name)
    if isinstance(entry, str):
        return {"display_name": entry}
    if isinstance(entry, dict):
        return {str(key): value for key, value in entry.items()}
    return {}


def player_display_name(
    player_name: str,
    language: str,
    *,
    field: str = "display_name",
    fallback: str | None = None,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> str:
    entry = player_display_entry(player_name, language, config_dir)
    value = entry.get(field) or entry.get("display_name")
    if value:
        return str(value)
    return player_name if fallback is None else fallback


@lru_cache(maxsize=16)
def _load_display_name_registry_cached(language: str, config_dir: str) -> dict[str, Any]:
    path = Path(config_dir) / "display_names" / f"{language}.json"
    if not path.exists():
        return {"language": language, "players": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Display-name registry file must contain an object: {path}")
    return payload


def load_display_name_registry(
    language: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    return _load_display_name_registry_cached(str(language), str(config_dir))
