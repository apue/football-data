from __future__ import annotations

from typing import Any


def match_count_for_candidate_pool(candidate_pool: dict[str, Any]) -> int:
    raw_count = candidate_pool.get("match_count")
    if raw_count is not None:
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return count

    matches = candidate_pool.get("matches")
    if isinstance(matches, list):
        keys: set[str] = set()
        for item in matches:
            if isinstance(item, dict):
                key = str(item.get("match_key") or item.get("match_no") or "")
            else:
                key = str(item or "")
            if key.strip():
                keys.add(key)
        if keys:
            return len(keys)

    keys = set()
    for group_name in ("selectable_candidates", "audit_candidates", "near_misses"):
        for item in candidate_pool.get(group_name, []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("match_key") or "")
            if key.strip():
                keys.add(key)
    return len(keys)


def selection_public_card_count(
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any],
) -> tuple[int, int] | None:
    context = public_card_count_context(candidate_pool, selection_config)
    min_count = _positive_int(context.get("min"))
    max_count = _positive_int(context.get("max"))
    if min_count <= 0 or max_count <= 0:
        return None
    if min_count > max_count:
        min_count, max_count = max_count, min_count
    return min_count, max_count


def public_card_count_context(
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any],
    *,
    selected_count: int = 0,
) -> dict[str, Any]:
    raw_count = selection_config.get("public_card_count")
    match_count = match_count_for_candidate_pool(candidate_pool)
    if not isinstance(raw_count, dict):
        return {
            "selected": selected_count,
            "match_count": match_count,
            "min": None,
            "recommended": None,
            "max": None,
            "policy": "none",
            "guidance": "",
        }

    rule = _matching_match_count_rule(raw_count, match_count)
    if rule:
        min_count = _positive_int(rule.get("min")) or _positive_int(raw_count.get("min"))
        max_count = _positive_int(rule.get("max")) or _positive_int(raw_count.get("max"))
        recommended = _positive_int(rule.get("recommended")) or min_count or max_count
        policy = "match_count_rule"
        guidance = str(rule.get("guidance") or "")
    else:
        min_count = _positive_int(raw_count.get("min"))
        max_count = _positive_int(raw_count.get("max"))
        recommended = _positive_int(raw_count.get("recommended")) or min_count or max_count
        policy = "static_range"
        guidance = str(raw_count.get("guidance") or "")

    if min_count and max_count and min_count > max_count:
        min_count, max_count = max_count, min_count
    return {
        "selected": selected_count,
        "match_count": match_count,
        "min": min_count or None,
        "recommended": recommended or None,
        "max": max_count or None,
        "policy": policy,
        "guidance": guidance,
    }


def _matching_match_count_rule(raw_count: dict[str, Any], match_count: int) -> dict[str, Any] | None:
    rules = raw_count.get("match_count_rules")
    if not isinstance(rules, list):
        return None
    for item in rules:
        if not isinstance(item, dict):
            continue
        min_matches = _positive_int(item.get("min_matches"))
        max_matches_raw = item.get("max_matches")
        max_matches = _positive_int(max_matches_raw) if max_matches_raw is not None else None
        if match_count >= min_matches and (max_matches is None or match_count <= max_matches):
            return item
    return None


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
