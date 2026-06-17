from __future__ import annotations

import sqlite3
from pathlib import Path

from football_data.extract import extraction_timestamp, parser_version
from football_data.model import ExtractedMatch


SCHEMA_VERSION = 2


def build_database(path: str | Path, records: list[ExtractedMatch]) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("pragma foreign_keys = on")
        _create_schema(conn)
        for record in records:
            _insert_record(conn, record)
        conn.commit()
    finally:
        conn.close()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table meta (
          key text primary key,
          value text not null
        );

        create table source_documents (
          source_id text primary key,
          competition text not null,
          report_type text not null,
          match_key text not null,
          match_no integer not null,
          home_code text not null,
          away_code text not null,
          version integer not null,
          source_url text,
          file_name text not null,
          sha256 text not null,
          file_size integer not null,
          discovered_at text,
          fetched_at text,
          active integer not null default 1,
          status text not null
        );

        create table extraction_runs (
          id integer primary key autoincrement,
          source_id text not null,
          match_key text not null,
          source_sha256 text not null,
          parser_version text not null,
          extracted_at text not null,
          status text not null,
          message text,
          foreign key(source_id) references source_documents(source_id)
        );

        create table matches (
          match_key text primary key,
          source_id text not null,
          match_no integer not null,
          group_name text not null,
          match_date text not null,
          kickoff_time text not null,
          stadium text not null,
          home_team text not null,
          away_team text not null,
          home_score integer not null,
          away_score integer not null,
          foreign key(source_id) references source_documents(source_id)
        );

        create table team_match_stats (
          match_key text not null,
          source_id text not null,
          team text not null,
          opponent text not null,
          possession_pct real,
          goals integer,
          xg real,
          attempts_total integer,
          attempts_on_target integer,
          passes_total integer,
          passes_complete integer,
          pass_completion_pct real,
          completed_line_breaks integer,
          defensive_line_breaks integer,
          receptions_final_third integer,
          crosses integer,
          ball_progressions integer,
          defensive_pressures integer,
          direct_pressures integer,
          forced_turnovers integer,
          second_balls integer,
          total_distance_km real,
          zone4_low_speed_sprinting_km real,
          primary key(match_key, team),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table shots (
          match_key text not null,
          source_id text not null,
          team text not null,
          shot_no integer not null,
          minute integer not null,
          player_name text not null,
          outcome text not null,
          body_part text not null,
          delivery_type text not null,
          is_goal integer not null,
          is_on_target integer not null,
          primary key(match_key, team, shot_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_physical_stats (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          total_distance_m real,
          zone1_m real,
          zone2_m real,
          zone3_m real,
          zone4_m real,
          zone5_m real,
          high_speed_runs real,
          sprints real,
          top_speed_kmh real,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );
        """
    )
    conn.executemany(
        "insert into meta(key, value) values(?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("parser_version", parser_version()),
        ],
    )


def _insert_record(conn: sqlite3.Connection, record: ExtractedMatch) -> None:
    match = record.match
    conn.execute(
        """
        insert into source_documents(
          source_id, competition, report_type, match_key, match_no, home_code,
          away_code, version, source_url, file_name, sha256, file_size,
          discovered_at, fetched_at, active, status
        ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.source.source_id,
            record.source.competition,
            record.source.report_type,
            match.match_key,
            record.source.match_no,
            record.source.home_code,
            record.source.away_code,
            record.source.version,
            record.source.source_url,
            record.source.file_name,
            record.source.sha256,
            record.source.file_size,
            record.source.discovered_at,
            record.source.fetched_at,
            int(record.source.active),
            record.source.status,
        ),
    )
    conn.execute(
        """
        insert into matches(
          match_key, source_id, match_no, group_name, match_date, kickoff_time,
          stadium, home_team, away_team, home_score, away_score
        ) values(
          :match_key, :source_id, :match_no, :group_name, :match_date, :kickoff_time,
          :stadium, :home_team, :away_team, :home_score, :away_score
        )
        """,
        {
            **match.__dict__,
            "source_id": record.source.source_id,
        },
    )
    conn.execute(
        """
        insert into extraction_runs(
          source_id, match_key, source_sha256, parser_version, extracted_at, status, message
        ) values(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.source.source_id,
            match.match_key,
            record.source.sha256,
            parser_version(),
            extraction_timestamp(),
            "success",
            None,
        ),
    )
    conn.executemany(
        """
        insert into team_match_stats(
          match_key, source_id, team, opponent, possession_pct, goals, xg,
          attempts_total, attempts_on_target, passes_total, passes_complete,
          pass_completion_pct, completed_line_breaks, defensive_line_breaks,
          receptions_final_third, crosses, ball_progressions, defensive_pressures,
          direct_pressures, forced_turnovers, second_balls, total_distance_km,
          zone4_low_speed_sprinting_km
        ) values(
          :match_key, :source_id, :team, :opponent, :possession_pct, :goals, :xg,
          :attempts_total, :attempts_on_target, :passes_total, :passes_complete,
          :pass_completion_pct, :completed_line_breaks, :defensive_line_breaks,
          :receptions_final_third, :crosses, :ball_progressions,
          :defensive_pressures, :direct_pressures, :forced_turnovers, :second_balls,
          :total_distance_km, :zone4_low_speed_sprinting_km
        )
        """,
        [row.__dict__ for row in record.team_stats],
    )
    conn.executemany(
        """
        insert into shots(
          match_key, source_id, team, shot_no, minute, player_name, outcome,
          body_part, delivery_type, is_goal, is_on_target
        ) values(
          :match_key, :source_id, :team, :shot_no, :minute, :player_name, :outcome,
          :body_part, :delivery_type, :is_goal, :is_on_target
        )
        """,
        [
            {
                **row.__dict__,
                "is_goal": int(row.is_goal),
                "is_on_target": int(row.is_on_target),
            }
            for row in record.shots
        ],
    )
    conn.executemany(
        """
        insert into player_physical_stats(
          match_key, source_id, team, player_no, player_name, total_distance_m,
          zone1_m, zone2_m, zone3_m, zone4_m, zone5_m, high_speed_runs,
          sprints, top_speed_kmh
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :total_distance_m,
          :zone1_m, :zone2_m, :zone3_m, :zone4_m, :zone5_m, :high_speed_runs,
          :sprints, :top_speed_kmh
        )
        """,
        [row.__dict__ for row in record.player_physical],
    )
