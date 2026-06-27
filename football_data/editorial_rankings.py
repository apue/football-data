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
    row_dict,
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
        players.extend(
            _public_player(score_player(row, scoring, flow_impacts=flow_impacts))
            for row in _timeline_only_player_rows(conn, match_date, players)
        )
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
    timeline_player_id = str(player.get("timeline_player_id") or "").strip()
    if timeline_player_id and player.get("player_no") is None:
        return f"{player['match_key']}|{player['team']}|timeline:{timeline_player_id}"
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
        "timeline_player_id",
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
        "data_sources",
    ]
    return {key: player.get(key) for key in keys if key in player}


def _timeline_only_player_rows(
    conn: sqlite3.Connection,
    match_date: str,
    players: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known_players = {
        (
            str(player.get("match_key") or ""),
            str(player.get("team") or ""),
            str(player.get("player_name") or "").upper(),
        )
        for player in players
    }
    events = conn.execute(
        """
        select
          g.match_key,
          g.fifa_match_id,
          g.team_name,
          g.scorer_player_id,
          g.scorer_name,
          g.assister_player_id,
          g.assister_name,
          m.match_no,
          m.match_date,
          m.home_team,
          m.away_team,
          m.home_score,
          m.away_score
        from goal_involvements g
        join matches m using(match_key)
        where m.match_date = ?
        order by g.match_key, g.goal_order
        """,
        (match_date,),
    ).fetchall()
    if not events:
        return []

    shot_totals = _shot_totals_by_player(conn, match_date)
    team_contexts = _team_contexts(conn, match_date)
    players_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in events:
        match = row_dict(row)
        team = str(match.get("team_name") or "")
        if not team:
            continue
        scorer_name = str(match.get("scorer_name") or "").strip()
        if scorer_name:
            player = _timeline_only_player(
                match=match,
                team=team,
                player_name=scorer_name,
                timeline_player_id=match.get("scorer_player_id"),
                known_players=known_players,
                players_by_key=players_by_key,
                team_contexts=team_contexts,
                shot_totals=shot_totals,
            )
            if player is not None:
                player["goals"] += 1
        assister_name = str(match.get("assister_name") or "").strip()
        if assister_name:
            player = _timeline_only_player(
                match=match,
                team=team,
                player_name=assister_name,
                timeline_player_id=match.get("assister_player_id"),
                known_players=known_players,
                players_by_key=players_by_key,
                team_contexts=team_contexts,
                shot_totals=shot_totals,
            )
            if player is not None:
                player["assists"] += 1

    for player in players_by_key.values():
        goals = int(player.get("goals") or 0)
        assists = int(player.get("assists") or 0)
        shots = int(player.get("shots") or 0)
        on_target = int(player.get("on_target") or 0)
        player["shots"] = max(shots, goals)
        player["on_target"] = max(on_target, goals)
        player["goal_involvements"] = goals + assists
        player["brace"] = 1 if goals >= 2 else 0
        player["hat_trick"] = 1 if goals >= 3 else 0
        player["only_goal_winner"] = 1 if goals and _only_goal_winner(player) else 0
    return list(players_by_key.values())


def _timeline_only_player(
    *,
    match: dict[str, Any],
    team: str,
    player_name: str,
    timeline_player_id: Any,
    known_players: set[tuple[str, str, str]],
    players_by_key: dict[tuple[str, str, str], dict[str, Any]],
    team_contexts: dict[tuple[str, str], dict[str, Any]],
    shot_totals: dict[tuple[str, str, str], dict[str, int]],
) -> dict[str, Any] | None:
    match_key = str(match["match_key"])
    name_key = player_name.upper()
    key = (match_key, team, name_key)
    if key in known_players:
        return None
    if key in players_by_key:
        return players_by_key[key]
    home_team = str(match["home_team"])
    away_team = str(match["away_team"])
    opponent = away_team if team == home_team else home_team
    team_final_goals = int(match["home_score"] if team == home_team else match["away_score"] or 0)
    opponent_final_goals = int(match["away_score"] if team == home_team else match["home_score"] or 0)
    team_context = team_contexts.get((match_key, team), {})
    opponent_context = team_contexts.get((match_key, opponent), {})
    shots = shot_totals.get(key, {})
    timeline_id = str(timeline_player_id or "").strip()
    player = {
        "match_key": match_key,
        "match_no": int(match["match_no"]),
        "match_date": str(match["match_date"]),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": int(match["home_score"] or 0),
        "away_score": int(match["away_score"] or 0),
        "opponent": opponent,
        "team_final_goals": team_final_goals,
        "opponent_final_goals": opponent_final_goals,
        "team_xg": float(team_context.get("xg") or 0),
        "team_attempts_total": int(team_context.get("attempts_total") or 0),
        "team_attempts_on_target": int(team_context.get("attempts_on_target") or 0),
        "opponent_xg": float(opponent_context.get("xg") or 0),
        "opponent_attempts_total": int(opponent_context.get("attempts_total") or 0),
        "opponent_attempts_on_target": int(opponent_context.get("attempts_on_target") or 0),
        "clean_sheet": 1 if opponent_final_goals == 0 else 0,
        "keeper_saved_shots": 0,
        "team": team,
        "player_no": None,
        "timeline_player_id": timeline_id or None,
        "player_name": player_name,
        "position": None,
        "roster_status": "timeline_only",
        "started": None,
        "shots": int(shots.get("shots") or 0),
        "on_target": int(shots.get("on_target") or 0),
        "goals": 0,
        "assists": 0,
        "goal_involvements": 0,
        "brace": 0,
        "hat_trick": 0,
        "substitute_goal": 0,
        "substitute_brace": 0,
        "only_goal_winner": 0,
        "opening_goal": 0,
        "equalizing_goal": 0,
        "go_ahead_goal": 0,
        "match_winning_goal": 0,
        "late_goal": 0,
        "stoppage_time_goal": 0,
        "late_match_winning_goal": 0,
        "team_came_from_behind_goal": 0,
        "comeback_equalizer": 0,
        "comeback_winner": 0,
        "total_offers": 0,
        "offers_received": 0,
        "in_behind": 0,
        "in_between": 0,
        "passes_completed": 0,
        "line_breaks_completed": 0,
        "units_4_attacking_line": 0,
        "units_4_attacking_midfield_line": 0,
        "units_4_midfield_line": 0,
        "units_4_defensive_line": 0,
        "units_3_attacking_line": 0,
        "units_3_midfield_line": 0,
        "units_3_defensive_line": 0,
        "units_2_midfield_line": 0,
        "units_2_defensive_line": 0,
        "direction_through": 0,
        "direction_around": 0,
        "direction_over": 0,
        "distribution_pass": 0,
        "distribution_cross": 0,
        "distribution_ball_progression": 0,
        "ball_progressions": 0,
        "take_ons": 0,
        "step_ins": 0,
        "tackles_won": 0,
        "interceptions": 0,
        "blocks": 0,
        "possession_regains": 0,
        "possession_interrupted": 0,
        "pressing_direct": 0,
        "pressing_indirect": 0,
        "clearances": 0,
        "top_speed_kmh": 0,
        "total_distance_m": 0,
        "data_sources": {
            "player_identity": "fifa_timeline_api",
            "goals_assists": "fifa_timeline_api",
            "shot_totals": "pmsr_shot_log" if shots else "fifa_timeline_api_minimum",
            "technical_physical": "unavailable_without_pmsr_player_row",
        },
    }
    players_by_key[key] = player
    return player


def _shot_totals_by_player(
    conn: sqlite3.Connection,
    match_date: str,
) -> dict[tuple[str, str, str], dict[str, int]]:
    rows = conn.execute(
        """
        select s.match_key, s.team, upper(s.player_name) as player_name,
               count(*) as shots,
               sum(s.is_on_target) as on_target
        from shots s
        join matches m using(match_key)
        where m.match_date = ?
        group by s.match_key, s.team, upper(s.player_name)
        """,
        (match_date,),
    ).fetchall()
    return {
        (str(row["match_key"]), str(row["team"]), str(row["player_name"])): {
            "shots": int(row["shots"] or 0),
            "on_target": int(row["on_target"] or 0),
        }
        for row in rows
    }


def _team_contexts(
    conn: sqlite3.Connection,
    match_date: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    rows = conn.execute(
        """
        select ts.match_key, ts.team, ts.xg, ts.attempts_total, ts.attempts_on_target
        from team_match_stats ts
        join matches m using(match_key)
        where m.match_date = ?
        """,
        (match_date,),
    ).fetchall()
    return {
        (str(row["match_key"]), str(row["team"])): row_dict(row)
        for row in rows
    }


def _only_goal_winner(player: dict[str, Any]) -> bool:
    team_goals = int(player.get("team_final_goals") or 0)
    opponent_goals = int(player.get("opponent_final_goals") or 0)
    return team_goals == 1 and opponent_goals == 0


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
