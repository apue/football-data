from football_data.metric_benchmarks import hidden_gem_profile, progression_benchmark


def test_progression_benchmark_does_not_overvalue_pass_only_line_break_volume():
    benchmark = progression_benchmark(
        {
            "position": "DF",
            "line_breaks_completed": 18,
            "distribution_ball_progression": 0,
            "ball_progressions": 1,
            "take_ons": 0,
            "step_ins": 1,
            "offers_received": 4,
            "in_between": 0,
            "in_behind": 1,
        }
    )

    assert benchmark["quality"] == "thin"
    assert benchmark["pass_only_line_break_volume"] is True
    assert benchmark["score"] < 20


def test_hidden_gem_profile_allows_close_loss_defensive_resistance():
    profile = hidden_gem_profile(
        {
            "team_final_goals": 0,
            "opponent_final_goals": 1,
            "position": "MF",
            "role_scores": {"defensive": 32.85, "progressor": 31.0, "off_ball": 15.4},
            "possession_regains": 9,
            "possession_interrupted": 7,
            "blocks": 2,
            "line_breaks_completed": 14,
            "distribution_ball_progression": 0,
            "ball_progressions": 1,
            "take_ons": 0,
            "step_ins": 1,
        }
    )

    assert profile["eligible"] is True
    assert profile["profile"] == "defensive_resistance"
