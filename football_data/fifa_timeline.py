from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FIFA_API_BASE_URL = "https://api.fifa.com/api/v3"
FIFA_WORLD_CUP_COMPETITION_ID = "17"
FIFA_WORLD_CUP_2026_SEASON_ID = "285023"
SOURCE_NAME = "fifa_timeline_api"
GOAL_EVENT_TYPE = 0
ASSIST_EVENT_TYPE = 1
PENALTY_GOAL_EVENT_TYPE = 41
PENALTY_MISSED_EVENT_TYPES = {60, 65}
GOAL_EVENT_TYPES = {GOAL_EVENT_TYPE, PENALTY_GOAL_EVENT_TYPE}
SHOOTOUT_PERIOD = 11
DEFAULT_SHOOTOUT_OVERRIDES_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "shootout_penalty_overrides.json"
)

FetchJson = Callable[[str], Mapping[str, Any]]


def backfill_fifa_timelines(
    db_path: str | Path,
    *,
    api_base_url: str = FIFA_API_BASE_URL,
    competition_id: str = FIFA_WORLD_CUP_COMPETITION_ID,
    season_id: str = FIFA_WORLD_CUP_2026_SEASON_ID,
    language: str = "en",
    fetch_json: FetchJson | None = None,
    raise_on_error: bool = False,
    shootout_overrides_path: str | Path | None = DEFAULT_SHOOTOUT_OVERRIDES_PATH,
) -> dict[str, Any]:
    """Fetch FIFA public match timelines and store event-level goal involvements."""

    fetch = fetch_json or _fetch_json
    shootout_overrides = _load_shootout_overrides(shootout_overrides_path)
    generated_at = _utc_now()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_fifa_timeline_schema(conn)
        matches = _load_matches(conn)
        summary: dict[str, Any] = {
            "generated_at": generated_at,
            "source": SOURCE_NAME,
            "status": "success",
            "matches": len(matches),
            "linked_matches": 0,
            "timeline_matches": 0,
            "events": 0,
            "goals": 0,
            "assists": 0,
            "goal_involvements": 0,
            "failures": [],
        }
        if not matches:
            conn.commit()
            return summary

        try:
            calendar = _fetch_calendar(
                matches,
                fetch=fetch,
                api_base_url=api_base_url,
                competition_id=competition_id,
                season_id=season_id,
                language=language,
            )
        except Exception as exc:
            if raise_on_error:
                raise
            summary["status"] = "partial"
            summary["failures"].append(
                {"failure_code": "fifa_calendar_failed", "message": str(exc)}
            )
            conn.commit()
            return summary

        links = _match_links(
            matches,
            calendar,
            fetched_at=generated_at,
            api_base_url=api_base_url,
            language=language,
        )
        _replace_links(conn, links)
        linked = [link for link in links if link.get("fifa_match_id")]
        summary["linked_matches"] = len(linked)
        for link in linked:
            try:
                timeline = _fetch_timeline(
                    str(link["fifa_match_id"]),
                    fetch=fetch,
                    api_base_url=api_base_url,
                    language=language,
                )
                event_summary = _replace_timeline(
                    conn,
                    link,
                    timeline,
                    fetched_at=generated_at,
                    fetch=fetch,
                    api_base_url=api_base_url,
                    language=language,
                    shootout_overrides=shootout_overrides,
                )
                summary["timeline_matches"] += 1
                summary["events"] += event_summary["events"]
                summary["goals"] += event_summary["goals"]
                summary["assists"] += event_summary["assists"]
                summary["goal_involvements"] += event_summary["goal_involvements"]
            except Exception as exc:
                if raise_on_error:
                    raise
                summary["status"] = "partial"
                summary["failures"].append(
                    {
                        "failure_code": "fifa_timeline_failed",
                        "match_key": link["match_key"],
                        "fifa_match_id": link["fifa_match_id"],
                        "message": str(exc),
                    }
                )
        conn.commit()
        return summary
    finally:
        conn.close()


def ensure_fifa_timeline_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists fifa_match_links (
          match_key text primary key,
          fifa_match_id text,
          fifa_competition_id text,
          fifa_season_id text,
          fifa_stage_id text,
          fifa_group_id text,
          fifa_home_team_id text,
          fifa_away_team_id text,
          result_type integer,
          winner_team_id text,
          home_penalty_score integer,
          away_penalty_score integer,
          api_url text,
          fetched_at text not null,
          status text not null,
          raw_json text,
          foreign key(match_key) references matches(match_key)
        );

        create table if not exists official_match_events (
          match_key text not null,
          fifa_match_id text not null,
          event_id text not null,
          event_order integer,
          event_type integer,
          event_type_name text,
          event_timestamp text,
          period integer,
          match_minute text,
          minute integer,
          stoppage_minute integer,
          absolute_minute integer,
          team_id text,
          team_name text,
          player_id text,
          player_name text,
          related_player_id text,
          home_goals integer,
          away_goals integer,
          home_penalty_goals integer,
          away_penalty_goals integer,
          penalty_result text,
          penalty_miss_type text,
          penalty_miss_type_source text,
          penalty_keeper_player_id text,
          penalty_keeper_name text,
          penalty_keeper_team_id text,
          penalty_keeper_team_name text,
          description text,
          raw_json text not null,
          primary key(match_key, event_id),
          foreign key(match_key) references matches(match_key)
        );

        create table if not exists goal_involvements (
          match_key text not null,
          fifa_match_id text not null,
          goal_event_id text not null,
          goal_order integer not null,
          team_id text,
          team_name text,
          minute_display text,
          minute integer,
          stoppage_minute integer,
          absolute_minute integer,
          scorer_player_id text,
          scorer_name text not null,
          assist_event_id text,
          assister_player_id text,
          assister_name text,
          home_goals_after integer,
          away_goals_after integer,
          source text not null,
          raw_json text not null,
          primary key(match_key, goal_event_id),
          foreign key(match_key) references matches(match_key)
        );

        create index if not exists idx_official_match_events_type
          on official_match_events(match_key, event_type);

        create index if not exists idx_goal_involvements_assister
          on goal_involvements(match_key, assister_name);
        """
    )
    _ensure_columns(
        conn,
        "fifa_match_links",
        {
            "result_type": "integer",
            "winner_team_id": "text",
            "home_penalty_score": "integer",
            "away_penalty_score": "integer",
        },
    )
    _ensure_columns(
        conn,
        "official_match_events",
        {
            "event_order": "integer",
            "event_timestamp": "text",
            "home_penalty_goals": "integer",
            "away_penalty_goals": "integer",
            "penalty_result": "text",
            "penalty_miss_type": "text",
            "penalty_miss_type_source": "text",
            "penalty_keeper_player_id": "text",
            "penalty_keeper_name": "text",
            "penalty_keeper_team_id": "text",
            "penalty_keeper_team_name": "text",
        },
    )
    conn.execute(
        "insert or replace into meta(key, value) values(?, ?)",
        ("fifa_timeline_schema_version", "3"),
    )
    conn.execute("insert or replace into meta(key, value) values(?, ?)", ("schema_version", "7"))


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Mapping[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"alter table {table} add column {name} {definition}")


def _load_matches(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select match_key, match_no, match_date, home_team, away_team, home_score, away_score
        from matches
        order by match_no
        """
    ).fetchall()


def _fetch_calendar(
    matches: list[sqlite3.Row],
    *,
    fetch: FetchJson,
    api_base_url: str,
    competition_id: str,
    season_id: str,
    language: str,
) -> list[Mapping[str, Any]]:
    from_date, to_date = _calendar_window(matches)
    params = urllib.parse.urlencode(
        {
            "idCompetition": competition_id,
            "idSeason": season_id,
            "from": f"{from_date.isoformat()}T00:00:00Z",
            "to": f"{to_date.isoformat()}T23:59:59Z",
            "language": language,
            "count": "500",
        }
    )
    payload = fetch(f"{api_base_url.rstrip('/')}/calendar/matches?{params}")
    results = payload.get("Results", [])
    if not isinstance(results, list):
        raise ValueError("FIFA calendar response did not contain Results list")
    return results


def _calendar_window(matches: list[sqlite3.Row]) -> tuple[date, date]:
    dates = [date.fromisoformat(str(match["match_date"])) for match in matches]
    return min(dates) - timedelta(days=1), max(dates) + timedelta(days=1)


def _match_links(
    matches: list[sqlite3.Row],
    calendar: list[Mapping[str, Any]],
    *,
    fetched_at: str,
    api_base_url: str,
    language: str,
) -> list[dict[str, Any]]:
    by_match_no: dict[int, Mapping[str, Any]] = {}
    for item in calendar:
        try:
            by_match_no[int(item.get("MatchNumber"))] = item
        except (TypeError, ValueError):
            continue

    links: list[dict[str, Any]] = []
    for match in matches:
        calendar_match = by_match_no.get(int(match["match_no"]))
        status = "linked" if calendar_match else "missing"
        home = calendar_match.get("Home", {}) if calendar_match else {}
        away = calendar_match.get("Away", {}) if calendar_match else {}
        links.append(
            {
                "match_key": str(match["match_key"]),
                "fifa_match_id": _str_or_none(calendar_match.get("IdMatch") if calendar_match else None),
                "fifa_competition_id": _str_or_none(
                    calendar_match.get("IdCompetition") if calendar_match else None
                ),
                "fifa_season_id": _str_or_none(calendar_match.get("IdSeason") if calendar_match else None),
                "fifa_stage_id": _str_or_none(calendar_match.get("IdStage") if calendar_match else None),
                "fifa_group_id": _str_or_none(calendar_match.get("IdGroup") if calendar_match else None),
                "fifa_home_team_id": _str_or_none(home.get("IdTeam")),
                "fifa_away_team_id": _str_or_none(away.get("IdTeam")),
                "result_type": _int_or_none(calendar_match.get("ResultType") if calendar_match else None),
                "winner_team_id": _str_or_none(calendar_match.get("Winner") if calendar_match else None),
                "home_penalty_score": _int_or_none(
                    calendar_match.get("HomeTeamPenaltyScore") if calendar_match else None
                ),
                "away_penalty_score": _int_or_none(
                    calendar_match.get("AwayTeamPenaltyScore") if calendar_match else None
                ),
                "api_url": _timeline_url(api_base_url, str(calendar_match.get("IdMatch")), language)
                if calendar_match
                else None,
                "fetched_at": fetched_at,
                "status": status,
                "raw_json": _json(calendar_match) if calendar_match else None,
                "home_team_name": _team_name(home),
                "away_team_name": _team_name(away),
            }
        )
    return links


def _replace_links(conn: sqlite3.Connection, links: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        insert or replace into fifa_match_links(
          match_key, fifa_match_id, fifa_competition_id, fifa_season_id, fifa_stage_id,
          fifa_group_id, fifa_home_team_id, fifa_away_team_id, result_type,
          winner_team_id, home_penalty_score, away_penalty_score, api_url, fetched_at,
          status, raw_json
        ) values(
          :match_key, :fifa_match_id, :fifa_competition_id, :fifa_season_id,
          :fifa_stage_id, :fifa_group_id, :fifa_home_team_id, :fifa_away_team_id,
          :result_type, :winner_team_id, :home_penalty_score, :away_penalty_score,
          :api_url, :fetched_at, :status, :raw_json
        )
        """,
        links,
    )


def _fetch_timeline(
    fifa_match_id: str,
    *,
    fetch: FetchJson,
    api_base_url: str,
    language: str,
) -> Mapping[str, Any]:
    return fetch(_timeline_url(api_base_url, fifa_match_id, language))


def _timeline_url(api_base_url: str, fifa_match_id: str, language: str) -> str:
    params = urllib.parse.urlencode({"language": language})
    return f"{api_base_url.rstrip('/')}/timelines/{fifa_match_id}?{params}"


def _replace_timeline(
    conn: sqlite3.Connection,
    link: Mapping[str, Any],
    timeline: Mapping[str, Any],
    *,
    fetched_at: str,
    fetch: FetchJson,
    api_base_url: str,
    language: str,
    shootout_overrides: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, int]:
    match_key = str(link["match_key"])
    fifa_match_id = str(link["fifa_match_id"])
    events = timeline.get("Event", [])
    if not isinstance(events, list):
        raise ValueError("FIFA timeline response did not contain Event list")
    team_names = {
        str(link["fifa_home_team_id"]): str(link.get("home_team_name") or ""),
        str(link["fifa_away_team_id"]): str(link.get("away_team_name") or ""),
    }
    player_names = _fetch_penalty_keeper_names(
        events,
        fetch=fetch,
        api_base_url=api_base_url,
        language=language,
    )
    conn.execute("delete from goal_involvements where match_key = ?", (match_key,))
    conn.execute("delete from official_match_events where match_key = ?", (match_key,))
    event_rows = [
        _event_row(
            match_key,
            fifa_match_id,
            event,
            index=index,
            team_names=team_names,
            player_names=player_names,
            shootout_overrides=shootout_overrides,
        )
        for index, event in enumerate(events, start=1)
    ]
    conn.executemany(
        """
        insert into official_match_events(
          match_key, fifa_match_id, event_id, event_order, event_type,
          event_type_name, event_timestamp, period, match_minute, minute,
          stoppage_minute, absolute_minute, team_id, team_name, player_id,
          player_name, related_player_id, home_goals, away_goals,
          home_penalty_goals, away_penalty_goals, penalty_result,
          penalty_miss_type, penalty_miss_type_source, penalty_keeper_player_id,
          penalty_keeper_name, penalty_keeper_team_id, penalty_keeper_team_name,
          description, raw_json
        ) values(
          :match_key, :fifa_match_id, :event_id, :event_order, :event_type,
          :event_type_name, :event_timestamp, :period, :match_minute, :minute,
          :stoppage_minute, :absolute_minute, :team_id, :team_name,
          :player_id, :player_name, :related_player_id, :home_goals,
          :away_goals, :home_penalty_goals, :away_penalty_goals,
          :penalty_result, :penalty_miss_type, :penalty_miss_type_source,
          :penalty_keeper_player_id, :penalty_keeper_name,
          :penalty_keeper_team_id, :penalty_keeper_team_name,
          :description, :raw_json
        )
        """,
        event_rows,
    )
    goal_rows = _goal_involvement_rows(
        match_key=match_key,
        fifa_match_id=fifa_match_id,
        event_rows=event_rows,
    )
    conn.executemany(
        """
        insert into goal_involvements(
          match_key, fifa_match_id, goal_event_id, goal_order, team_id, team_name,
          minute_display, minute, stoppage_minute, absolute_minute,
          scorer_player_id, scorer_name, assist_event_id, assister_player_id,
          assister_name, home_goals_after, away_goals_after, source, raw_json
        ) values(
          :match_key, :fifa_match_id, :goal_event_id, :goal_order, :team_id,
          :team_name, :minute_display, :minute, :stoppage_minute, :absolute_minute,
          :scorer_player_id, :scorer_name, :assist_event_id, :assister_player_id,
          :assister_name, :home_goals_after, :away_goals_after, :source, :raw_json
        )
        """,
        goal_rows,
    )
    conn.execute(
        """
        update fifa_match_links
        set fetched_at = ?, status = ?
        where match_key = ?
        """,
        (fetched_at, "timeline_loaded", match_key),
    )
    return {
        "events": len(event_rows),
        "goals": len([row for row in event_rows if _counts_as_match_goal(row)]),
        "assists": len([row for row in event_rows if row["event_type"] == ASSIST_EVENT_TYPE]),
        "goal_involvements": len(goal_rows),
    }


def _event_row(
    match_key: str,
    fifa_match_id: str,
    event: Mapping[str, Any],
    *,
    index: int,
    team_names: Mapping[str, str],
    player_names: Mapping[str, str],
    shootout_overrides: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    event_type = _int_or_none(event.get("Type"))
    match_minute = _str_or_none(event.get("MatchMinute"))
    minute, stoppage, absolute = parse_match_minute(match_minute)
    team_id = _str_or_none(event.get("IdTeam"))
    event_id = _str_or_none(event.get("EventId")) or f"{index}"
    description = _localized(event.get("EventDescription"))
    penalty_fields = _penalty_fields(
        match_key=match_key,
        event_id=event_id,
        event=event,
        event_type=event_type,
        period=_int_or_none(event.get("Period")),
        team_names=team_names,
        player_names=player_names,
        shootout_overrides=shootout_overrides,
    )
    return {
        "match_key": match_key,
        "fifa_match_id": fifa_match_id,
        "event_id": event_id,
        "event_order": index,
        "event_type": event_type,
        "event_type_name": _localized(event.get("TypeLocalized")),
        "event_timestamp": _str_or_none(event.get("Timestamp")),
        "period": _int_or_none(event.get("Period")),
        "match_minute": match_minute,
        "minute": minute,
        "stoppage_minute": stoppage,
        "absolute_minute": absolute,
        "team_id": team_id,
        "team_name": team_names.get(str(team_id), "") if team_id is not None else None,
        "player_id": _str_or_none(event.get("IdPlayer")),
        "player_name": _event_player_name(event_type, description),
        "related_player_id": _str_or_none(event.get("IdSubPlayer")),
        "home_goals": _int_or_none(event.get("HomeGoals")),
        "away_goals": _int_or_none(event.get("AwayGoals")),
        "home_penalty_goals": _int_or_none(event.get("HomePenaltyGoals")),
        "away_penalty_goals": _int_or_none(event.get("AwayPenaltyGoals")),
        **penalty_fields,
        "description": description,
        "raw_json": _json(event),
    }


def _goal_involvement_rows(
    *,
    match_key: str,
    fifa_match_id: str,
    event_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assists = [row for row in event_rows if row["event_type"] == ASSIST_EVENT_TYPE]
    used_assists: set[str] = set()
    goal_rows: list[dict[str, Any]] = []
    goal_order = 0
    for row in event_rows:
        if not _counts_as_match_goal(row):
            continue
        goal_order += 1
        assist = _assist_for_goal(row, assists, used_assists)
        if assist:
            used_assists.add(str(assist["event_id"]))
        raw = {"goal": json.loads(row["raw_json"])}
        if assist:
            raw["assist"] = json.loads(assist["raw_json"])
        goal_rows.append(
            {
                "match_key": match_key,
                "fifa_match_id": fifa_match_id,
                "goal_event_id": row["event_id"],
                "goal_order": goal_order,
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "minute_display": row["match_minute"],
                "minute": row["minute"],
                "stoppage_minute": row["stoppage_minute"],
                "absolute_minute": row["absolute_minute"],
                "scorer_player_id": row["player_id"],
                "scorer_name": row["player_name"] or _name_from_goal_description(row["description"]),
                "assist_event_id": assist["event_id"] if assist else None,
                "assister_player_id": assist["player_id"] if assist else None,
                "assister_name": assist["player_name"] if assist else None,
                "home_goals_after": row["home_goals"],
                "away_goals_after": row["away_goals"],
                "source": SOURCE_NAME,
                "raw_json": _json(raw),
            }
        )
    return goal_rows


def _counts_as_match_goal(row: Mapping[str, Any]) -> bool:
    return row.get("event_type") in GOAL_EVENT_TYPES and row.get("period") != SHOOTOUT_PERIOD


def _penalty_fields(
    *,
    match_key: str,
    event_id: str,
    event: Mapping[str, Any],
    event_type: int | None,
    period: int | None,
    team_names: Mapping[str, str],
    player_names: Mapping[str, str],
    shootout_overrides: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    result = _penalty_result(event_type, period)
    keeper_player_id = _str_or_none(event.get("IdSubPlayer")) if result else None
    keeper_team_id = _str_or_none(event.get("IdSubTeam")) if result else None
    override = shootout_overrides.get((match_key, event_id), {})
    miss_type = _penalty_miss_type(
        event_type=event_type,
        result=result,
        override=override,
    )
    miss_type_source = None
    if result == "missed":
        miss_type_source = _str_or_none(override.get("source_url")) or "fifa_timeline"
    return {
        "penalty_result": result,
        "penalty_miss_type": miss_type,
        "penalty_miss_type_source": miss_type_source,
        "penalty_keeper_player_id": keeper_player_id,
        "penalty_keeper_name": player_names.get(str(keeper_player_id)) if keeper_player_id else None,
        "penalty_keeper_team_id": keeper_team_id,
        "penalty_keeper_team_name": team_names.get(str(keeper_team_id), "")
        if keeper_team_id
        else None,
    }


def _penalty_result(event_type: int | None, period: int | None) -> str | None:
    if period != SHOOTOUT_PERIOD:
        return None
    if event_type == PENALTY_GOAL_EVENT_TYPE:
        return "scored"
    if event_type in PENALTY_MISSED_EVENT_TYPES:
        return "missed"
    return None


def _penalty_miss_type(
    *,
    event_type: int | None,
    result: str | None,
    override: Mapping[str, Any],
) -> str | None:
    if result != "missed":
        return None
    override_type = _str_or_none(override.get("penalty_miss_type"))
    if override_type:
        return override_type
    if event_type == 65:
        return "off_target"
    return "unknown"


def _fetch_penalty_keeper_names(
    events: list[Any],
    *,
    fetch: FetchJson,
    api_base_url: str,
    language: str,
) -> dict[str, str]:
    player_ids = sorted(
        {
            str(event.get("IdSubPlayer"))
            for event in events
            if isinstance(event, Mapping)
            and _penalty_result(_int_or_none(event.get("Type")), _int_or_none(event.get("Period")))
            and event.get("IdSubPlayer") is not None
        }
    )
    names: dict[str, str] = {}
    for player_id in player_ids:
        try:
            payload = fetch(_player_url(api_base_url, player_id, language))
        except Exception:
            continue
        name = _localized(payload.get("Name")) or _localized(payload.get("Alias"))
        if name:
            names[player_id] = name
    return names


def _player_url(api_base_url: str, fifa_player_id: str, language: str) -> str:
    params = urllib.parse.urlencode({"language": language})
    return f"{api_base_url.rstrip('/')}/players/{fifa_player_id}?{params}"


def _load_shootout_overrides(path: str | Path | None) -> dict[tuple[str, str], Mapping[str, Any]]:
    if path is None:
        return {}
    override_path = Path(path)
    if not override_path.exists():
        return {}
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise ValueError("shootout penalty overrides must contain an events list")
    overrides: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in events:
        if not isinstance(item, Mapping):
            continue
        match_key = _str_or_none(item.get("match_key"))
        event_id = _str_or_none(item.get("event_id"))
        if match_key and event_id:
            overrides[(match_key, event_id)] = item
    return overrides


def _assist_for_goal(
    goal: Mapping[str, Any],
    assists: list[dict[str, Any]],
    used_assists: set[str],
) -> dict[str, Any] | None:
    candidates = [
        assist
        for assist in assists
        if str(assist["event_id"]) not in used_assists
        and assist.get("team_id") == goal.get("team_id")
    ]
    if not candidates:
        return None

    scorer_id = goal.get("player_id")
    related_matches = [
        assist
        for assist in candidates
        if scorer_id
        and assist.get("related_player_id") == scorer_id
        and _minute_delta(assist, goal) <= 2
    ]
    if related_matches:
        return min(related_matches, key=lambda assist: _minute_delta(assist, goal))

    same_minute = [
        assist
        for assist in candidates
        if assist.get("match_minute") == goal.get("match_minute")
        and _scoreline_close_to_goal(assist, goal)
    ]
    if same_minute:
        return min(same_minute, key=lambda assist: _minute_delta(assist, goal))

    nearby = [
        assist
        for assist in candidates
        if _minute_delta(assist, goal) <= 1 and _scoreline_close_to_goal(assist, goal)
    ]
    if nearby:
        return min(nearby, key=lambda assist: _minute_delta(assist, goal))
    return None


def _minute_delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    left_minute = left.get("absolute_minute")
    right_minute = right.get("absolute_minute")
    if left_minute is None or right_minute is None:
        return 999
    return abs(int(left_minute) - int(right_minute))


def _scoreline_close_to_goal(assist: Mapping[str, Any], goal: Mapping[str, Any]) -> bool:
    home_before = assist.get("home_goals")
    away_before = assist.get("away_goals")
    home_after = goal.get("home_goals")
    away_after = goal.get("away_goals")
    if None in (home_before, away_before, home_after, away_after):
        return True
    return abs(int(home_after) - int(home_before)) <= 1 and abs(int(away_after) - int(away_before)) <= 1


def parse_match_minute(value: str | None) -> tuple[int | None, int | None, int | None]:
    if not value:
        return None, None, None
    clean = value.strip().replace(" ", "")
    match = re.match(r"^(\d+)'(?:\+(\d+)')?$", clean)
    if not match:
        return None, None, None
    minute = int(match.group(1))
    stoppage = int(match.group(2) or 0)
    return minute, stoppage, minute + stoppage


def _fetch_json(url: str) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 football-data/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def _localized(items: Any, locale: str = "en-GB") -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("Locale") == locale:
            return _str_or_none(item.get("Description"))
    for item in items:
        if isinstance(item, dict) and item.get("Description") is not None:
            return _str_or_none(item.get("Description"))
    return None


def _team_name(team: Mapping[str, Any]) -> str | None:
    return _localized(team.get("TeamName")) or _str_or_none(team.get("ShortClubName"))


def _event_player_name(event_type: int | None, description: str | None) -> str | None:
    if event_type == ASSIST_EVENT_TYPE:
        return _name_from_assist_description(description)
    if event_type in GOAL_EVENT_TYPES:
        return _name_from_goal_description(description)
    penalty_miss_name = _name_from_penalty_miss_description(description)
    if penalty_miss_name:
        return penalty_miss_name
    return None


def _name_from_assist_description(description: str | None) -> str | None:
    if not description:
        return None
    match = re.match(r"^Assisted by\s+(.+?)\.?$", description.strip())
    return match.group(1).strip() if match else None


def _name_from_goal_description(description: str | None) -> str | None:
    if not description:
        return None
    match = re.match(
        r"^(.+?)\s+\(.+?\)\s+(?:scores|successfully converts the penalty)",
        description.strip(),
    )
    return match.group(1).strip() if match else None


def _name_from_penalty_miss_description(description: str | None) -> str | None:
    if not description:
        return None
    match = re.match(
        r"^(.+?)\s+\(.+?\)\s+(?:"
        r"sees (?:his|her|their) penalty saved by the goalkeeper"
        r"|misses from the penalty spot"
        r")",
        description.strip(),
    )
    return match.group(1).strip() if match else None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
