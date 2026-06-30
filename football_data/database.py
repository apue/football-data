from __future__ import annotations

import sqlite3
from pathlib import Path

from football_data.extract import extraction_timestamp, parser_version
from football_data.model import ExtractedMatch


SCHEMA_VERSION = 7


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

        create table player_appearances (
          match_key text not null,
          source_id text not null,
          team text not null,
          opponent text not null,
          player_no integer not null,
          player_name text not null,
          position text not null,
          roster_status text not null,
          started integer not null,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_event_markers (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          marker_index integer not null,
          raw_marker text not null,
          minute integer,
          page_number integer,
          primary key(match_key, team, player_no, marker_index),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_in_possession_distributions (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          page_number integer,
          passes_attempted integer,
          passes_completed integer,
          pass_completion_pct real,
          switches_of_play integer,
          crosses_attempted integer,
          crosses_completed integer,
          line_breaks_attempted integer,
          line_breaks_completed integer,
          line_break_completion_pct real,
          ball_progressions integer,
          take_ons integer,
          step_ins integer,
          attempts_at_goal integer,
          goals integer,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_line_breaks (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          page_number integer,
          line_breaks_attempted integer,
          line_breaks_completed integer,
          line_break_completion_pct real,
          units_4_attacking_line integer,
          units_4_attacking_midfield_line integer,
          units_4_midfield_line integer,
          units_4_defensive_line integer,
          units_3_attacking_line integer,
          units_3_midfield_line integer,
          units_3_defensive_line integer,
          units_2_midfield_line integer,
          units_2_defensive_line integer,
          direction_through integer,
          direction_around integer,
          direction_over integer,
          distribution_pass integer,
          distribution_cross integer,
          distribution_ball_progression integer,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_offers_receptions (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          page_number integer,
          total_offers integer,
          in_front integer,
          in_between integer,
          out_to_in integer,
          in_to_out integer,
          in_behind integer,
          no_movement integer,
          offers_received integer,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table player_defensive_actions (
          match_key text not null,
          source_id text not null,
          team text not null,
          player_no integer not null,
          player_name text not null,
          page_number integer,
          tackles_made integer,
          tackles_won integer,
          blocks integer,
          interceptions integer,
          pressing_direct integer,
          pressing_indirect integer,
          duels_won_aerial integer,
          duels_won_physical integer,
          possession_contests_won integer,
          clearances integer,
          loose_ball_receptions integer,
          pushing_on integer,
          pushing_on_into_pressing integer,
          possession_regains integer,
          possession_interrupted integer,
          primary key(match_key, team, player_no),
          foreign key(match_key) references matches(match_key),
          foreign key(source_id) references source_documents(source_id)
        );

        create table fifa_match_links (
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

        create table official_match_events (
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

        create table goal_involvements (
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

        create index idx_player_appearances_name
          on player_appearances(player_name, team);

        create index idx_player_physical_identity
          on player_physical_stats(match_key, team, player_no);

        create index idx_official_match_events_type
          on official_match_events(match_key, event_type);

        create index idx_goal_involvements_assister
          on goal_involvements(match_key, assister_name);
        """
    )
    conn.executemany(
        "insert into meta(key, value) values(?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("parser_version", parser_version()),
            ("fifa_timeline_schema_version", "3"),
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
    conn.executemany(
        """
        insert into player_appearances(
          match_key, source_id, team, opponent, player_no, player_name, position,
          roster_status, started
        ) values(
          :match_key, :source_id, :team, :opponent, :player_no, :player_name,
          :position, :roster_status, :started
        )
        """,
        [
            {
                **row.__dict__,
                "started": int(row.started),
            }
            for row in record.player_appearances
        ],
    )
    conn.executemany(
        """
        insert into player_event_markers(
          match_key, source_id, team, player_no, player_name, marker_index,
          raw_marker, minute, page_number
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :marker_index,
          :raw_marker, :minute, :page_number
        )
        """,
        [row.__dict__ for row in record.player_event_markers],
    )
    conn.executemany(
        """
        insert into player_in_possession_distributions(
          match_key, source_id, team, player_no, player_name, page_number,
          passes_attempted, passes_completed, pass_completion_pct, switches_of_play,
          crosses_attempted, crosses_completed, line_breaks_attempted,
          line_breaks_completed, line_break_completion_pct, ball_progressions,
          take_ons, step_ins, attempts_at_goal, goals
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :page_number,
          :passes_attempted, :passes_completed, :pass_completion_pct,
          :switches_of_play, :crosses_attempted, :crosses_completed,
          :line_breaks_attempted, :line_breaks_completed,
          :line_break_completion_pct, :ball_progressions, :take_ons, :step_ins,
          :attempts_at_goal, :goals
        )
        """,
        [row.__dict__ for row in record.player_distributions],
    )
    conn.executemany(
        """
        insert into player_line_breaks(
          match_key, source_id, team, player_no, player_name, page_number,
          line_breaks_attempted, line_breaks_completed, line_break_completion_pct,
          units_4_attacking_line, units_4_attacking_midfield_line,
          units_4_midfield_line, units_4_defensive_line,
          units_3_attacking_line, units_3_midfield_line, units_3_defensive_line,
          units_2_midfield_line, units_2_defensive_line,
          direction_through, direction_around, direction_over,
          distribution_pass, distribution_cross, distribution_ball_progression
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :page_number,
          :line_breaks_attempted, :line_breaks_completed, :line_break_completion_pct,
          :units_4_attacking_line, :units_4_attacking_midfield_line,
          :units_4_midfield_line, :units_4_defensive_line,
          :units_3_attacking_line, :units_3_midfield_line, :units_3_defensive_line,
          :units_2_midfield_line, :units_2_defensive_line,
          :direction_through, :direction_around, :direction_over,
          :distribution_pass, :distribution_cross, :distribution_ball_progression
        )
        """,
        [row.__dict__ for row in record.player_line_breaks],
    )
    conn.executemany(
        """
        insert into player_offers_receptions(
          match_key, source_id, team, player_no, player_name, page_number,
          total_offers, in_front, in_between, out_to_in, in_to_out, in_behind,
          no_movement, offers_received
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :page_number,
          :total_offers, :in_front, :in_between, :out_to_in, :in_to_out,
          :in_behind, :no_movement, :offers_received
        )
        """,
        [row.__dict__ for row in record.player_offers],
    )
    conn.executemany(
        """
        insert into player_defensive_actions(
          match_key, source_id, team, player_no, player_name, page_number,
          tackles_made, tackles_won, blocks, interceptions, pressing_direct,
          pressing_indirect, duels_won_aerial, duels_won_physical,
          possession_contests_won, clearances, loose_ball_receptions, pushing_on,
          pushing_on_into_pressing, possession_regains, possession_interrupted
        ) values(
          :match_key, :source_id, :team, :player_no, :player_name, :page_number,
          :tackles_made, :tackles_won, :blocks, :interceptions, :pressing_direct,
          :pressing_indirect, :duels_won_aerial, :duels_won_physical,
          :possession_contests_won, :clearances, :loose_ball_receptions,
          :pushing_on, :pushing_on_into_pressing, :possession_regains,
          :possession_interrupted
        )
        """,
        [row.__dict__ for row in record.player_defensive_actions],
    )
