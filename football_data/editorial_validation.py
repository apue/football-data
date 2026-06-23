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
        if award_type not in candidate.get("eligible_awards", []):
            warnings.append(f"{player_id} is not eligible for {award_type}")
        if award_type == "progression_pick" and not _progression_pick_publishable(candidate):
            warnings.append(f"{player_id} has thin or pass-only progression evidence")
        if award_type == "goalkeeper_watch" and not _goalkeeper_watch_publishable(candidate):
            warnings.append(f"{player_id} is not a publishable goalkeeper-watch profile")
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

    selection_config = experiment.get("selection", {})
    slots = selection_config.get("slots", {})
    optional_slots = {str(item) for item in selection_config.get("optional_slots", [])}
    for award_type, expected_count in slots.items():
        if award_counts[award_type] > int(expected_count):
            warnings.append(f"{award_type} exceeds configured slots")
        if award_type not in optional_slots and award_counts[award_type] < int(expected_count):
            warnings.append(f"missing required slot {award_type}")

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


def _progression_pick_publishable(candidate: dict[str, Any]) -> bool:
    benchmark = candidate.get("progression_benchmark") or {}
    return (
        benchmark.get("quality") in {"strong", "useful"}
        and not bool(benchmark.get("pass_only_line_break_volume"))
        and float(benchmark.get("score") or 0) >= 18.0
    )


def _goalkeeper_watch_publishable(candidate: dict[str, Any]) -> bool:
    if str(candidate.get("position") or "").upper() != "GK" or int(candidate.get("started") or 0) != 1:
        return False
    if int(candidate.get("clean_sheet") or 0) == 1:
        return (
            float(candidate.get("opponent_xg") or 0) >= 1.0
            and float(candidate.get("opponent_attempts_on_target") or 0) >= 5
        )
    return (
        float(candidate.get("opponent_xg") or 0) - float(candidate.get("opponent_final_goals") or 0) >= 0.75
        and float(candidate.get("keeper_saved_shots") or 0) >= 4
    )
