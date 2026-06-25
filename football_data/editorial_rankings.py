from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from football_data.editorial_evidence import choice_metrics, evidence_chips
from football_data.editorial_scoring import (
    attach_flow_contexts,
    load_scoring_config,
    matches_for_date,
    player_rows_for_date,
    score_player,
)
from football_data.match_flow import build_match_flows, player_flow_impacts


ROLE_NAMES = [
    "impact",
    "progressor",
    "off_ball",
    "defensive",
    "goalkeeper",
    "attacking_threat",
]


def build_editorial_rankings(
    db_path: str | Path,
    match_date: str,
    scoring_config_path: str | Path,
) -> dict[str, Any]:
    scoring = load_scoring_config(scoring_config_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        matches = matches_for_date(conn, match_date)
        match_flows = build_match_flows(db_path, match_date=match_date)
        flow_impacts = player_flow_impacts(match_flows)
        players = [
            _public_player(score_player(row, scoring, flow_impacts=flow_impacts))
            for row in player_rows_for_date(conn, match_date)
        ]
        attach_flow_contexts(players, match_flows)
    finally:
        conn.close()

    headline = _rank(players, "headline_score", "headline_rank")
    roles = {
        role: _rank(players, role, f"{role}_rank", role_score=True)
        for role in ROLE_NAMES
    }
    encoded_players = json.loads(json.dumps(players, ensure_ascii=False))
    return {
        "schema_version": 1,
        "match_date": match_date,
        "scoring_version": scoring["version"],
        "event_sources": {
            "goal_involvements": "fifa_timeline_api",
        },
        "matches": matches,
        "match_flows": match_flows,
        "players": encoded_players,
        "rankings": {
            "headline": headline,
            "roles": roles,
        },
    }


def player_id(player: dict[str, Any]) -> str:
    return f"{player['match_key']}|{player['team']}|{int(player['player_no'])}"


def _rank(
    players: list[dict[str, Any]],
    score_name: str,
    rank_key: str,
    *,
    role_score: bool = False,
) -> list[dict[str, Any]]:
    ranked = sorted(
        players,
        key=lambda player: _score_value(player, score_name, role_score=role_score),
        reverse=True,
    )
    public: list[dict[str, Any]] = []
    for rank, player in enumerate(ranked, start=1):
        player[rank_key] = rank
        item = _candidate_view(player)
        item[rank_key] = rank
        item["rank_score"] = round(_score_value(player, score_name, role_score=role_score), 2)
        public.append(item)
    return public


def _score_value(player: dict[str, Any], score_name: str, *, role_score: bool) -> float:
    if role_score:
        return float(player.get("role_scores", {}).get(score_name, 0) or 0)
    return float(player.get(score_name) or 0)


def _public_player(player: dict[str, Any]) -> dict[str, Any]:
    public = dict(player)
    public["player_id"] = player_id(public)
    public["score_components"] = _top_components(public)
    public["metrics"] = choice_metrics(public, "player_of_the_day")
    public["evidence_chips"] = evidence_chips(public, "player_of_the_day")
    return public


def _candidate_view(player: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "player_id",
        "match_key",
        "match_no",
        "match_date",
        "player_no",
        "player_name",
        "team",
        "opponent",
        "position",
        "started",
        "headline_score",
        "composite_score",
        "role_scores",
        "score_components",
        "metrics",
        "evidence_chips",
        "flow_context",
        "hidden_gem_profile",
        "progression_benchmark",
        "team_final_goals",
        "opponent_final_goals",
    ]
    return {key: player.get(key) for key in keys if key in player}


def _top_components(player: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for role_components in player.get("score_components", {}).values():
        if isinstance(role_components, list):
            components.extend(role_components)
    components.sort(key=lambda item: float(item.get("contribution") or 0), reverse=True)
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for component in components:
        metric = str(component.get("metric") or "")
        if not metric or metric in seen:
            continue
        seen.add(metric)
        selected.append(component)
        if len(selected) >= limit:
            break
    return selected
