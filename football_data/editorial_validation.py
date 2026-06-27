from __future__ import annotations

from collections import Counter
from typing import Any


def validate_selection_decision(
    decision: dict[str, Any],
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    selectable = {
        str(candidate["player_id"]): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
    }
    selection_config = experiment.get("selection", {})
    award_limits = _selection_award_limits(selection_config)
    allowed_awards = {
        award_type
        for award_type, limit in award_limits.items()
        if int(limit) > 0
    }
    selected = decision.get("selected") if isinstance(decision.get("selected"), list) else []
    if not selected:
        warnings.append("selection_decision.selected is empty")

    seen_keys: set[tuple[str, str]] = set()
    award_counts: Counter[str] = Counter()
    team_counts: Counter[str] = Counter()
    match_counts: Counter[str] = Counter()
    player_awards: dict[str, str] = {}
    for item in selected:
        player_id = str(item.get("player_id") or "")
        award_type = str(item.get("award_type") or "")
        if player_id not in selectable:
            warnings.append(f"{player_id or 'missing player'} not in candidate pool")
            continue
        candidate = selectable[player_id]
        if award_type not in allowed_awards:
            warnings.append(f"{award_type or 'missing award_type'} is not an allowed public award type")
        elif award_type not in candidate.get("eligible_awards", []):
            warnings.append(f"{player_id} is not eligible for {award_type}")
        key = (award_type, player_id)
        if key in seen_keys:
            warnings.append(f"duplicate selection {award_type}:{player_id}")
        seen_keys.add(key)
        if player_id in player_awards and player_awards[player_id] != award_type:
            warnings.append(f"{player_id} selected for multiple awards")
        player_awards[player_id] = award_type
        award_counts[award_type] += 1
        team_counts[str(candidate.get("team") or "")] += 1
        match_counts[str(candidate.get("match_key") or "")] += 1

    required_slots = _selection_required_slots(selection_config)
    for award_type, expected_count in award_limits.items():
        if award_counts[award_type] > int(expected_count):
            warnings.append(f"{award_type} exceeds configured award limit")
    for award_type, expected_count in required_slots.items():
        if award_counts[award_type] < int(expected_count):
            warnings.append(f"missing required slot {award_type}")
    target_public_cards = int(selection_config.get("target_public_cards") or 0)
    public_card_count = _selection_public_card_count(selection_config)
    if target_public_cards and len(selected) != target_public_cards:
        warnings.append(
            f"selected public card count {len(selected)} does not match target_public_cards {target_public_cards}"
        )
    elif public_card_count:
        min_count, max_count = public_card_count
        if len(selected) < min_count or len(selected) > max_count:
            warnings.append(
                "selected public card count "
                f"{len(selected)} outside public_card_count range {min_count}-{max_count}"
            )

    slate_constraints = selection_config.get("slate_constraints", {})
    if isinstance(slate_constraints, dict):
        max_per_team = int(slate_constraints.get("max_per_team") or 0)
        if max_per_team:
            for team, count in team_counts.items():
                if team and count > max_per_team:
                    warnings.append(f"{team} exceeds max_per_team {max_per_team}")
        max_per_match = int(slate_constraints.get("max_per_match") or 0)
        if max_per_match:
            for match_key, count in match_counts.items():
                if match_key and count > max_per_match:
                    warnings.append(f"{match_key} exceeds max_per_match {max_per_match}")

    if selection_config.get("must_explain_skipped_higher_ranked_candidates"):
        skipped_ids = {
            str(item.get("player_id") or "")
            for item in decision.get("skipped_higher_ranked", [])
            if isinstance(item, dict)
        }
        selected_potd = [
            item
            for item in selected
            if isinstance(item, dict) and item.get("award_type") == "player_of_the_day"
        ]
        selected_ids = {
            str(item.get("player_id"))
            for item in selected
            if isinstance(item, dict)
        }
        selected_potd_ids = {str(item.get("player_id")) for item in selected_potd}
        for item in selected_potd:
            player = selectable.get(str(item.get("player_id")))
            if not player:
                continue
            rank = int(player.get("headline_rank") or 9999)
            higher_unselected = [
                candidate
                for candidate in candidate_pool.get("selectable_candidates", [])
                if "player_of_the_day" in candidate.get("eligible_awards", [])
                and int(candidate.get("headline_rank") or 9999) < rank
                and str(candidate.get("player_id")) not in selected_ids
            ]
            missing = [
                candidate
                for candidate in higher_unselected
                if str(candidate.get("player_id")) not in skipped_ids
            ]
            if missing:
                warnings.append(
                    "skipped_higher_ranked is required for "
                    f"{item.get('player_name')} over {missing[0].get('player_name')}"
                )

    return {
        "schema_version": 1,
        "status": "failed" if warnings else "pass",
        "warnings": warnings,
    }


def _selection_award_limits(selection_config: dict[str, Any]) -> dict[str, int]:
    raw_limits = selection_config.get("award_limits")
    if not isinstance(raw_limits, dict):
        raw_limits = selection_config.get("slots", {})
    if not isinstance(raw_limits, dict):
        return {}
    return {str(key): int(value) for key, value in raw_limits.items()}


def _selection_required_slots(selection_config: dict[str, Any]) -> dict[str, int]:
    raw_required = selection_config.get("required_slots")
    if isinstance(raw_required, dict):
        return {str(key): int(value) for key, value in raw_required.items()}
    if isinstance(raw_required, list):
        return {str(item): 1 for item in raw_required}
    raw_slots = selection_config.get("slots", {})
    if not isinstance(raw_slots, dict):
        return {}
    optional_slots = {
        str(item)
        for item in (
            selection_config.get("optional_slots")
            or selection_config.get("optional_awards")
            or []
        )
    }
    return {
        str(award_type): int(expected_count)
        for award_type, expected_count in raw_slots.items()
        if str(award_type) not in optional_slots
    }


def _selection_public_card_count(selection_config: dict[str, Any]) -> tuple[int, int] | None:
    raw_count = selection_config.get("public_card_count")
    if not isinstance(raw_count, dict):
        return None
    min_count = int(raw_count.get("min") or 0)
    max_count = int(raw_count.get("max") or 0)
    if min_count <= 0 or max_count <= 0:
        return None
    if min_count > max_count:
        min_count, max_count = max_count, min_count
    return min_count, max_count
