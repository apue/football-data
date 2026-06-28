from __future__ import annotations

import json
from typing import Any


def build_selector_input(
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
    *,
    shuffle_seed: str | None = None,
) -> dict[str, Any]:
    del shuffle_seed
    candidates = [_compact_candidate(candidate) for candidate in candidate_pool.get("selectable_candidates", [])]
    audit_candidates = [
        _compact_audit_candidate(candidate)
        for candidate in candidate_pool.get("audit_candidates", [])
        if isinstance(candidate, dict)
    ]
    strategy = str(experiment.get("shuffle_strategy") or "name_sorted")
    if strategy == "name_sorted":
        candidates.sort(key=lambda item: (str(item.get("player_name") or ""), str(item.get("team") or "")))
    elif strategy == "score_ordered_for_debug":
        candidates.sort(key=lambda item: int(item.get("headline_rank") or 9999))
    return {
        "schema_version": 1,
        "workflow_variant": experiment["workflow_variant"],
        "selection": experiment["selection"],
        "match_date": candidate_pool["match_date"],
        "scoring_version": candidate_pool["scoring_version"],
        "candidate_pool": {
            "selectable_candidates": candidates,
            "audit_candidates": audit_candidates,
            "near_misses": [
                _compact_near_miss(candidate)
                for candidate in candidate_pool.get("near_misses", [])
            ],
        },
    }


AWARD_TYPE_ALIASES = {
    "potd": "player_of_the_day",
    "player": "player_of_the_day",
    "player_of_day": "player_of_the_day",
    "player_of_the_day": "player_of_the_day",
    "impact": "impact_pick",
    "impact_pick": "impact_pick",
}


def normalize_selection_decision(decision: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(decision, ensure_ascii=False))
    warnings = list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings"), list) else []
    for key in ("selected", "skipped_higher_ranked", "skipped_notable_candidates"):
        items = normalized.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_award_type = str(item.get("award_type") or "")
            canonical = AWARD_TYPE_ALIASES.get(raw_award_type)
            if canonical and canonical != raw_award_type:
                item["award_type"] = canonical
                warning = f"normalized award_type {raw_award_type} to {canonical}"
                if warning not in warnings:
                    warnings.append(warning)
    normalized["warnings"] = warnings
    return normalized


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "player_id",
        "player_name",
        "team",
        "opponent",
        "match_key",
        "match_no",
        "player_no",
        "position",
        "started",
        "headline_rank",
        "headline_score",
        "rank_score",
        "eligible_awards",
        "pool_reasons",
        "role_scores",
        "evidence_chips",
        "display_names",
        "data_sources",
    ]
    compact = {key: candidate.get(key) for key in keys if key in candidate}
    compact["score_components"] = list(candidate.get("score_components", []))[:6]
    compact["award_contexts"] = {
        award_type: {
            "award_label": context.get("award_label"),
            "metrics": context.get("metrics", {}),
            "evidence_chips": context.get("evidence_chips", {"en": [], "zh": []}),
        }
        for award_type, context in (candidate.get("award_contexts") or {}).items()
        if isinstance(context, dict)
    }
    flow_context = candidate.get("flow_context") or {}
    if flow_context:
        compact["flow_context"] = {
            "allowed_claims": flow_context.get("allowed_claims", {}),
            "goal_tags": flow_context.get("goal_tags", []),
            "team_came_from_behind_to_win": flow_context.get("team_came_from_behind_to_win"),
        }
    hidden_gem = candidate.get("hidden_gem_profile") or {}
    if hidden_gem:
        compact["hidden_gem_profile"] = {
            key: hidden_gem.get(key)
            for key in ("eligible", "score", "reasons")
            if key in hidden_gem
        }
    progression = candidate.get("progression_benchmark") or {}
    if progression:
        compact["progression_benchmark"] = {
            key: progression.get(key)
            for key in (
                "score",
                "quality",
                "support_actions",
                "pass_only_line_break_volume",
                "percentile",
                "label",
            )
            if key in progression
        }
    return compact


def _compact_audit_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "player_id",
        "player_name",
        "team",
        "opponent",
        "match_key",
        "match_no",
        "player_no",
        "position",
        "started",
        "headline_rank",
        "headline_score",
        "rank_score",
        "audit_type",
        "audit_reasons",
        "role_scores",
        "display_names",
        "data_sources",
    ]
    compact = {key: candidate.get(key) for key in keys if key in candidate}
    active_context = (candidate.get("audit_contexts") or {}).get(str(candidate.get("audit_type") or "")) or {}
    if active_context:
        compact["audit_context"] = {
            "award_label": active_context.get("award_label"),
            "metrics": active_context.get("metrics", {}),
            "evidence_chips": active_context.get("evidence_chips", {"en": [], "zh": []}),
        }
    hidden_gem = candidate.get("hidden_gem_profile") or {}
    if hidden_gem:
        compact["hidden_gem_profile"] = {
            key: hidden_gem.get(key)
            for key in ("eligible", "score", "reasons")
            if key in hidden_gem
        }
    progression = candidate.get("progression_benchmark") or {}
    if progression:
        compact["progression_benchmark"] = {
            key: progression.get(key)
            for key in (
                "score",
                "quality",
                "support_actions",
                "pass_only_line_break_volume",
                "percentile",
                "label",
            )
            if key in progression
        }
    return compact

def _compact_near_miss(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "player_id",
        "player_name",
        "team",
        "opponent",
        "match_no",
        "position",
        "headline_rank",
        "headline_score",
        "rank_score",
        "evidence_chips",
        "data_sources",
        "reason_not_in_pool",
    ]
    compact = {key: candidate.get(key) for key in keys if key in candidate}
    compact["score_components"] = list(candidate.get("score_components", []))[:4]
    return compact
