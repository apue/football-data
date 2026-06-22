from football_data.match_flow import build_match_flows


def test_match_flow_marks_germany_comeback_against_cote_divoire():
    flows = build_match_flows("data/latest.sqlite", match_date="2026-06-20")
    flow = flows["FIFA-2026-M33-GER-CIV"]

    assert flow["home_team"] == "Germany"
    assert flow["away_team"] == "Côte d'Ivoire"
    assert flow["home_came_from_behind_to_win"] is True
    assert flow["winner_team"] == "Germany"

    goals = flow["goals"]
    assert [
        (goal["minute"], goal["team"], goal["player_name"], goal["score_before"], goal["score_after"])
        for goal in goals
    ] == [
        (29, "Côte d'Ivoire", "Franck KESSIE", "0-0", "0-1"),
        (67, "Germany", "Deniz UNDAV", "0-1", "1-1"),
        (93, "Germany", "Deniz UNDAV", "1-1", "2-1"),
    ]
    assert "equalizer" in goals[1]["tags"]
    assert "comeback_equalizer" in goals[1]["tags"]
    assert "match_winning_goal" in goals[2]["tags"]
    assert "stoppage_time_goal" in goals[2]["tags"]
    assert "comeback_winner" in goals[2]["tags"]
    assert flow["decisive_goal"]["player_name"] == "Deniz UNDAV"


def test_match_flow_keeps_scoreless_draw_empty():
    flows = build_match_flows("data/latest.sqlite", match_date="2026-06-20")
    flow = flows["FIFA-2026-M34-ECU-CUW"]

    assert flow["goals"] == []
    assert flow["winner_team"] is None
    assert flow["home_came_from_behind_to_win"] is False
    assert flow["away_came_from_behind_to_win"] is False


def test_match_flow_does_not_label_routine_blowout_opener_as_winner():
    flows = build_match_flows("data/latest.sqlite", match_date="2026-06-21")
    flow = flows["FIFA-2026-M38-ESP-KSA"]

    assert flow["winner_team"] == "Spain"
    assert flow["decisive_goal"] is None

    first_goal = flow["goals"][0]
    assert first_goal["player_name"] == "Lamine YAMAL"
    assert "opening_goal" in first_goal["tags"]
    assert "go_ahead_goal" in first_goal["tags"]
    assert "match_winning_goal" not in first_goal["tags"]
