from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from football_data.editorial_registry import DEFAULT_CONFIG_DIR


def load_style_calibration(
    language: str,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    *,
    categories: list[str] | None = None,
    max_examples: int | None = None,
) -> list[dict[str, Any]]:
    path = Path(config_dir) / "style_calibration" / f"{language}.jsonl"
    if not path.exists():
        return []
    wanted_categories = {str(category) for category in categories or [] if str(category).strip()}
    examples: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid style calibration JSONL at {path}:{line_no}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"Style calibration row must be an object: {path}:{line_no}")
        normalized = _normalize_example(item, path=path, line_no=line_no)
        if wanted_categories and normalized["category"] not in wanted_categories:
            continue
        examples.append(normalized)
        if max_examples is not None and len(examples) >= max_examples:
            break
    return examples


def _normalize_example(item: dict[str, Any], *, path: Path, line_no: int) -> dict[str, Any]:
    required = {
        "id",
        "category",
        "bad",
        "why_bad",
        "better",
        "principle",
        "confidence",
    }
    missing = sorted(key for key in required if not item.get(key))
    if missing:
        raise ValueError(
            f"Style calibration row missing {', '.join(missing)}: {path}:{line_no}"
        )
    better = item.get("better")
    if isinstance(better, str):
        better_values = [better]
    elif isinstance(better, list):
        better_values = [str(value) for value in better if str(value).strip()]
    else:
        better_values = []
    if not better_values:
        raise ValueError(f"Style calibration row must include better examples: {path}:{line_no}")
    normalized = dict(item)
    normalized["id"] = str(item["id"])
    normalized["category"] = str(item["category"])
    normalized["bad"] = str(item["bad"])
    normalized["why_bad"] = str(item["why_bad"])
    normalized["better"] = better_values
    normalized["principle"] = str(item["principle"])
    normalized["confidence"] = str(item["confidence"])
    return normalized
