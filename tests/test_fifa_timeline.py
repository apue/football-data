import sqlite3

from football_data.fifa_timeline import backfill_fifa_timelines, parse_match_minute


def test_parse_match_minute_handles_stoppage_time():
    assert parse_match_minute("5'") == (5, 0, 5)
    assert parse_match_minute("90'+4'") == (90, 4, 94)
    assert parse_match_minute("45'+3'") == (45, 3, 48)
    assert parse_match_minute(None) == (None, None, None)


def test_backfill_fifa_timelines_stores_goal_involvements(tmp_path):
    db_path = tmp_path / "timeline.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            create table meta(key text primary key, value text not null);
            create table matches(
              match_key text primary key,
              match_no integer not null,
              match_date text not null,
              home_team text not null,
              away_team text not null,
              home_score integer not null,
              away_score integer not null
            );
            insert into matches values(
              'FIFA-2026-M35-NED-SWE', 35, '2026-06-20',
              'Netherlands', 'Sweden', 5, 1
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    def fake_fetch(url: str):
        if "/calendar/matches" in url:
            return {
                "Results": [
                    {
                        "IdMatch": "400021472",
                        "IdCompetition": "17",
                        "IdSeason": "285023",
                        "IdStage": "289273",
                        "IdGroup": "289280",
                        "MatchNumber": 35,
                        "Home": {
                            "IdTeam": "43960",
                            "Score": 5,
                            "TeamName": [{"Locale": "en-GB", "Description": "Netherlands"}],
                        },
                        "Away": {
                            "IdTeam": "43970",
                            "Score": 1,
                            "TeamName": [{"Locale": "en-GB", "Description": "Sweden"}],
                        },
                    }
                ]
            }
        if "/timelines/400021472" in url:
            return {
                "IdMatch": "400021472",
                "Event": [
                    {
                        "EventId": "assist-1",
                        "IdTeam": "43960",
                        "IdPlayer": "448152",
                        "MatchMinute": "5'",
                        "Period": 3,
                        "HomeGoals": 0,
                        "AwayGoals": 0,
                        "Type": 1,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Assist"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Assisted by Cody GAKPO."}
                        ],
                    },
                    {
                        "EventId": "goal-1",
                        "IdTeam": "43960",
                        "IdPlayer": "424051",
                        "MatchMinute": "5'",
                        "Period": 3,
                        "HomeGoals": 1,
                        "AwayGoals": 0,
                        "Type": 0,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Goal!"}],
                        "EventDescription": [
                            {
                                "Locale": "en-GB",
                                "Description": "Brian BROBBEY (Netherlands) scores!!",
                            }
                        ],
                    },
                    {
                        "EventId": "goal-2",
                        "IdTeam": "43960",
                        "IdPlayer": "448152",
                        "MatchMinute": "47'",
                        "Period": 5,
                        "HomeGoals": 2,
                        "AwayGoals": 0,
                        "Type": 0,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Goal!"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Cody GAKPO (Netherlands) scores!!"}
                        ],
                    },
                    {
                        "EventId": "assist-2",
                        "IdTeam": "43960",
                        "IdPlayer": "436612",
                        "MatchMinute": "47'",
                        "Period": 5,
                        "HomeGoals": 1,
                        "AwayGoals": 0,
                        "Type": 1,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Assist"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Assisted by Denzel DUMFRIES."}
                        ],
                    },
                    {
                        "EventId": "penalty-goal-1",
                        "IdTeam": "43960",
                        "IdPlayer": "424051",
                        "MatchMinute": "60'",
                        "Period": 5,
                        "HomeGoals": 3,
                        "AwayGoals": 0,
                        "Type": 41,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Penalty Goal"}],
                        "EventDescription": [
                            {
                                "Locale": "en-GB",
                                "Description": "Brian BROBBEY (Netherlands) successfully converts the penalty!",
                            }
                        ],
                    },
                    {
                        "EventId": "assist-3",
                        "IdTeam": "43960",
                        "IdPlayer": "400511",
                        "IdSubPlayer": "430413",
                        "MatchMinute": "90'+3'",
                        "Period": 5,
                        "HomeGoals": 3,
                        "AwayGoals": 0,
                        "Type": 1,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Assist"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Assisted by Kou ITAKURA."}
                        ],
                    },
                    {
                        "EventId": "goal-3",
                        "IdTeam": "43960",
                        "IdPlayer": "430413",
                        "MatchMinute": "90'+4'",
                        "Period": 5,
                        "HomeGoals": 4,
                        "AwayGoals": 0,
                        "Type": 0,
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Goal!"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Ayase UEDA (Netherlands) scores!!"}
                        ],
                    },
                ],
            }
        raise AssertionError(f"Unexpected URL {url}")

    summary = backfill_fifa_timelines(db_path, fetch_json=fake_fetch)

    conn = sqlite3.connect(db_path)
    try:
        link = conn.execute(
            "select fifa_match_id, status from fifa_match_links where match_key = ?",
            ("FIFA-2026-M35-NED-SWE",),
        ).fetchone()
        events = conn.execute("select count(*) from official_match_events").fetchone()[0]
        goals = conn.execute(
            """
            select scorer_name, assister_name, minute_display, home_goals_after, away_goals_after
            from goal_involvements
            order by goal_order
            """
        ).fetchall()
        schema_version = conn.execute(
            "select value from meta where key = 'schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert summary["status"] == "success"
    assert summary["linked_matches"] == 1
    assert summary["assists"] == 3
    assert link == ("400021472", "timeline_loaded")
    assert events == 7
    assert goals == [
        ("Brian BROBBEY", "Cody GAKPO", "5'", 1, 0),
        ("Cody GAKPO", "Denzel DUMFRIES", "47'", 2, 0),
        ("Brian BROBBEY", None, "60'", 3, 0),
        ("Ayase UEDA", "Kou ITAKURA", "90'+4'", 4, 0),
    ]
    assert schema_version == "7"


def test_backfill_fifa_timelines_keeps_shootout_out_of_goal_involvements(tmp_path):
    db_path = tmp_path / "shootout.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            create table meta(key text primary key, value text not null);
            create table matches(
              match_key text primary key,
              match_no integer not null,
              match_date text not null,
              home_team text not null,
              away_team text not null,
              home_score integer not null,
              away_score integer not null
            );
            insert into matches values(
              'FIFA-2026-M74-GER-PAR', 74, '2026-06-29',
              'Germany', 'Paraguay', 1, 1
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    def fake_fetch(url: str):
        if "/calendar/matches" in url:
            return {
                "Results": [
                    {
                        "IdMatch": "400021519",
                        "IdCompetition": "17",
                        "IdSeason": "285023",
                        "IdStage": "289287",
                        "MatchNumber": 74,
                        "ResultType": 2,
                        "Winner": "43928",
                        "HomeTeamPenaltyScore": 3,
                        "AwayTeamPenaltyScore": 4,
                        "Home": {
                            "IdTeam": "43948",
                            "Score": 1,
                            "TeamName": [{"Locale": "en-GB", "Description": "Germany"}],
                        },
                        "Away": {
                            "IdTeam": "43928",
                            "Score": 1,
                            "TeamName": [{"Locale": "en-GB", "Description": "Paraguay"}],
                        },
                    }
                ]
            }
        if "/timelines/400021519" in url:
            return {
                "IdMatch": "400021519",
                "Event": [
                    {
                        "EventId": "regular-goal-1",
                        "IdTeam": "43948",
                        "IdPlayer": "386413",
                        "MatchMinute": "12'",
                        "Period": 3,
                        "HomeGoals": 1,
                        "AwayGoals": 0,
                        "HomePenaltyGoals": 0,
                        "AwayPenaltyGoals": 0,
                        "Type": 0,
                        "Timestamp": "2026-06-29T19:12:00Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Goal!"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "Joshua KIMMICH (Germany) scores!!"}
                        ],
                    },
                    {
                        "EventId": "regular-goal-2",
                        "IdTeam": "43928",
                        "IdPlayer": "495046",
                        "MatchMinute": "82'",
                        "Period": 5,
                        "HomeGoals": 1,
                        "AwayGoals": 1,
                        "HomePenaltyGoals": 0,
                        "AwayPenaltyGoals": 0,
                        "Type": 0,
                        "Timestamp": "2026-06-29T20:42:00Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Goal!"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "MAURICIO (Paraguay) scores!!"}
                        ],
                    },
                    {
                        "EventId": "shootout-start",
                        "Period": 11,
                        "HomeGoals": 1,
                        "AwayGoals": 1,
                        "HomePenaltyGoals": 0,
                        "AwayPenaltyGoals": 0,
                        "Type": 7,
                        "Timestamp": "2026-06-29T23:17:21Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Start Time"}],
                        "EventDescription": [
                            {
                                "Locale": "en-GB",
                                "Description": "The penalty shoot-out is about to begin.",
                            }
                        ],
                    },
                    {
                        "EventId": "shootout-miss-1",
                        "IdTeam": "43948",
                        "IdPlayer": "411367",
                        "IdSubPlayer": "494531",
                        "IdSubTeam": "43928",
                        "Period": 11,
                        "HomeGoals": 1,
                        "AwayGoals": 1,
                        "HomePenaltyGoals": 0,
                        "AwayPenaltyGoals": 0,
                        "Type": 60,
                        "Timestamp": "2026-06-29T23:18:22Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Penalty missed"}],
                        "EventDescription": [
                            {
                                "Locale": "en-GB",
                                "Description": "Kai HAVERTZ (Germany) sees his penalty saved by the goalkeeper.",
                            }
                        ],
                    },
                    {
                        "EventId": "shootout-goal-1",
                        "IdTeam": "43928",
                        "IdPlayer": "495046",
                        "IdSubPlayer": "228912",
                        "IdSubTeam": "43948",
                        "Period": 11,
                        "HomeGoals": 1,
                        "AwayGoals": 1,
                        "HomePenaltyGoals": 0,
                        "AwayPenaltyGoals": 1,
                        "Type": 41,
                        "Timestamp": "2026-06-29T23:19:29Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "Penalty Goal"}],
                        "EventDescription": [
                            {
                                "Locale": "en-GB",
                                "Description": "MAURICIO (Paraguay) successfully converts the penalty!",
                            }
                        ],
                    },
                    {
                        "EventId": "shootout-end",
                        "Period": 11,
                        "HomeGoals": 1,
                        "AwayGoals": 1,
                        "HomePenaltyGoals": 3,
                        "AwayPenaltyGoals": 4,
                        "Type": 8,
                        "Timestamp": "2026-06-29T23:28:25Z",
                        "TypeLocalized": [{"Locale": "en-GB", "Description": "End Time"}],
                        "EventDescription": [
                            {"Locale": "en-GB", "Description": "The penalty shoot-out is over."}
                        ],
                    },
                ],
            }
        if "/players/494531" in url:
            return {
                "IdPlayer": "494531",
                "Name": [{"Locale": "en-GB", "Description": "Orlando GILL"}],
            }
        if "/players/228912" in url:
            return {
                "IdPlayer": "228912",
                "Name": [{"Locale": "en-GB", "Description": "Manuel NEUER"}],
            }
        raise AssertionError(f"Unexpected URL {url}")

    summary = backfill_fifa_timelines(db_path, fetch_json=fake_fetch)

    conn = sqlite3.connect(db_path)
    try:
        goals = conn.execute(
            """
            select scorer_name, minute_display, home_goals_after, away_goals_after
            from goal_involvements
            order by goal_order
            """
        ).fetchall()
        link = conn.execute(
            """
            select home_penalty_score, away_penalty_score, winner_team_id, result_type
            from fifa_match_links
            where match_key = 'FIFA-2026-M74-GER-PAR'
            """
        ).fetchone()
        shootout_events = conn.execute(
            """
            select event_order, event_timestamp, event_type_name, team_name, player_name,
                   home_penalty_goals, away_penalty_goals, penalty_result,
                   penalty_miss_type, penalty_keeper_player_id, penalty_keeper_name,
                   penalty_keeper_team_id, penalty_keeper_team_name, description
            from official_match_events
            where period = 11
            order by event_order
            """
        ).fetchall()
        schema_version = conn.execute(
            "select value from meta where key = 'schema_version'"
        ).fetchone()[0]
        timeline_schema_version = conn.execute(
            "select value from meta where key = 'fifa_timeline_schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert summary["goals"] == 2
    assert summary["goal_involvements"] == 2
    assert goals == [
        ("Joshua KIMMICH", "12'", 1, 0),
        ("MAURICIO", "82'", 1, 1),
    ]
    assert link == (3, 4, "43928", 2)
    assert shootout_events == [
        (
            3,
            "2026-06-29T23:17:21Z",
            "Start Time",
            None,
            None,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            "The penalty shoot-out is about to begin.",
        ),
        (
            4,
            "2026-06-29T23:18:22Z",
            "Penalty missed",
            "Germany",
            "Kai HAVERTZ",
            0,
            0,
            "missed",
            "unknown",
            "494531",
            "Orlando GILL",
            "43928",
            "Paraguay",
            "Kai HAVERTZ (Germany) sees his penalty saved by the goalkeeper.",
        ),
        (
            5,
            "2026-06-29T23:19:29Z",
            "Penalty Goal",
            "Paraguay",
            "MAURICIO",
            0,
            1,
            "scored",
            None,
            "228912",
            "Manuel NEUER",
            "43948",
            "Germany",
            "MAURICIO (Paraguay) successfully converts the penalty!",
        ),
        (
            6,
            "2026-06-29T23:28:25Z",
            "End Time",
            None,
            None,
            3,
            4,
            None,
            None,
            None,
            None,
            None,
            None,
            "The penalty shoot-out is over.",
        ),
    ]
    assert schema_version == "7"
    assert timeline_schema_version == "3"
