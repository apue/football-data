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
    selected = decision.get("selected") if isinstance(decision.get("selected"), list) else []
    if not selected:
        warnings.append("selection_decision.selected is empty")

    seen_keys: set[tuple[str, str]] = set()
    award_counts: Counter[str] = Counter()
    for item in selected:
        player_id = str(item.get("player_id") or "")
        award_type = str(item.get("award_type") or "")
        if player_id not in selectable:
            warnings.append(f"{player_id or 'missing player'} not in candidate pool")
            continue
        if award_type not in selectable[player_id].get("eligible_awards", []):
            warnings.append(f"{player_id} is not eligible for {award_type}")
        key = (award_type, player_id)
        if key in seen_keys:
            warnings.append(f"duplicate selection {award_type}:{player_id}")
        seen_keys.add(key)
        award_counts[award_type] += 1

    selection_config = experiment.get("selection", {})
    slots = selection_config.get("slots", {})
    optional_slots = {str(item) for item in selection_config.get("optional_slots", [])}
    for award_type, expected_count in slots.items():
        if award_counts[award_type] > int(expected_count):
            warnings.append(f"{award_type} exceeds configured slots")
        if award_type not in optional_slots and award_counts[award_type] < int(expected_count):
            warnings.append(f"missing required slot {award_type}")

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
                and str(candidate.get("player_id")) not in selected_potd_ids
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
