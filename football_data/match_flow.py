from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


def build_match_flows(
    db_path: str | Path,
    *,
    match_date: str | None = None,
    match_keys: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        matches = _load_matches(conn, match_date=match_date, match_keys=match_keys)
        goals = _load_goals(conn, match_date=match_date, match_keys=match_keys)
    finally:
        conn.close()

    goals_by_match: dict[str, list[dict[str, Any]]] = {}
    for goal in goals:
        goals_by_match.setdefault(str(goal["match_key"]), []).append(goal)
    return {
        str(match["match_key"]): _build_match_flow(match, goals_by_match.get(str(match["match_key"]), []))
        for match in matches
    }


def player_flow_impacts(
    match_flows: dict[str, dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, int]]:
    impacts: dict[tuple[str, str, str], dict[str, int]] = {}
    tag_metric_map = {
        "opening_goal": "opening_goal",
        "equalizer": "equalizing_goal",
        "go_ahead_goal": "go_ahead_goal",
        "match_winning_goal": "match_winning_goal",
        "late_goal": "late_goal",
        "stoppage_time_goal": "stoppage_time_goal",
        "late_match_winning_goal": "late_match_winning_goal",
        "team_came_from_behind_goal": "team_came_from_behind_goal",
        "comeback_equalizer": "comeback_equalizer",
        "comeback_winner": "comeback_winner",
    }
    for match_key, flow in match_flows.items():
        for goal in flow.get("goals", []):
            if goal.get("own_goal"):
                continue
            key = (str(match_key), str(goal["team"]), str(goal["player_name"]).upper())
            metrics = impacts.setdefault(key, {metric: 0 for metric in tag_metric_map.values()})
            for tag in goal.get("tags", []):
                metric = tag_metric_map.get(str(tag))
                if metric:
                    metrics[metric] += 1
    return impacts


def _load_matches(
    conn: sqlite3.Connection,
    *,
    match_date: str | None,
    match_keys: list[str] | None,
) -> list[sqlite3.Row]:
    where, params = _where_clause(match_date=match_date, match_keys=match_keys, table_alias="m")
    return conn.execute(
        f"""
        select m.match_key, m.match_no, m.match_date, m.home_team, m.away_team,
               m.home_score, m.away_score
        from matches m
        {where}
        order by m.match_no
        """,
        params,
    ).fetchall()


def _load_goals(
    conn: sqlite3.Connection,
    *,
    match_date: str | None,
    match_keys: list[str] | None,
) -> list[dict[str, Any]]:
    official_goals = _load_official_goal_events(
        conn,
        match_date=match_date,
        match_keys=match_keys,
    )
    if official_goals:
        return official_goals
    return _load_shot_goals(conn, match_date=match_date, match_keys=match_keys)


def _load_shot_goals(
    conn: sqlite3.Connection,
    *,
    match_date: str | None,
    match_keys: list[str] | None,
) -> list[dict[str, Any]]:
    where, params = _where_clause(match_date=match_date, match_keys=match_keys, table_alias="m")
    rows = conn.execute(
        f"""
        select s.match_key, s.team, s.player_name, s.minute, s.shot_no,
               m.home_team, m.away_team, m.home_score, m.away_score
        from shots s
        join matches m using(match_key)
        {where}
          and s.is_goal = 1
        order by s.match_key, s.minute,
                 case when s.team = m.home_team then 0 else 1 end,
                 s.shot_no
        """,
        params,
    ).fetchall()
    return [
        {
            "match_key": row["match_key"],
            "team": row["team"],
            "player_team": row["team"],
            "player_name": row["player_name"],
            "minute": int(row["minute"] or 0),
            "own_goal": False,
        }
        for row in rows
    ]


def _load_official_goal_events(
    conn: sqlite3.Connection,
    *,
    match_date: str | None,
    match_keys: list[str] | None,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "official_match_events"):
        return []
    where, params = _where_clause(match_date=match_date, match_keys=match_keys, table_alias="m")
    rows = conn.execute(
        f"""
        select e.match_key, e.event_id, e.event_type_name, e.match_minute,
               e.minute, e.stoppage_minute, e.absolute_minute, e.team_name,
               e.player_name, e.home_goals, e.away_goals, e.description,
               m.home_team, m.away_team
        from official_match_events e
        join matches m using(match_key)
        {where}
          and lower(coalesce(e.event_type_name, '')) in ('goal!', 'penalty goal', 'own goal')
          and e.home_goals is not null
          and e.away_goals is not null
        order by e.match_key, e.absolute_minute, e.event_id
        """,
        params,
    ).fetchall()
    goals: list[dict[str, Any]] = []
    scores: dict[str, tuple[int, int]] = {}
    for row in rows:
        match_key = str(row["match_key"])
        home_team = str(row["home_team"])
        away_team = str(row["away_team"])
        home_before, away_before = scores.get(match_key, (0, 0))
        home_after = int(row["home_goals"] or 0)
        away_after = int(row["away_goals"] or 0)
        event_team = str(row["team_name"] or "")
        is_own_goal = str(row["event_type_name"] or "").lower() == "own goal"
        if home_after > home_before:
            scoring_team = home_team
        elif away_after > away_before:
            scoring_team = away_team
        elif is_own_goal:
            scoring_team = away_team if event_team == home_team else home_team
        else:
            scoring_team = event_team
        player_name = str(row["player_name"] or "").strip() or _player_name_from_description(
            str(row["description"] or "")
        )
        goals.append(
            {
                "match_key": match_key,
                "team": scoring_team,
                "player_team": event_team or scoring_team,
                "player_name": player_name,
                "minute": int(row["absolute_minute"] or row["minute"] or 0),
                "own_goal": is_own_goal,
            }
        )
        scores[match_key] = (home_after, away_after)
    return goals


def _where_clause(
    *,
    match_date: str | None,
    match_keys: list[str] | None,
    table_alias: str,
) -> tuple[str, list[Any]]:
    conditions: list[str] = ["1 = 1"]
    params: list[Any] = []
    if match_date is not None:
        conditions.append(f"{table_alias}.match_date = ?")
        params.append(match_date)
    if match_keys:
        placeholders = ", ".join("?" for _ in match_keys)
        conditions.append(f"{table_alias}.match_key in ({placeholders})")
        params.extend(match_keys)
    return "where " + " and ".join(conditions), params


def _build_match_flow(match: sqlite3.Row, goals: list[dict[str, Any]]) -> dict[str, Any]:
    home_team = str(match["home_team"])
    away_team = str(match["away_team"])
    home_final = int(match["home_score"] or 0)
    away_final = int(match["away_score"] or 0)
    winner_team = _winner_team(home_team, away_team, home_final, away_final)

    home_goals = 0
    away_goals = 0
    home_trailing = False
    away_trailing = False
    team_trailing_seen: dict[str, bool] = {home_team: False, away_team: False}
    built_goals: list[dict[str, Any]] = []

    for index, goal in enumerate(goals, start=1):
        team = str(goal["team"])
        home_before = home_goals
        away_before = away_goals
        team_before = home_before if team == home_team else away_before
        opponent_before = away_before if team == home_team else home_before
        if team_before < opponent_before:
            team_trailing_seen[team] = True
        if home_before < away_before:
            home_trailing = True
        if away_before < home_before:
            away_trailing = True

        if team == home_team:
            home_goals += 1
        else:
            away_goals += 1

        home_after = home_goals
        away_after = away_goals
        team_after = home_after if team == home_team else away_after
        opponent_after = away_after if team == home_team else home_after
        if home_after < away_after:
            home_trailing = True
        if away_after < home_after:
            away_trailing = True

        tags = _goal_tags(
            goal_order=index,
            minute=int(goal["minute"] or 0),
            team=team,
            winner_team=winner_team,
            team_before=team_before,
            opponent_before=opponent_before,
            team_after=team_after,
            opponent_after=opponent_after,
            team_final=home_final if team == home_team else away_final,
            opponent_final=away_final if team == home_team else home_final,
            team_trailing_seen=team_trailing_seen[team],
        )
        built_goals.append(
            {
                "goal_order": index,
                "minute": int(goal["minute"] or 0),
                "team": team,
                "player_team": str(goal.get("player_team") or team),
                "player_name": str(goal["player_name"]),
                "own_goal": bool(goal.get("own_goal")),
                "score_before": f"{home_before}-{away_before}",
                "score_after": f"{home_after}-{away_after}",
                "team_score_before": team_before,
                "opponent_score_before": opponent_before,
                "team_score_after": team_after,
                "opponent_score_after": opponent_after,
                "tags": tags,
            }
        )

    decisive_goal = next(
        (goal for goal in built_goals if "match_winning_goal" in goal["tags"]),
        None,
    )
    return {
        "match_key": str(match["match_key"]),
        "match_no": int(match["match_no"]),
        "match_date": str(match["match_date"]),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_final,
        "away_score": away_final,
        "winner_team": winner_team,
        "home_trailing_at_any_point": home_trailing,
        "away_trailing_at_any_point": away_trailing,
        "home_came_from_behind_to_win": winner_team == home_team and home_trailing,
        "away_came_from_behind_to_win": winner_team == away_team and away_trailing,
        "goals": built_goals,
        "decisive_goal": decisive_goal,
    }


def _goal_tags(
    *,
    goal_order: int,
    minute: int,
    team: str,
    winner_team: str | None,
    team_before: int,
    opponent_before: int,
    team_after: int,
    opponent_after: int,
    team_final: int,
    opponent_final: int,
    team_trailing_seen: bool,
) -> list[str]:
    tags: list[str] = []
    if goal_order == 1:
        tags.append("opening_goal")
    if team_before < opponent_before and team_after == opponent_after:
        tags.append("equalizer")
        tags.append("comeback_equalizer")
    if team_before <= opponent_before and team_after > opponent_after:
        tags.append("go_ahead_goal")
    final_margin = team_final - opponent_final
    is_contextual_winner = final_margin == 1 or team_trailing_seen
    if winner_team == team and team_after == opponent_final + 1 and is_contextual_winner:
        tags.append("match_winning_goal")
    if minute >= 75:
        tags.append("late_goal")
    if minute >= 90:
        tags.append("stoppage_time_goal")
    if "match_winning_goal" in tags and minute >= 85:
        tags.append("late_match_winning_goal")
    if winner_team == team and team_trailing_seen:
        tags.append("team_came_from_behind_goal")
    if "match_winning_goal" in tags and winner_team == team and team_trailing_seen:
        tags.append("comeback_winner")
    return tags


def _winner_team(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> str | None:
    if home_score > away_score:
        return home_team
    if away_score > home_score:
        return away_team
    return None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _player_name_from_description(description: str) -> str:
    match = re.match(
        r"(.+?) \([^)]+\) (?:scores|successfully converts the penalty)",
        description.strip(),
    )
    if match:
        return match.group(1).strip()
    return ""
