from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from football_data.metric_benchmarks import hidden_gem_profile, progression_benchmark


def load_scoring_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("version") != "v0.4":
        raise ValueError(f"Unsupported scoring config version: {config.get('version')}")
    return config


def latest_match_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("select max(match_date) from matches").fetchone()
    if row is None or row[0] is None:
        raise ValueError("No matches available for editorial generation")
    return str(row[0])


def matches_for_date(conn: sqlite3.Connection, match_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select match_key, match_no, match_date, kickoff_time, stadium,
               home_team, away_team, home_score, away_score
        from matches
        where match_date = ?
        order by match_no
        """,
        (match_date,),
    ).fetchall()
    return [row_dict(row) for row in rows]


def player_rows_for_date(conn: sqlite3.Connection, match_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        with shot_totals as (
          select match_key, team, upper(player_name) as player_name,
                 count(*) as shots,
                 sum(is_on_target) as on_target,
                 sum(case when outcome like '% - Goal' then 1 else 0 end) as goals
          from shots
          group by match_key, team, upper(player_name)
        ),
        assist_totals as (
          select match_key,
                 team_name as team,
                 upper(assister_name) as player_name,
                 count(*) as assists
          from goal_involvements
          where assister_name is not null
          group by match_key, team_name, upper(assister_name)
        ),
        official_scorer_totals as (
          select match_key,
                 team_name as team,
                 upper(scorer_name) as player_name,
                 count(*) as goals
          from goal_involvements
          where scorer_name is not null
          group by match_key, team_name, upper(scorer_name)
        ),
        goal_rows as (
          select
            s.match_key,
            s.team,
            upper(s.player_name) as player_name,
            s.minute,
            s.shot_no,
            m.home_team,
            m.away_team,
            m.home_score,
            m.away_score,
            case when s.team = m.home_team then m.away_team else m.home_team end as opponent,
            case when s.team = m.home_team then m.home_score else m.away_score end as team_final_goals,
            case when s.team = m.home_team then m.away_score else m.home_score end as opponent_final_goals,
            row_number() over (
              partition by s.match_key
              order by s.minute, case when s.team = m.home_team then 0 else 1 end, s.shot_no
            ) as goal_order
          from shots s
          join matches m using(match_key)
          where s.outcome like '% - Goal'
        ),
        goal_states as (
          select
            g.match_key,
            g.team,
            g.player_name,
            g.minute,
            g.team_final_goals,
            g.opponent_final_goals,
            coalesce(sum(case when prev.team = g.team then 1 else 0 end), 0) as team_goals_before,
            coalesce(sum(case when prev.team = g.opponent then 1 else 0 end), 0) as opponent_goals_before
          from goal_rows g
          left join goal_rows prev
            on prev.match_key = g.match_key
           and prev.goal_order < g.goal_order
          group by
            g.match_key,
            g.team,
            g.player_name,
            g.opponent,
            g.minute,
            g.goal_order,
            g.team_final_goals,
            g.opponent_final_goals
        ),
        goal_impacts as (
          select
            match_key,
            team,
            player_name,
            sum(case when team_goals_before = 0 and opponent_goals_before = 0 then 1 else 0 end) as opening_goal,
            sum(case when team_goals_before < opponent_goals_before and team_goals_before + 1 = opponent_goals_before then 1 else 0 end) as equalizing_goal,
            sum(case when team_goals_before <= opponent_goals_before and team_goals_before + 1 > opponent_goals_before then 1 else 0 end) as go_ahead_goal,
            sum(
              case
                when team_final_goals > opponent_final_goals
                 and team_goals_before + 1 = opponent_final_goals + 1
                 and (
                   team_final_goals - opponent_final_goals = 1
                   or team_goals_before < opponent_goals_before
                 )
                then 1 else 0
              end
            ) as match_winning_goal,
            sum(case when minute >= 75 then 1 else 0 end) as late_goal,
            sum(case when minute >= 90 then 1 else 0 end) as stoppage_time_goal,
            sum(
              case
                when minute >= 85
                 and team_final_goals > opponent_final_goals
                 and team_goals_before + 1 = opponent_final_goals + 1
                 and (
                   team_final_goals - opponent_final_goals = 1
                   or team_goals_before < opponent_goals_before
                 )
                then 1 else 0
              end
            ) as late_match_winning_goal
          from goal_states
          group by match_key, team, player_name
        ),
        saved_shot_totals as (
          select
            match_key,
            team as shooting_team,
            count(*) as saved_shots
          from shots
          where outcome like '%Saved%'
          group by match_key, team
        ),
        shootout_saved_penalty_totals as (
          select
            match_key,
            penalty_keeper_team_name as keeper_team,
            upper(penalty_keeper_name) as keeper_name,
            count(*) as shootout_penalty_saves
          from official_match_events
          where period = 11
            and penalty_result = 'missed'
            and penalty_miss_type = 'saved'
            and penalty_keeper_team_name is not null
            and penalty_keeper_name is not null
          group by match_key, keeper_team, keeper_name
        )
        select
          m.match_key,
          m.match_no,
          m.match_date,
          m.home_team,
          m.away_team,
          m.home_score,
          m.away_score,
          case when a.team = m.home_team then m.away_team else m.home_team end as opponent,
          case when a.team = m.home_team then m.home_score else m.away_score end as team_final_goals,
          case when a.team = m.home_team then m.away_score else m.home_score end as opponent_final_goals,
          coalesce(ts.xg, 0) as team_xg,
          coalesce(ts.attempts_total, 0) as team_attempts_total,
          coalesce(ts.attempts_on_target, 0) as team_attempts_on_target,
          coalesce(ots.xg, 0) as opponent_xg,
          coalesce(ots.attempts_total, 0) as opponent_attempts_total,
          coalesce(ots.attempts_on_target, 0) as opponent_attempts_on_target,
          case when (case when a.team = m.home_team then m.away_score else m.home_score end) = 0 then 1 else 0 end as clean_sheet,
          coalesce(kss.saved_shots, 0) as keeper_saved_shots,
          coalesce(sps.shootout_penalty_saves, 0) as shootout_penalty_saves,
          a.team,
          a.player_no,
          a.player_name,
          a.position,
          a.roster_status,
          a.started,
          coalesce(s.shots, d.attempts_at_goal, 0) as shots,
          coalesce(s.on_target, 0) as on_target,
          coalesce(os.goals, s.goals, d.goals, 0) as goals,
          coalesce(ast.assists, 0) as assists,
          coalesce(os.goals, s.goals, d.goals, 0) + coalesce(ast.assists, 0) as goal_involvements,
          case when coalesce(os.goals, s.goals, d.goals, 0) >= 2 then 1 else 0 end as brace,
          case when coalesce(os.goals, s.goals, d.goals, 0) >= 3 then 1 else 0 end as hat_trick,
          case when a.started = 0 then coalesce(os.goals, s.goals, d.goals, 0) else 0 end as substitute_goal,
          case when a.started = 0 and coalesce(os.goals, s.goals, d.goals, 0) >= 2 then 1 else 0 end as substitute_brace,
          case
            when coalesce(os.goals, s.goals, d.goals, 0) > 0
             and (
               (a.team = m.home_team and m.home_score = 1 and m.away_score = 0)
               or (a.team = m.away_team and m.away_score = 1 and m.home_score = 0)
             )
            then 1 else 0
          end as only_goal_winner,
          coalesce(g.opening_goal, 0) as opening_goal,
          coalesce(g.equalizing_goal, 0) as equalizing_goal,
          coalesce(g.go_ahead_goal, 0) as go_ahead_goal,
          coalesce(g.match_winning_goal, 0) as match_winning_goal,
          coalesce(g.late_goal, 0) as late_goal,
          coalesce(g.stoppage_time_goal, 0) as stoppage_time_goal,
          coalesce(g.late_match_winning_goal, 0) as late_match_winning_goal,
          coalesce(o.total_offers, 0) as total_offers,
          coalesce(o.offers_received, 0) as offers_received,
          coalesce(o.in_behind, 0) as in_behind,
          coalesce(o.in_between, 0) as in_between,
          coalesce(d.passes_completed, 0) as passes_completed,
          coalesce(d.line_breaks_completed, 0) as line_breaks_completed,
          coalesce(lb.units_4_attacking_line, 0) as units_4_attacking_line,
          coalesce(lb.units_4_attacking_midfield_line, 0) as units_4_attacking_midfield_line,
          coalesce(lb.units_4_midfield_line, 0) as units_4_midfield_line,
          coalesce(lb.units_4_defensive_line, 0) as units_4_defensive_line,
          coalesce(lb.units_3_attacking_line, 0) as units_3_attacking_line,
          coalesce(lb.units_3_midfield_line, 0) as units_3_midfield_line,
          coalesce(lb.units_3_defensive_line, 0) as units_3_defensive_line,
          coalesce(lb.units_2_midfield_line, 0) as units_2_midfield_line,
          coalesce(lb.units_2_defensive_line, 0) as units_2_defensive_line,
          coalesce(lb.direction_through, 0) as direction_through,
          coalesce(lb.direction_around, 0) as direction_around,
          coalesce(lb.direction_over, 0) as direction_over,
          coalesce(lb.distribution_pass, 0) as distribution_pass,
          coalesce(lb.distribution_cross, 0) as distribution_cross,
          coalesce(lb.distribution_ball_progression, 0) as distribution_ball_progression,
          coalesce(d.ball_progressions, 0) as ball_progressions,
          coalesce(d.take_ons, 0) as take_ons,
          coalesce(d.step_ins, 0) as step_ins,
          coalesce(x.tackles_won, 0) as tackles_won,
          coalesce(x.interceptions, 0) as interceptions,
          coalesce(x.blocks, 0) as blocks,
          coalesce(x.possession_regains, 0) as possession_regains,
          coalesce(x.possession_interrupted, 0) as possession_interrupted,
          coalesce(x.pressing_direct, 0) as pressing_direct,
          coalesce(x.pressing_indirect, 0) as pressing_indirect,
          coalesce(x.clearances, 0) as clearances,
          coalesce(p.top_speed_kmh, 0) as top_speed_kmh,
          coalesce(p.total_distance_m, 0) as total_distance_m
        from player_appearances a
        join matches m using(match_key)
        left join player_in_possession_distributions d
          on d.match_key = a.match_key
         and d.team = a.team
         and d.player_no = a.player_no
        left join player_line_breaks lb
          on lb.match_key = a.match_key
         and lb.team = a.team
         and lb.player_no = a.player_no
        left join player_offers_receptions o
          on o.match_key = a.match_key
         and o.team = a.team
         and o.player_no = a.player_no
        left join player_defensive_actions x
          on x.match_key = a.match_key
         and x.team = a.team
         and x.player_no = a.player_no
        left join player_physical_stats p
          on p.match_key = a.match_key
         and p.team = a.team
         and p.player_no = a.player_no
        left join shot_totals s
          on s.match_key = a.match_key
         and s.team = a.team
         and s.player_name = upper(a.player_name)
        left join official_scorer_totals os
          on os.match_key = a.match_key
         and os.team = a.team
         and os.player_name = upper(a.player_name)
        left join assist_totals ast
          on ast.match_key = a.match_key
         and ast.team = a.team
         and ast.player_name = upper(a.player_name)
        left join goal_impacts g
          on g.match_key = a.match_key
         and g.team = a.team
         and g.player_name = upper(a.player_name)
        left join team_match_stats ts
          on ts.match_key = a.match_key
         and ts.team = a.team
        left join team_match_stats ots
          on ots.match_key = a.match_key
         and ots.team = case when a.team = m.home_team then m.away_team else m.home_team end
        left join saved_shot_totals kss
          on kss.match_key = a.match_key
         and kss.shooting_team = case when a.team = m.home_team then m.away_team else m.home_team end
        left join shootout_saved_penalty_totals sps
          on sps.match_key = a.match_key
         and sps.keeper_team = a.team
         and sps.keeper_name = upper(a.player_name)
        where m.match_date = ?
        """,
        (match_date,),
    ).fetchall()


def score_player(
    row: sqlite3.Row,
    scoring: dict[str, Any],
    *,
    flow_impacts: dict[tuple[str, str, str], dict[str, int]] | None = None,
) -> dict[str, Any]:
    features = row_dict(row)
    if flow_impacts:
        key = (
            str(features["match_key"]),
            str(features["team"]),
            str(features["player_name"]).upper(),
        )
        features.update(flow_impacts.get(key, {}))
    role_scores: dict[str, float] = {}
    component_map: dict[str, list[dict[str, Any]]] = {}
    for score_name, weights in scoring["scores"].items():
        if score_name == "goalkeeper" and not _is_starting_goalkeeper(features):
            role_scores[score_name] = 0.0
            component_map[score_name] = []
            continue
        components = []
        total = 0.0
        for metric, weight in weights.items():
            value = float(features.get(metric) or 0)
            contribution = value * float(weight)
            if contribution:
                components.append(
                    {
                        "metric": metric,
                        "value": clean_number(value),
                        "weight": weight,
                        "contribution": round(contribution, 2),
                    }
                )
            total += contribution
        role_scores[score_name] = round(total, 2)
        component_map[score_name] = sorted(
            components,
            key=lambda item: item["contribution"],
            reverse=True,
        )
    composite = 0.0
    for score_name, weight in scoring["composite_weights"].items():
        composite += role_scores.get(score_name, 0) * float(weight)
    headline = composite
    for score_name, weight in scoring.get("headline_weights", {}).items():
        if score_name == "composite_score":
            headline += composite * float(weight)
        else:
            headline += role_scores.get(score_name, 0) * float(weight)
    features["role_scores"] = role_scores
    features["score_components"] = component_map
    features["composite_score"] = round(composite, 2)
    features["headline_score"] = round(headline, 2)
    features["progression_benchmark"] = progression_benchmark(features)
    features["hidden_gem_profile"] = hidden_gem_profile(features)
    return features


def attach_flow_contexts(
    players: list[dict[str, Any]],
    match_flows: dict[str, dict[str, Any]],
) -> None:
    for player in players:
        player["flow_context"] = _player_flow_context(
            player,
            match_flows.get(str(player["match_key"])),
        )


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def clean_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return round(value, 2)


def _is_starting_goalkeeper(player: dict[str, Any]) -> bool:
    return str(player.get("position") or "").upper() == "GK" and int(player.get("started") or 0) == 1


def _player_flow_context(
    player: dict[str, Any],
    match_flow: dict[str, Any] | None,
) -> dict[str, Any]:
    if not match_flow:
        return {
            "goals": [],
            "allowed_claims": {"en": [], "zh": []},
            "team_came_from_behind_to_win": False,
        }
    player_name = str(player["player_name"]).upper()
    team = str(player["team"])
    goals = [
        goal
        for goal in match_flow.get("goals", [])
        if str(goal.get("team")) == team and str(goal.get("player_name", "")).upper() == player_name
    ]
    en_claims: list[str] = []
    zh_claims: list[str] = []
    team_came_from_behind_to_win = _team_came_from_behind_to_win(match_flow, team)
    if team_came_from_behind_to_win:
        _append_unique(en_claims, "comeback win")
        _append_unique(zh_claims, "逆转取胜")
    for goal in goals:
        tags = {str(tag) for tag in goal.get("tags", [])}
        minute = int(goal.get("minute") or 0)
        if "opening_goal" in tags:
            _append_unique(en_claims, "opening goal")
            _append_unique(zh_claims, "首开纪录")
        if "equalizer" in tags:
            _append_unique(en_claims, "equaliser")
            _append_unique(zh_claims, "扳平")
        if "go_ahead_goal" in tags:
            _append_unique(en_claims, "go-ahead goal")
            _append_unique(zh_claims, "取得领先")
        if "match_winning_goal" in tags:
            _append_unique(en_claims, "match-winning goal")
            _append_unique(zh_claims, "制胜球")
        if "stoppage_time_goal" in tags:
            _append_unique(en_claims, "stoppage-time goal")
            _append_unique(zh_claims, "补时进球")
        if "late_match_winning_goal" in tags:
            _append_unique(en_claims, "late winner")
            _append_unique(zh_claims, "补时制胜")
        if "comeback_winner" in tags:
            _append_unique(en_claims, "comeback winner")
            _append_unique(zh_claims, "逆转制胜")
        if "comeback_equalizer" in tags:
            _append_unique(en_claims, "comeback equaliser")
            _append_unique(zh_claims, "逆转过程中的扳平球")
            _append_unique(zh_claims, "逆转扳平")
        if "stoppage_time_goal" in tags and "match_winning_goal" in tags:
            _append_unique(en_claims, f"{minute}' stoppage-time winner")
            _append_unique(zh_claims, f"{minute}' 补时制胜")
        elif "match_winning_goal" in tags:
            _append_unique(en_claims, f"{minute}' winner")
            _append_unique(zh_claims, f"{minute}' 制胜")
        elif "equalizer" in tags:
            _append_unique(en_claims, f"{minute}' equaliser")
            _append_unique(zh_claims, f"{minute}' 扳平")
    return {
        "match_key": match_flow["match_key"],
        "team_came_from_behind_to_win": team_came_from_behind_to_win,
        "allowed_claims": {"en": en_claims, "zh": zh_claims},
        "goals": goals,
        "decisive_goal": next(
            (goal for goal in goals if "match_winning_goal" in goal.get("tags", [])),
            None,
        ),
    }


def _team_came_from_behind_to_win(match_flow: dict[str, Any], team: str) -> bool:
    if team == match_flow.get("home_team"):
        return bool(match_flow.get("home_came_from_behind_to_win"))
    if team == match_flow.get("away_team"):
        return bool(match_flow.get("away_came_from_behind_to_win"))
    return False


def _append_unique(items: list[str], item: str) -> None:
    if item and item not in items:
        items.append(item)
