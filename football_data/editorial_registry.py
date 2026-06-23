from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_DIR = Path("config/editorial")


def load_editorial_experiment(
    experiment_id: str | None = None,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    root = Path(config_dir)
    resolved_id = experiment_id or _active_experiment_id(root)
    experiment = _load_registry_json(root / "experiments" / f"{resolved_id}.json")
    _require_id(experiment, resolved_id, "experiment")
    return experiment


def load_candidate_pool_config(
    pool_id: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    root = Path(config_dir)
    config = _load_registry_json(root / "candidate_pools" / f"{pool_id}.json")
    _require_id(config, pool_id, "candidate pool")
    return config


def load_selector_profile(
    profile_id: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    root = Path(config_dir)
    profile = _load_registry_json(root / "selector_profiles" / f"{profile_id}.json")
    _require_id(profile, profile_id, "selector profile")
    return profile


def load_copy_profile(
    profile_id: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    root = Path(config_dir)
    profile = _load_registry_json(root / "copy_profiles" / f"{profile_id}.json")
    _require_id(profile, profile_id, "copy profile")
    return profile


def _active_experiment_id(root: Path) -> str:
    production = _load_registry_json(root / "production.json")
    value = production.get("active_experiment")
    if not value:
        raise ValueError(f"Missing active_experiment in {root / 'production.json'}")
    return str(value)


def _load_registry_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Missing editorial registry file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Editorial registry file must contain an object: {path}")
    return payload


def _require_id(payload: dict[str, Any], expected_id: str, kind: str) -> None:
    actual = payload.get("id")
    if actual != expected_id:
        raise ValueError(f"Expected {kind} id {expected_id!r}, got {actual!r}")
