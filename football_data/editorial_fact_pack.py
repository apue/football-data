from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_editorial_fact_pack(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    agent_runs_dir: str | Path = "agent-runs",
) -> dict[str, Any]:
    audit_dir = Path(agent_runs_dir) / match_date
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    rankings = _load_json(audit_dir / "rankings.json")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        matches = _matches_for_date(conn, match_date)
        match_keys = [str(match["match_key"]) for match in matches]
        team_stats = _team_stats(conn, match_keys)
        goal_events = _goal_events(conn, matches)
        shot_summary = _shot_summary(conn, match_keys)
    finally:
        conn.close()

    selectable = [
        _candidate_summary(candidate)
        for candidate in candidate_pool.get("selectable_candidates", [])
        if isinstance(candidate, dict)
    ]
    audit_candidates = [
        _candidate_summary(candidate)
        for candidate in candidate_pool.get("audit_candidates", [])
        if isinstance(candidate, dict)
    ]
    review_candidates = _dedupe_candidates(selectable + audit_candidates)
    fact_pack = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": match_date,
        "source_files": {
            "rankings": str(audit_dir / "rankings.json"),
            "candidate_pool": str(audit_dir / "candidate_pool.json"),
            "selector_input": str(audit_dir / "selector_input.json"),
        },
        "matches": matches,
        "goal_timeline": goal_events,
        "team_stats": team_stats,
        "shot_summary": shot_summary,
        "top_selectable_candidates": selectable[:12],
        "audit_candidates": audit_candidates[:12],
        "direct_impact_candidates": _direct_impact_candidates(selectable),
        "goalkeeper_pressure_candidates": _goalkeeper_pressure_candidates(review_candidates),
        "metric_led_high_rank_candidates": _metric_led_high_rank_candidates(review_candidates),
        "candidate_traps": _candidate_traps(review_candidates, goal_events, team_stats),
        "rank_lookup_sample": _rank_lookup_sample(candidate_pool),
        "rankings_source": {
            "scoring_version": rankings.get("scoring_version"),
            "workflow_note": "Use candidate-pool ranks as a coarse slate input, not as the final editorial decision.",
        },
    }
    return fact_pack


def write_editorial_fact_pack(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    agent_runs_dir: str | Path = "agent-runs",
) -> dict[str, Any]:
    fact_pack = build_editorial_fact_pack(
        match_date=match_date,
        db_path=db_path,
        agent_runs_dir=agent_runs_dir,
    )
    audit_dir = Path(agent_runs_dir) / match_date
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "editorial_fact_pack.json", fact_pack)
    (audit_dir / "editorial_fact_pack.md").write_text(
        render_editorial_fact_pack_markdown(fact_pack),
        encoding="utf-8",
    )
    return fact_pack


def render_editorial_fact_pack_markdown(fact_pack: dict[str, Any]) -> str:
    lines = [
        f"# Editorial Fact Pack - {fact_pack['match_date']}",
        "",
        "## Matches",
        "",
    ]
    for match in fact_pack.get("matches", []):
        lines.append(
            "- Match {match_no}: {home_team} {home_score}-{away_score} {away_team}".format(
                **match
            )
        )
    lines.extend(["", "## Goal Timeline", ""])
    for goal in fact_pack.get("goal_timeline", []):
        assist = f", assist: {goal['assister_name']}" if goal.get("assister_name") else ""
        own_goal = (
            f", own goal by {goal['own_goal_by']}"
            if goal.get("own_goal_by")
            else ""
        )
        lines.append(
            "- {match_key} {minute_display}: {scoring_team} {home_goals_after}-{away_goals_after}, "
            "{scorer_name}{assist}{own_goal}".format(**goal, assist=assist, own_goal=own_goal)
        )
    lines.extend(["", "## Direct Impact Candidates", ""])
    for candidate in fact_pack.get("direct_impact_candidates", []):
        lines.append(
            "- #{headline_rank} {player_name} ({team}): {goals}G {assists}A, "
            "winner={match_winning_goal}, only_goal={only_goal_winner}, "
            "shootout_saves={shootout_penalty_saves}".format(**candidate)
        )
    lines.extend(["", "## Goalkeeper Pressure", ""])
    for candidate in fact_pack.get("goalkeeper_pressure_candidates", []):
        lines.append(
            "- {player_name} ({team}): clean_sheet={clean_sheet}, saves={keeper_saved_shots}, "
            "shootout_saves={shootout_penalty_saves}, opp SOT={opponent_attempts_on_target}, "
            "opp xG={opponent_xg}".format(**candidate)
        )
    lines.extend(["", "## Metric-Led High-Rank Candidates", ""])
    for candidate in fact_pack.get("metric_led_high_rank_candidates", []):
        lines.append(
            "- #{headline_rank} {player_name} ({team}): no G/A, line_breaks={line_breaks_completed}, "
            "progressions={ball_progressions}, note={trap_note}".format(**candidate)
        )
    lines.extend(["", "## Audit-Only Candidates", ""])
    for candidate in fact_pack.get("audit_candidates", []):
        lines.append(
            "- {audit_type}: #{headline_rank} {player_name} ({team}), "
            "line_breaks={line_breaks_completed}, progressions={ball_progressions}, "
            "regains={possession_regains}".format(**candidate)
        )
    lines.extend(["", "## Candidate Traps", ""])
    for trap in fact_pack.get("candidate_traps", []):
        lines.append(f"- {trap['category']}: {trap['message']}")
    lines.append("")
    return "\n".join(lines)


def _matches_for_date(conn: sqlite3.Connection, match_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select match_key, match_no, match_date, home_team, away_team, home_score, away_score
        from matches
        where match_date = ?
        order by match_no
        """,
        (match_date,),
    ).fetchall()
    return [_dict(row) for row in rows]


def _team_stats(conn: sqlite3.Connection, match_keys: list[str]) -> list[dict[str, Any]]:
    if not match_keys:
        return []
    rows = conn.execute(
        f"""
        select match_key, team, opponent, goals, xg, attempts_total, attempts_on_target,
               completed_line_breaks, ball_progressions
        from team_match_stats
        where match_key in ({_placeholders(match_keys)})
        order by match_key, team
        """,
        match_keys,
    ).fetchall()
    return [_dict(row) for row in rows]


def _goal_events(
    conn: sqlite3.Connection,
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    match_keys = [str(match["match_key"]) for match in matches]
    if not match_keys:
        return []
    match_by_key = {str(match["match_key"]): match for match in matches}
    assist_lookup = _assist_lookup(conn, match_keys)
    rows = conn.execute(
        f"""
        select match_key, event_id, event_type_name, match_minute, minute,
               stoppage_minute, absolute_minute, team_name, player_name,
               home_goals, away_goals, description
        from official_match_events
        where match_key in ({_placeholders(match_keys)})
          and event_type_name in ('Goal!', 'Own goal')
        order by match_key, absolute_minute, event_id
        """,
        match_keys,
    ).fetchall()

    previous_scores: dict[str, tuple[int, int]] = {}
    events: list[dict[str, Any]] = []
    for row in rows:
        raw = _dict(row)
        match = match_by_key[str(raw["match_key"])]
        previous_home, previous_away = previous_scores.get(str(raw["match_key"]), (0, 0))
        home_after = int(raw.get("home_goals") or 0)
        away_after = int(raw.get("away_goals") or 0)
        scoring_team = str(raw.get("team_name") or "")
        if raw.get("event_type_name") == "Own goal":
            if home_after > previous_home:
                scoring_team = str(match["home_team"])
            elif away_after > previous_away:
                scoring_team = str(match["away_team"])
        previous_scores[str(raw["match_key"])] = (home_after, away_after)
        assist = assist_lookup.get(
            (
                str(raw["match_key"]),
                int(raw.get("minute") or 0),
                str(raw.get("player_name") or ""),
            )
        )
        events.append(
            {
                "match_key": raw["match_key"],
                "minute_display": raw.get("match_minute"),
                "minute": raw.get("minute"),
                "event_type": raw.get("event_type_name"),
                "scoring_team": scoring_team,
                "scorer_name": raw.get("player_name") or raw.get("description"),
                "assister_name": assist,
                "own_goal_by": raw.get("team_name") if raw.get("event_type_name") == "Own goal" else None,
                "home_goals_after": home_after,
                "away_goals_after": away_after,
                "score_before": f"{previous_home}-{previous_away}",
                "score_after": f"{home_after}-{away_after}",
                "description": raw.get("description"),
            }
        )
    return events


def _assist_lookup(
    conn: sqlite3.Connection,
    match_keys: list[str],
) -> dict[tuple[str, int, str], str | None]:
    rows = conn.execute(
        f"""
        select match_key, minute, scorer_name, assister_name
        from goal_involvements
        where match_key in ({_placeholders(match_keys)})
        """,
        match_keys,
    ).fetchall()
    return {
        (str(row["match_key"]), int(row["minute"] or 0), str(row["scorer_name"] or "")): row[
            "assister_name"
        ]
        for row in rows
    }


def _shot_summary(conn: sqlite3.Connection, match_keys: list[str]) -> list[dict[str, Any]]:
    if not match_keys:
        return []
    rows = conn.execute(
        f"""
        select match_key, team, player_name, count(*) as shots,
               sum(is_on_target) as on_target, sum(is_goal) as goals
        from shots
        where match_key in ({_placeholders(match_keys)})
        group by match_key, team, player_name
        having goals > 0 or on_target > 0
        order by match_key, goals desc, on_target desc, shots desc
        """,
        match_keys,
    ).fetchall()
    return [_dict(row) for row in rows]


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    audit_type = str(candidate.get("audit_type") or "")
    if not metrics and audit_type:
        metrics = ((candidate.get("audit_contexts") or {}).get(audit_type) or {}).get("metrics") or {}
    return {
        "player_id": candidate.get("player_id"),
        "player_name": candidate.get("player_name"),
        "team": candidate.get("team"),
        "opponent": candidate.get("opponent"),
        "match_key": candidate.get("match_key"),
        "position": candidate.get("position"),
        "headline_rank": candidate.get("headline_rank"),
        "rank_score": candidate.get("rank_score"),
        "eligible_awards": candidate.get("eligible_awards", []),
        "audit_type": candidate.get("audit_type"),
        "goals": int(candidate.get("goals") or metrics.get("goals") or 0),
        "assists": int(candidate.get("assists") or metrics.get("assists") or 0),
        "goal_involvements": int(
            candidate.get("goal_involvements") or metrics.get("goal_involvements") or 0
        ),
        "opening_goal": int(candidate.get("opening_goal") or metrics.get("opening_goal") or 0),
        "go_ahead_goal": int(candidate.get("go_ahead_goal") or metrics.get("go_ahead_goal") or 0),
        "equalizing_goal": int(candidate.get("equalizing_goal") or metrics.get("equalizing_goal") or 0),
        "match_winning_goal": int(
            candidate.get("match_winning_goal") or metrics.get("match_winning_goal") or 0
        ),
        "only_goal_winner": int(
            candidate.get("only_goal_winner") or metrics.get("only_goal_winner") or 0
        ),
        "brace": int(candidate.get("brace") or metrics.get("brace") or 0),
        "hat_trick": int(candidate.get("hat_trick") or metrics.get("hat_trick") or 0),
        "late_goal": int(candidate.get("late_goal") or metrics.get("late_goal") or 0),
        "stoppage_time_goal": int(
            candidate.get("stoppage_time_goal") or metrics.get("stoppage_time_goal") or 0
        ),
        "comeback_equalizer": int(
            candidate.get("comeback_equalizer") or metrics.get("comeback_equalizer") or 0
        ),
        "clean_sheet": int(candidate.get("clean_sheet") or metrics.get("clean_sheet") or 0),
        "keeper_saved_shots": int(candidate.get("keeper_saved_shots") or 0),
        "shootout_penalty_saves": int(
            candidate.get("shootout_penalty_saves") or metrics.get("shootout_penalty_saves") or 0
        ),
        "opponent_xg": candidate.get("opponent_xg"),
        "opponent_attempts_on_target": candidate.get("opponent_attempts_on_target"),
        "opponent_attempts_total": candidate.get("opponent_attempts_total"),
        "shots": int(candidate.get("shots") or metrics.get("shots") or 0),
        "on_target": int(candidate.get("on_target") or metrics.get("on_target") or 0),
        "line_breaks_completed": int(candidate.get("line_breaks_completed") or 0),
        "ball_progressions": int(candidate.get("ball_progressions") or 0),
        "offers_received": int(candidate.get("offers_received") or 0),
        "possession_regains": int(candidate.get("possession_regains") or 0),
        "possession_interrupted": int(candidate.get("possession_interrupted") or 0),
        "evidence_chips": candidate.get("evidence_chips", {}),
        "flow_context": candidate.get("flow_context", {}),
        "progression_benchmark": candidate.get("progression_benchmark", {}),
        "hidden_gem_profile": candidate.get("hidden_gem_profile", {}),
        "data_sources": candidate.get("data_sources", {}),
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (str(candidate.get("player_id") or ""), str(candidate.get("audit_type") or "public"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _direct_impact_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate["goals"] > 0
        or candidate["assists"] > 0
        or candidate["goal_involvements"] > 0
        or candidate["match_winning_goal"] > 0
        or candidate.get("shootout_penalty_saves", 0) > 0
    ]


def _goalkeeper_pressure_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if _is_goalkeeper_candidate(candidate)
        and (
            candidate.get("audit_type") == "goalkeeper_watch"
            or "goalkeeper_watch" in candidate.get("eligible_awards", [])
            or int(candidate.get("keeper_saved_shots") or 0) >= 4
            or int(candidate.get("shootout_penalty_saves") or 0) > 0
            or (
                int(candidate.get("clean_sheet") or 0) == 1
                and float(candidate.get("opponent_xg") or 0) >= 1.0
            )
        )
    ]


def _is_goalkeeper_candidate(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("position") or "").upper() == "GK"


def _metric_led_high_rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metric_led: list[dict[str, Any]] = []
    for candidate in candidates:
        if int(candidate.get("headline_rank") or 9999) > 12:
            continue
        if candidate["goals"] or candidate["assists"] or candidate["goal_involvements"]:
            continue
        copy = dict(candidate)
        copy["trap_note"] = "high candidate-pool rank without direct goal involvement"
        metric_led.append(copy)
    return metric_led


def _candidate_traps(
    candidates: list[dict[str, Any]],
    goal_events: list[dict[str, Any]],
    team_stats: list[dict[str, Any]],
) -> list[dict[str, str]]:
    traps: list[dict[str, str]] = []
    for goal in goal_events:
        if goal.get("own_goal_by"):
            traps.append(
                {
                    "category": "own_goal_context",
                    "message": (
                        f"{goal['match_key']} includes an own goal by {goal['own_goal_by']} "
                        f"for {goal['scoring_team']} at {goal['minute_display']}."
                    ),
                }
            )
    for candidate in candidates:
        if candidate["goals"] > 0 and not candidate["match_winning_goal"] and not candidate["opening_goal"]:
            traps.append(
                {
                    "category": "non_winning_goal",
                    "message": (
                        f"{candidate['player_name']} scored for {candidate['team']} but the packet "
                        "does not tag it as opening or match-winning; verify score context before copy."
                    ),
                }
            )
    for candidate in _metric_led_high_rank_candidates(candidates):
        traps.append(
            {
                "category": "metric_led_candidate",
                "message": (
                    f"{candidate['player_name']} ranks #{candidate['headline_rank']} without G/A; "
                    "do not promote line breaks, offers, or movement over clearer direct impact unless reviewed."
                ),
            }
        )
    high_pressure_by_match = {
        (str(stat["match_key"]), str(stat["team"])): stat
        for stat in team_stats
        if float(stat.get("xg") or 0) >= 2.0 or int(stat.get("attempts_total") or 0) >= 25
    }
    for (match_key, team), stat in high_pressure_by_match.items():
        traps.append(
            {
                "category": "goalkeeper_pressure_check",
                "message": (
                    f"{team} produced {stat.get('attempts_total')} attempts and {stat.get('xg')} xG "
                    f"in {match_key}; check the opposing goalkeeper before ignoring a keeper card."
                ),
            }
        )
    return traps


def _rank_lookup_sample(candidate_pool: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = candidate_pool.get("rank_lookup")
    if not isinstance(lookup, dict):
        return []
    sample: list[dict[str, Any]] = []
    for player_id, ranks in list(lookup.items())[:20]:
        item = {"player_id": player_id}
        if isinstance(ranks, dict):
            item.update(ranks)
        sample.append(item)
    return sample


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing editorial packet file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)
