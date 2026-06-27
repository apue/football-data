from __future__ import annotations

from typing import Any


def validate_copy(
    copy: dict[str, Any],
    copy_profiles: dict[str, dict[str, Any]],
    *,
    copy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    choices_by_player_id = _choices_by_player_id(copy_payload)
    for language, profile in copy_profiles.items():
        payload = copy.get(language)
        if not isinstance(payload, dict):
            continue
        terms = [str(term) for term in profile.get("banned_public_terms", []) if str(term).strip()]
        unsupported_terms = [
            str(term)
            for term in profile.get("unsupported_public_terms", [])
            if str(term).strip()
        ]
        title_policy = profile.get("title_policy") if isinstance(profile.get("title_policy"), dict) else {}
        title_terms = [
            str(term)
            for term in title_policy.get("banned_title_terms", [])
            if str(term).strip()
        ]
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            body = str(item.get("body") or "")
            label = str(item.get("player_id") or item.get("award_type") or "unknown")
            for term in terms:
                if term in title or term in body:
                    warnings.append(f"banned {language} public term {term!r} in {label}")
            for term in unsupported_terms:
                if term in title or term in body:
                    warnings.append(f"unsupported {language} public term {term!r} in {label}")
            for term in title_terms:
                if term in title:
                    warnings.append(f"banned {language} title term {term!r} in {label}")
            if language == "zh" and title_policy.get("mode") == "core_fact_label":
                warnings.extend(_zh_title_core_fact_warnings(item, choices_by_player_id))
    return {
        "schema_version": 1,
        "status": "failed" if warnings else "pass",
        "warnings": warnings,
    }


def _choices_by_player_id(copy_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(copy_payload, dict):
        return {}
    return {
        str(choice.get("player_id")): choice
        for choice in copy_payload.get("choices", [])
        if isinstance(choice, dict) and choice.get("player_id")
    }


def _zh_title_core_fact_warnings(
    copy_item: dict[str, Any],
    choices_by_player_id: dict[str, dict[str, Any]],
) -> list[str]:
    player_id = str(copy_item.get("player_id") or "")
    choice = choices_by_player_id.get(player_id)
    if not choice:
        return []
    title = str(copy_item.get("title") or "")
    award_type = str(copy_item.get("award_type") or "")
    metrics = choice.get("metrics") if isinstance(choice.get("metrics"), dict) else {}
    warnings: list[str] = []
    goals = int(metrics.get("goals") or 0)
    assists = int(metrics.get("assists") or 0)
    match_winning_goal = int(metrics.get("match_winning_goal") or 0)
    comeback_winner = int(metrics.get("comeback_winner") or 0)
    late_match_winning_goal = int(metrics.get("late_match_winning_goal") or 0)
    if goals >= 3:
        if not _has_any(title, ["帽子戏法"]):
            warnings.append(f"missing zh title core fact hat_trick in {player_id}")
    elif goals >= 2 and not _has_any(title, ["梅开二度", "双响", "两球", "两度破门", "独中两元"]):
        warnings.append(f"missing zh title core fact goals>=2 in {player_id}")
    if goals >= 2 and (match_winning_goal or comeback_winner or late_match_winning_goal):
        if not _has_any(title, ["制胜", "反超", "绝杀"]):
            warnings.append(f"missing zh title core fact winner in {player_id}")
    elif goals < 2 and (match_winning_goal or comeback_winner or late_match_winning_goal):
        if not _has_any(title, ["制胜", "反超", "绝杀"]):
            warnings.append(f"missing zh title core fact winner in {player_id}")
    if goals == 0 and assists >= 2 and not _has_any(title, ["两次助攻", "双助攻", "助攻双响"]):
        warnings.append(f"missing zh title core fact assists>=2 in {player_id}")
    return warnings


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)
