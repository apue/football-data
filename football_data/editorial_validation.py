from __future__ import annotations

from collections import Counter
from typing import Any

from football_data.editorial_constants import PUBLIC_AWARD_TYPES


_WEAK_SELECTION_TEXTS = {
    "",
    "en",
    "zh",
    "english",
    "chinese",
    "low",
    "medium",
    "high",
    "n/a",
    "na",
    "none",
    "null",
    "todo",
}
_GENERIC_REPAIR_SELECTION_RISK = (
    "low: selected player is in the candidate pool and the evidence packet supports the award."
)


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
    public_awards = set(PUBLIC_AWARD_TYPES)
    legacy_keys = {"slots", "required_slots", "optional_slots", "optional_awards", "target_public_cards"}
    for key in sorted(legacy_keys & set(selection_config)):
        warnings.append(f"selection.{key} is retired; use public_card_count and public award_limits")
    for award_type in sorted(set(award_limits) - public_awards):
        warnings.append(f"{award_type} is not an allowed public award type")
    allowed_awards = {
        award_type
        for award_type, limit in award_limits.items()
        if int(limit) > 0 and award_type in public_awards
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
        if not isinstance(item, dict):
            warnings.append("selection_decision.selected item must be an object")
            continue
        player_id = str(item.get("player_id") or "")
        award_type = str(item.get("award_type") or "")
        candidate = selectable.get(player_id)
        warnings.extend(_selected_item_content_warnings(item, player_id, candidate))
        if not candidate:
            warnings.append(f"{player_id or 'missing player'} not in candidate pool")
            continue
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

    for award_type, expected_count in award_limits.items():
        if award_counts[award_type] > int(expected_count):
            warnings.append(f"{award_type} exceeds configured award limit")
    public_card_count = _selection_public_card_count(selection_config)
    if public_card_count:
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
        return {}
    return {str(key): int(value) for key, value in raw_limits.items()}


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


def _selected_item_content_warnings(
    item: dict[str, Any],
    player_id: str,
    candidate: dict[str, Any] | None,
) -> list[str]:
    label = player_id or str(item.get("player_name") or "selected item")
    warnings: list[str] = []
    if _weak_selection_text(item.get("editorial_reason"), min_chars=20):
        warnings.append(f"{label} editorial_reason is too weak")
    if _weak_evidence_used(item.get("evidence_used"), candidate, str(item.get("award_type") or "")):
        warnings.append(f"{label} evidence_used must include meaningful evidence strings")
    if _weak_selection_text(item.get("selection_risk"), min_chars=20, reject_generic_risk=True):
        warnings.append(f"{label} selection_risk is too weak")
    return warnings


def _weak_selection_text(
    value: Any,
    *,
    min_chars: int,
    reject_generic_risk: bool = False,
) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in _WEAK_SELECTION_TEXTS:
        return True
    if reject_generic_risk and lowered == _GENERIC_REPAIR_SELECTION_RISK:
        return True
    return len(text) < min_chars


def _weak_evidence_used(
    value: Any,
    candidate: dict[str, Any] | None,
    award_type: str,
) -> bool:
    if not isinstance(value, list):
        return True
    evidence = [str(item).strip() for item in value if str(item).strip()]
    if not evidence:
        return True
    chip_set = _candidate_evidence_chip_set(candidate, award_type)
    return any(_weak_evidence_item(item, chip_set) for item in evidence)


def _weak_evidence_item(text: str, chip_set: set[str]) -> bool:
    lowered = text.lower()
    if lowered in _WEAK_SELECTION_TEXTS:
        return True
    return len(text) < 8 and lowered not in chip_set


def _candidate_evidence_chip_set(candidate: dict[str, Any] | None, award_type: str) -> set[str]:
    if not candidate:
        return set()
    award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
    chips = (award_context.get("evidence_chips") or {}).get("en")
    if not chips:
        chips = (candidate.get("evidence_chips") or {}).get("en", [])
    return {str(chip).strip().lower() for chip in chips if str(chip).strip()}
