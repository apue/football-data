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
                        "EventId": "assist-3",
                        "IdTeam": "43960",
                        "IdPlayer": "400511",
                        "IdSubPlayer": "430413",
                        "MatchMinute": "90'+3'",
                        "Period": 5,
                        "HomeGoals": 2,
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
                        "HomeGoals": 3,
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
    assert events == 6
    assert goals == [
        ("Brian BROBBEY", "Cody GAKPO", "5'", 1, 0),
        ("Cody GAKPO", "Denzel DUMFRIES", "47'", 2, 0),
        ("Ayase UEDA", "Kou ITAKURA", "90'+4'", 3, 0),
    ]
    assert schema_version == "5"
