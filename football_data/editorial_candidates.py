from __future__ import annotations

from typing import Any

from football_data.editorial import AWARD_LABELS, _choice_metrics, _evidence_chips


AWARD_ROLE_MAP = {
    "impact_pick": "impact",
    "progression_pick": "progressor",
    "defensive_pick": "defensive",
    "goalkeeper_watch": "goalkeeper",
}


def build_candidate_pool(
    rankings: dict[str, Any],
    pool_config: dict[str, Any],
) -> dict[str, Any]:
    players_by_id = {
        str(player["player_id"]): dict(player)
        for player in rankings.get("players", [])
    }
    candidates: dict[str, dict[str, Any]] = {}
    headline = rankings.get("rankings", {}).get("headline", [])
    potd_top_n = int(pool_config.get("potd_top_n", 8))
    for item in headline[:potd_top_n]:
        _add_candidate(candidates, players_by_id, item, "player_of_the_day", "headline_top_n")

    roles = rankings.get("rankings", {}).get("roles", {})
    role_top_n = int(pool_config.get("role_top_n", 5))
    for award_type, role in AWARD_ROLE_MAP.items():
        if award_type == "goalkeeper_watch" and not pool_config.get("include_goalkeepers", True):
            continue
        for item in roles.get(role, [])[:role_top_n]:
            if award_type == "goalkeeper_watch" and str(item.get("position") or "").upper() != "GK":
                continue
            _add_candidate(candidates, players_by_id, item, award_type, f"{role}_top_n")

    for item in roles.get("impact", [])[: int(pool_config.get("impact_top_n", 5))]:
        if float(item.get("rank_score") or 0) > 0:
            _add_candidate(candidates, players_by_id, item, "impact_pick", "impact_story")

    if pool_config.get("include_hidden_gems", True):
        hidden_players = [
            player
            for player in players_by_id.values()
            if (player.get("hidden_gem_profile") or {}).get("eligible")
            and int(player.get("goals") or 0) == 0
        ]
        hidden_players.sort(
            key=lambda player: float((player.get("hidden_gem_profile") or {}).get("score") or 0),
            reverse=True,
        )
        for player in hidden_players[:role_top_n]:
            _add_candidate(
                candidates,
                players_by_id,
                player,
                "hidden_gem",
                "hidden_gem_profile",
            )

    selectable = sorted(
        candidates.values(),
        key=lambda item: (
            int(item.get("headline_rank") or 9999),
            str(item.get("team") or ""),
            str(item.get("player_name") or ""),
        ),
    )
    near_miss_count = int(pool_config.get("near_miss_count", 8))
    selectable_ids = {str(candidate["player_id"]) for candidate in selectable}
    near_misses = [
        {
            **item,
            "reason_not_in_pool": "outside configured selectable pool",
        }
        for item in headline
        if str(item.get("player_id")) not in selectable_ids
    ][:near_miss_count]
    return {
        "schema_version": 1,
        "match_date": rankings["match_date"],
        "scoring_version": rankings["scoring_version"],
        "pool_config_id": pool_config["id"],
        "selectable_candidates": selectable,
        "near_misses": near_misses,
        "rank_lookup": {
            str(item["player_id"]): {
                "headline_rank": item.get("headline_rank"),
                "headline_score": item.get("headline_score"),
                "player_name": item.get("player_name"),
                "team": item.get("team"),
            }
            for item in headline
        },
    }


def _add_candidate(
    candidates: dict[str, dict[str, Any]],
    players_by_id: dict[str, dict[str, Any]],
    source: dict[str, Any],
    award_type: str,
    reason: str,
) -> None:
    player_id = str(source["player_id"])
    player = dict(players_by_id.get(player_id, source))
    candidate = candidates.setdefault(player_id, player)
    candidate.setdefault("eligible_awards", [])
    candidate.setdefault("pool_reasons", [])
    candidate.setdefault("award_contexts", {})
    if award_type not in candidate["eligible_awards"]:
        candidate["eligible_awards"].append(award_type)
    if reason not in candidate["pool_reasons"]:
        candidate["pool_reasons"].append(reason)
    candidate["award_contexts"][award_type] = {
        "award_label": AWARD_LABELS.get(award_type, {"en": award_type, "zh": award_type}),
        "metrics": _choice_metrics(candidate, award_type),
        "evidence_chips": _evidence_chips(candidate, award_type),
        "role_scores": candidate.get("role_scores", {}),
        "score_components": candidate.get("score_components", []),
    }
