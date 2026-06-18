from __future__ import annotations

import json
import shlex
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def load_keypool_env(path: str | Path = ".env.local") -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Missing env file: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _clean_env_value(value.strip())
        values[key] = value
    for required in ("KEYPOOL_URL", "KEYPOOL_KEY"):
        if not values.get(required):
            raise ValueError(f"Missing {required} in {env_path}")
    values["KEYPOOL_URL"] = normalize_keypool_url(values["KEYPOOL_URL"])
    return values


def normalize_keypool_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if not urllib.parse.urlparse(cleaned).scheme:
        cleaned = "https://" + cleaned
    return cleaned


def build_firecrawl_url(base_url: str, path: str) -> str:
    return normalize_keypool_url(base_url) + "/" + path.lstrip("/")


def search_firecrawl(
    *,
    query: str,
    limit: int = 5,
    env_path: str | Path = ".env.local",
    timeout: int = 45,
) -> list[dict[str, str]]:
    env = load_keypool_env(env_path)
    payload = json.dumps({"query": query, "limit": limit}).encode()
    request = urllib.request.Request(
        build_firecrawl_url(env["KEYPOOL_URL"], "/v2/search"),
        data=payload,
        headers=_headers(env["KEYPOOL_KEY"]),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firecrawl search failed with HTTP {exc.code}: {body[:500]}") from exc
    return extract_firecrawl_search_results(json.loads(body))


def extract_firecrawl_search_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    data = payload.get("data")
    if isinstance(data, dict):
        raw_results = data.get("web") or data.get("results") or []
    elif isinstance(data, list):
        raw_results = data
    else:
        raw_results = []
    results: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("sourceURL")
        if not url:
            continue
        results.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(url),
                "description": str(item.get("description") or item.get("markdown") or ""),
            }
        )
    return results


def _headers(keypool_key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {keypool_key}",
        "content-type": "application/json",
        "x-keypool-service": "firecrawl",
        "user-agent": "Mozilla/5.0",
    }


def _clean_env_value(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        try:
            parsed = shlex.split(value)
        except ValueError:
            return value[1:-1]
        return parsed[0] if parsed else ""
    return value
