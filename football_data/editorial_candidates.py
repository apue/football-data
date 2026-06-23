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
        if award_type == "progression_pick":
            role_items = _progression_candidates(players_by_id, pool_config)[:role_top_n]
        elif award_type == "goalkeeper_watch":
            role_items = _goalkeeper_watch_candidates(players_by_id, pool_config)[:role_top_n]
        else:
            role_items = roles.get(role, [])[:role_top_n]
        for item in role_items:
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
            and int(player.get("goal_involvements") or 0) == 0
            and int(player.get("headline_rank") or 9999) > potd_top_n
            and not _heavy_loss(player)
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


def _progression_candidates(
    players_by_id: dict[str, dict[str, Any]],
    pool_config: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed_quality = {
        str(item)
        for item in pool_config.get("progression_allowed_quality", ["strong", "useful"])
    }
    min_score = float(pool_config.get("progression_min_benchmark_score", 18.0))
    exclude_pass_only = bool(pool_config.get("exclude_pass_only_progression", True))
    candidates = [
        player
        for player in players_by_id.values()
        if str(player.get("position") or "").upper() != "GK"
        and int(player.get("goal_involvements") or 0) == 0
        and (player.get("progression_benchmark") or {}).get("quality") in allowed_quality
        and float((player.get("progression_benchmark") or {}).get("score") or 0) >= min_score
        and (
            not exclude_pass_only
            or not bool((player.get("progression_benchmark") or {}).get("pass_only_line_break_volume"))
        )
    ]
    return sorted(
        (_with_rank_score(player, (player.get("progression_benchmark") or {}).get("score")) for player in candidates),
        key=lambda player: (
            float((player.get("progression_benchmark") or {}).get("score") or 0),
            float((player.get("role_scores") or {}).get("progressor") or 0),
            -int(player.get("headline_rank") or 9999),
        ),
        reverse=True,
    )


def _goalkeeper_watch_candidates(
    players_by_id: dict[str, dict[str, Any]],
    pool_config: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = [
        player
        for player in players_by_id.values()
        if _goalkeeper_watch_publishable(player, pool_config)
    ]
    return sorted(
        (_with_rank_score(player, (player.get("role_scores") or {}).get("goalkeeper")) for player in candidates),
        key=lambda player: (
            float((player.get("role_scores") or {}).get("goalkeeper") or 0),
            float(player.get("opponent_xg") or 0),
            float(player.get("opponent_attempts_on_target") or 0),
        ),
        reverse=True,
    )


def _goalkeeper_watch_publishable(player: dict[str, Any], pool_config: dict[str, Any]) -> bool:
    policy = pool_config.get("goalkeeper_watch_policy")
    if not isinstance(policy, dict):
        policy = {}
    if str(player.get("position") or "").upper() != "GK" or int(player.get("started") or 0) != 1:
        return False
    score = float((player.get("role_scores") or {}).get("goalkeeper") or 0)
    if score < float(policy.get("min_goalkeeper_score", 35.0)):
        return False
    opponent_xg = float(player.get("opponent_xg") or 0)
    opponent_sot = float(player.get("opponent_attempts_on_target") or 0)
    saved_shots = float(player.get("keeper_saved_shots") or 0)
    goals_against = float(player.get("opponent_final_goals") or 0)
    clean_sheet_case = (
        bool(player.get("clean_sheet"))
        and opponent_xg >= float(policy.get("min_opponent_xg", 1.0))
        and opponent_sot >= float(policy.get("min_opponent_on_target", 5))
    )
    prevented_case = (
        bool(policy.get("allow_goals_prevented_case", True))
        and opponent_xg - goals_against >= float(policy.get("min_goals_prevented", 0.75))
        and saved_shots >= float(policy.get("min_saved_shots", 4))
    )
    if bool(policy.get("require_clean_sheet", True)):
        return clean_sheet_case
    return clean_sheet_case or prevented_case


def _with_rank_score(player: dict[str, Any], score: Any) -> dict[str, Any]:
    item = dict(player)
    item["rank_score"] = round(float(score or 0), 2)
    return item


def _heavy_loss(player: dict[str, Any]) -> bool:
    team_goals = int(player.get("team_final_goals") or 0)
    opponent_goals = int(player.get("opponent_final_goals") or 0)
    return opponent_goals >= 3 and team_goals - opponent_goals <= -2


def _add_candidate(
    candidates: dict[str, dict[str, Any]],
    players_by_id: dict[str, dict[str, Any]],
    source: dict[str, Any],
    award_type: str,
    reason: str,
) -> None:
    player_id = str(source["player_id"])
    player = dict(players_by_id.get(player_id, source))
    if "rank_score" in source:
        player["rank_score"] = source["rank_score"]
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
