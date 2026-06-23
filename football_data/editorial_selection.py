from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from football_data.llm_client import AgentTextClient


class SelectionItem(BaseModel):
    award_type: str
    player_id: str
    player_name: str
    team: str
    editorial_reason: str
    evidence_used: list[str] = Field(default_factory=list)
    selection_risk: str = ""


class SkippedCandidate(BaseModel):
    award_type: str
    player_id: str
    player_name: str
    coarse_rank: int | None = None
    reason: str


class SelectionDecision(BaseModel):
    selected: list[SelectionItem]
    skipped_higher_ranked: list[SkippedCandidate] = Field(default_factory=list)
    skipped_notable_candidates: list[SkippedCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_selector_input(
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
    *,
    shuffle_seed: str | None = None,
) -> dict[str, Any]:
    del shuffle_seed
    candidates = [_compact_candidate(candidate) for candidate in candidate_pool.get("selectable_candidates", [])]
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
            "near_misses": [
                _compact_near_miss(candidate)
                for candidate in candidate_pool.get("near_misses", [])
            ],
        },
    }


def run_ai_rerank_selector(
    selector_input: dict[str, Any],
    text_client: AgentTextClient,
    profile: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    instructions = "\n".join(str(item) for item in profile.get("instructions", []))
    response = text_client.complete(
        role="selection_editor",
        model=model,
        instructions=instructions,
        user_input=json.dumps(selector_input, ensure_ascii=False),
        output_type=SelectionDecision,
    )
    return normalize_selection_decision(_extract_json(response))


AWARD_TYPE_ALIASES = {
    "potd": "player_of_the_day",
    "player": "player_of_the_day",
    "player_of_day": "player_of_the_day",
    "player_of_the_day": "player_of_the_day",
    "impact": "impact_pick",
    "impact_pick": "impact_pick",
    "progression": "progression_pick",
    "progressor": "progression_pick",
    "progression_pick": "progression_pick",
    "defensive": "defensive_pick",
    "defender": "defensive_pick",
    "defensive_pick": "defensive_pick",
    "goalkeeper": "goalkeeper_watch",
    "keeper": "goalkeeper_watch",
    "goalkeeper_watch": "goalkeeper_watch",
    "hidden": "hidden_gem",
    "hidden_gem": "hidden_gem",
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


def repair_selection_decision(
    decision: dict[str, Any],
    candidate_pool: dict[str, Any],
) -> dict[str, Any]:
    repaired = json.loads(json.dumps(decision, ensure_ascii=False))
    warnings = list(repaired.get("warnings", [])) if isinstance(repaired.get("warnings"), list) else []
    candidates = {
        str(candidate.get("player_id")): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
        if isinstance(candidate, dict)
    }
    selected = repaired.get("selected")
    if not isinstance(selected, list):
        repaired["warnings"] = warnings
        return repaired
    for item in selected:
        if not isinstance(item, dict):
            continue
        candidate = candidates.get(str(item.get("player_id")))
        if not candidate:
            continue
        award_type = str(item.get("award_type") or "")
        chips = _candidate_chips(candidate, award_type)
        if _weak_reason(item.get("editorial_reason")):
            item["editorial_reason"] = _fallback_editorial_reason(candidate, award_type, chips)
            warning = f"repaired weak editorial_reason for {candidate.get('player_name')} {award_type}"
            if warning not in warnings:
                warnings.append(warning)
        if _weak_evidence_used(item.get("evidence_used"), chips):
            item["evidence_used"] = chips[:4]
            warning = f"repaired weak evidence_used for {candidate.get('player_name')} {award_type}"
            if warning not in warnings:
                warnings.append(warning)
        if _weak_reason(item.get("selection_risk")):
            item["selection_risk"] = "Low: selected player is in the candidate pool and the evidence packet supports the award."
    repaired["warnings"] = warnings
    return repaired


def _candidate_chips(candidate: dict[str, Any], award_type: str) -> list[str]:
    award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
    chips = (award_context.get("evidence_chips") or {}).get("en")
    if not chips:
        chips = (candidate.get("evidence_chips") or {}).get("en", [])
    return [str(chip) for chip in chips if str(chip).strip()]


def _fallback_editorial_reason(
    candidate: dict[str, Any],
    award_type: str,
    chips: list[str],
) -> str:
    evidence = "; ".join(chips[:3]) or "the candidate packet shows a strong match-day profile"
    award_label = award_type.replace("_", " ")
    return (
        f"Selected for {award_label} because {candidate.get('player_name')} "
        f"has the clearest evidence packet for this slot: {evidence}."
    )


def _weak_reason(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) < 20 or text.lower() in {"en", "zh", "english", "chinese", "low"}


def _weak_evidence_used(value: Any, chips: list[str]) -> bool:
    if not isinstance(value, list) or not value:
        return True
    chip_set = {chip.strip().lower() for chip in chips}
    evidence = [str(item).strip() for item in value if str(item).strip()]
    if not evidence:
        return True
    if any(_weak_reason(item) for item in evidence):
        return True
    return any(item.lower() not in chip_set for item in evidence)


def fake_selection_decision(
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    candidates = list(candidate_pool.get("selectable_candidates", []))
    by_award = {
        award: [
            candidate
            for candidate in candidates
            if award in candidate.get("eligible_awards", [])
        ]
        for award in experiment["selection"]["slots"]
    }
    selection_config = experiment["selection"]
    optional_slots = {str(item) for item in selection_config.get("optional_slots", [])}
    slate_constraints = selection_config.get("slate_constraints", {})
    if not isinstance(slate_constraints, dict):
        slate_constraints = {}
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    team_counts: dict[str, int] = {}
    match_counts: dict[str, int] = {}
    skipped: list[dict[str, Any]] = []
    for award_type, slot_count in selection_config["slots"].items():
        ordered = sorted(
            by_award.get(award_type, []),
            key=lambda candidate: _candidate_award_score(candidate, award_type),
            reverse=True,
        )
        picked = 0
        for candidate in ordered:
            player_id = str(candidate["player_id"])
            if player_id in used:
                continue
            if not _slate_allows(candidate, team_counts, match_counts, slate_constraints):
                continue
            selected.append(_selected_item(award_type, candidate))
            used.add(player_id)
            _count_slate(candidate, team_counts, match_counts)
            picked += 1
            if picked >= int(slot_count):
                break
        if picked < int(slot_count) and award_type not in optional_slots:
            for candidate in ordered:
                player_id = str(candidate["player_id"])
                if player_id in used:
                    continue
                selected.append(_selected_item(award_type, candidate))
                used.add(player_id)
                _count_slate(candidate, team_counts, match_counts)
                picked += 1
                if picked >= int(slot_count):
                    break
    selected_potd_ids = {
        item["player_id"]
        for item in selected
        if item["award_type"] == "player_of_the_day"
    }
    selected_potd_ranks = [
        int(candidate.get("headline_rank") or 9999)
        for candidate in candidates
        if candidate["player_id"] in selected_potd_ids
    ]
    worst_selected_rank = max(selected_potd_ranks or [0])
    for candidate in by_award.get("player_of_the_day", []):
        rank = int(candidate.get("headline_rank") or 9999)
        if rank < worst_selected_rank and candidate["player_id"] not in selected_potd_ids:
            skipped.append(
                {
                    "award_type": "player_of_the_day",
                    "player_id": candidate["player_id"],
                    "player_name": candidate["player_name"],
                    "coarse_rank": candidate.get("headline_rank"),
                    "reason": "Higher raw rank, but the selected slate gives a broader match-day story.",
                }
            )
    return {
        "selected": selected,
        "skipped_higher_ranked": skipped,
        "skipped_notable_candidates": [],
        "warnings": [],
    }


def _selected_item(award_type: str, candidate: dict[str, Any]) -> dict[str, Any]:
    award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
    chips = (award_context.get("evidence_chips") or {}).get("en")
    if not chips:
        chips = candidate.get("evidence_chips", {}).get("en", [])
    reason = ", ".join(str(chip) for chip in chips[:2]) or "strong all-round evidence"
    return {
        "award_type": award_type,
        "player_id": candidate["player_id"],
        "player_name": candidate["player_name"],
        "team": candidate["team"],
        "editorial_reason": f"Selected from the candidate pool for {reason}.",
        "evidence_used": [str(chip) for chip in chips[:4]],
        "selection_risk": "Low: deterministic evidence supports the selection.",
    }


def _candidate_award_score(candidate: dict[str, Any], award_type: str) -> tuple[float, float, float, float]:
    role_scores = candidate.get("role_scores") or {}
    metrics = ((candidate.get("award_contexts") or {}).get(award_type) or {}).get("metrics") or {}
    headline_rank = int(candidate.get("headline_rank") or 9999)
    if award_type == "player_of_the_day":
        team_won = int(candidate.get("team_final_goals") or 0) > int(candidate.get("opponent_final_goals") or 0)
        direct_tier = (
            _num(metrics, "goals") * 100
            + _num(metrics, "assists") * 35
            + _num(metrics, "hat_trick") * 50
            + _num(metrics, "brace") * 10
            + (20 if team_won else 0)
        )
        decisive_tiebreak = (
            _num(metrics, "match_winning_goal")
            + _num(metrics, "comeback_winner")
            + _num(metrics, "late_match_winning_goal")
        )
        return (direct_tier, float(candidate.get("headline_score") or 0), decisive_tiebreak, -headline_rank)
    if award_type == "impact_pick":
        return (
            float(role_scores.get("impact") or 0),
            float(candidate.get("headline_score") or 0),
            -headline_rank,
            0,
        )
    if award_type == "progression_pick":
        benchmark = candidate.get("progression_benchmark") or {}
        return (
            float(benchmark.get("score") or 0),
            float(role_scores.get("progressor") or 0),
            -headline_rank,
            0,
        )
    if award_type == "defensive_pick":
        return (
            float(role_scores.get("defensive") or 0),
            float(candidate.get("headline_score") or 0),
            -headline_rank,
            0,
        )
    if award_type == "goalkeeper_watch":
        return (
            float(role_scores.get("goalkeeper") or 0),
            float(candidate.get("opponent_xg") or 0),
            float(candidate.get("opponent_attempts_on_target") or 0),
            -headline_rank,
        )
    if award_type == "hidden_gem":
        profile = candidate.get("hidden_gem_profile") or {}
        return (
            float(profile.get("score") or 0),
            float(candidate.get("headline_score") or 0),
            -headline_rank,
            0,
        )
    return (float(candidate.get("headline_score") or 0), -headline_rank, 0, 0)


def _slate_allows(
    candidate: dict[str, Any],
    team_counts: dict[str, int],
    match_counts: dict[str, int],
    slate_constraints: dict[str, Any],
) -> bool:
    max_per_team = int(slate_constraints.get("max_per_team") or 0)
    max_per_match = int(slate_constraints.get("max_per_match") or 0)
    team = str(candidate.get("team") or "")
    match_key = str(candidate.get("match_key") or "")
    if max_per_team and team_counts.get(team, 0) >= max_per_team:
        return False
    if max_per_match and match_counts.get(match_key, 0) >= max_per_match:
        return False
    return True


def _count_slate(
    candidate: dict[str, Any],
    team_counts: dict[str, int],
    match_counts: dict[str, int],
) -> None:
    team = str(candidate.get("team") or "")
    match_key = str(candidate.get("match_key") or "")
    team_counts[team] = team_counts.get(team, 0) + 1
    match_counts[match_key] = match_counts.get(match_key, 0) + 1


def _num(metrics: dict[str, Any], key: str) -> float:
    return float(metrics.get(key) or 0)


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
        "reason_not_in_pool",
    ]
    compact = {key: candidate.get(key) for key in keys if key in candidate}
    compact["score_components"] = list(candidate.get("score_components", []))[:4]
    return compact


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        return json.loads(text[start : end + 1])
