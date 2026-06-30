import json
import shutil
import sqlite3
from pathlib import Path

from editorial_test_helpers import build_test_copy, build_test_selection_decision


def test_editorial_v2_registry_resolves_default_experiment():
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_review_profile,
        load_copy_profile,
        load_editorial_experiment,
        load_selection_review_profile,
        load_selector_profile,
    )
    from football_data.editorial_constants import AWARD_DISPLAY_ORDER, AWARD_LABELS
    from football_data.editorial_display_names import player_display_entry, player_display_name

    experiment = load_editorial_experiment()

    assert experiment["id"] == "bounded_editorial_loop_v1"
    assert experiment["workflow_variant"] == "bounded_selection_copy_loop_v1"
    assert experiment["selection"]["mode"] == "bounded_loop_local_editor"
    assert experiment["candidate_pool"] == "guarded_packet_v2"
    assert experiment["selector_profile"] == "slate_balanced_editor_v3"
    assert experiment["selection_review_profile"] == "selection_review_v1"
    assert experiment["copy_review_profile"] == "copy_review_v1"
    assert experiment["loop_policy"]["selection_max_rounds"] == 3
    assert experiment["loop_policy"]["copy_max_rounds"] == 3
    assert experiment["copy_profiles"]["zh"] == "zh_matchnote_light_emotion_v1"
    assert experiment["selection"]["strategy"] == "overall_slate_v1"
    assert experiment["selection"]["public_card_count"]["min"] == 3
    assert experiment["selection"]["public_card_count"]["max"] == 6
    assert "recommended_by_match_count" not in experiment["selection"]["public_card_count"]
    assert "slots" not in experiment["selection"]
    assert "required_slots" not in experiment["selection"]
    assert "optional_awards" not in experiment["selection"]
    assert "target_public_cards" not in experiment["selection"]
    assert experiment["selection"]["award_limits"] == {
        "player_of_the_day": 6,
        "impact_pick": 2,
    }
    assert experiment["selection"]["slate_balance"]["angle_awards_can_be_omitted"] == [
        "impact_pick",
    ]
    assert experiment["selection"]["slate_constraints"] == {
        "max_per_match": 3,
        "max_per_team": 3,
    }
    assert set(AWARD_LABELS) == {"player_of_the_day", "impact_pick"}
    assert AWARD_DISPLAY_ORDER == ["player_of_the_day", "impact_pick"]
    assert player_display_name("CRISTIANO RONALDO", "zh") == "C罗"
    assert player_display_entry("BRUNO FERNANDES", "zh") == {
        "display_name": "布鲁诺-费尔南德斯",
        "short_name": "B费",
    }

    pool = load_candidate_pool_config(experiment["candidate_pool"])
    selector = load_selector_profile(experiment["selector_profile"])
    selection_review = load_selection_review_profile(experiment["selection_review_profile"])
    copy_review = load_copy_review_profile(experiment["copy_review_profile"])
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    en_profile = load_copy_profile(experiment["copy_profiles"]["en"])

    assert pool["potd_top_n"] == 8
    assert selector["allowed_selection_source"] == "candidate_pool_only"
    assert any("Fact accuracy" in item for item in selector["instructions"])
    assert any("same match" in item for item in selector["instructions"])
    assert any("not a quota" in item for item in selector["instructions"])
    assert not any("slot" in item.lower() for item in selector["instructions"])
    assert selection_review["required_dimensions"] == [
        "selected_card_convincingness",
        "obvious_omission",
        "alternative_slate_comparison",
        "weakest_selected_card",
        "strongest_omitted_card",
        "impact_challenger_comparison",
        "card_count_verdict",
    ]
    assert selection_review["required_slate_assessment_fields"] == [
        "reader_questions",
        "alternative_slate_comparison",
        "weakest_selected_card",
        "strongest_omitted_card",
        "drop_weakest_verdict",
        "replace_weakest_verdict",
        "impact_challenger_verdict",
        "add_card_verdict",
        "preferred_card_count",
        "revision_decision",
    ]
    assert selection_review["required_unselected_impact_top_n"] == 5
    assert selection_review["required_card_count_challenger_count"] == 3
    assert "forced_match_coverage" in selection_review["blocking_categories"]
    assert copy_review["required_dimensions"] == [
        "fact_support",
        "english_flow",
        "zh_style",
        "title_core_fact",
        "unsupported_claims",
    ]
    assert zh_profile["language"] == "zh"
    assert zh_profile["instructions"]
    assert isinstance(zh_profile.get("banned_public_terms"), list)
    assert zh_profile["banned_public_terms"]
    assert zh_profile["title_policy"]["mode"] == "core_fact_label"
    assert isinstance(zh_profile["title_policy"].get("banned_title_terms"), list)
    assert en_profile["language"] == "en"
    assert en_profile["instructions"]

    scoring = json.loads(Path(experiment["scoring_config"]).read_text(encoding="utf-8"))
    assert "selection" not in scoring

    retired_paths = [
        "config/editorial/experiments/ai_rerank_baseline_v1.json",
        "config/editorial/experiments/ai_rerank_guardrails_v2.json",
        "config/editorial/experiments/ai_rerank_slate_copy_v3.json",
        "config/editorial/experiments/ai_rerank_slate_self_review_v4.json",
        "config/editorial/experiments/ai_rerank_reader_loop_v5.json",
        "config/editorial/review_profiles/reader_intuition_v1.json",
        "config/editorial/review_profiles/reader_intuition_loop_v2.json",
        "config/editorial/candidate_pools/rich_packet_v1.json",
        "config/editorial/selector_profiles/strict_editor_v1.json",
        "config/editorial/selector_profiles/guarded_editor_v2.json",
        "config/editorial/copy_profiles/zh_natural_v1.json",
    ]
    assert not [path for path in retired_paths if Path(path).exists()]


def test_editorial_style_calibration_loads_curated_zh_examples():
    from football_data.editorial_style_calibration import load_style_calibration

    examples = load_style_calibration("zh")

    assert examples
    assert any(example["bad"] == "这个零封很硬" for example in examples)
    assert any(example["category"] == "generic_closure" for example in examples)
    assert all(
        {
            "id",
            "category",
            "bad",
            "why_bad",
            "better",
            "principle",
            "confidence",
        }
        <= set(example)
        for example in examples
    )


def test_editorial_rankings_prefer_pmsr_appearance_for_hat_trick_scorer():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import load_candidate_pool_config, load_editorial_experiment

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-26",
        experiment["scoring_config"],
    )

    dembele = next(
        player
        for player in rankings["players"]
        if player["match_key"] == "FIFA-2026-M61-NOR-FRA"
        and player["team"] == "France"
        and player["player_name"] == "Ousmane DEMBELE"
    )
    assert dembele["player_id"] == "FIFA-2026-M61-NOR-FRA|France|7"
    assert dembele["player_no"] == 7
    assert dembele["position"] == "FW"
    assert dembele.get("data_sources") is None
    assert dembele["goals"] == 3
    assert dembele["hat_trick"] == 1
    assert dembele["opening_goal"] == 1
    assert "hat-trick" in dembele["evidence_chips"]["en"]

    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    candidate = next(
        item
        for item in pool["selectable_candidates"]
        if item["player_id"] == dembele["player_id"]
    )
    assert "player_of_the_day" in candidate["eligible_awards"]
    assert candidate["award_contexts"]["player_of_the_day"]["metrics"]["goals"] == 3
    assert candidate["award_contexts"]["player_of_the_day"]["metrics"]["hat_trick"] == 1


def test_copy_review_payload_includes_zh_style_calibration_examples():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_copy_validation import validate_copy
    from football_data.editorial_loop import build_copy_review_payload
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_profile,
        load_copy_review_profile,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-20",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    decision = build_test_selection_decision(pool, experiment)
    copy_payload = build_copy_payloads(decision, pool)
    copy = build_test_copy(build_copy_payloads(decision, pool))
    copy_profiles = {
        language: load_copy_profile(str(profile_id))
        for language, profile_id in experiment["copy_profiles"].items()
    }
    review_payload = build_copy_review_payload(
        copy=copy,
        copy_payload=copy_payload,
        copy_validation=validate_copy(copy, copy_profiles, copy_payload=copy_payload),
        review_profile=load_copy_review_profile(experiment["copy_review_profile"]),
    )

    zh_examples = review_payload["style_calibration"]["zh"]
    assert any(example["bad"] == "中锋这份活干得很满" for example in zh_examples)
    assert any(example["category"] == "generic_closure" for example in zh_examples)
    assert review_payload["style_calibration"]["review_instruction"] == (
        "Use these examples to detect repeatable taste failures; prefer concrete match consequences over generic evaluative closers."
    )


def test_selection_review_validation_requires_objection_coverage():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_loop import build_selection_review_payload, validate_selection_review
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
        load_selection_review_profile,
    )
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    decision = build_test_selection_decision(pool, experiment)
    review_profile = load_selection_review_profile(experiment["selection_review_profile"])
    review_payload = build_selection_review_payload(
        selection_decision=decision,
        candidate_pool=pool,
        selection_validation=validate_selection_decision(decision, pool, experiment),
        review_profile=review_profile,
        selection_config=experiment["selection"],
    )
    assert review_payload["public_card_count"] == {
        "selected": len(decision["selected"]),
        "min": 3,
        "max": 6,
        "match_count": 4,
    }

    selected_reviews = [
        {
            "player_id": item["player_id"],
            "verdict": "pass",
            "note": "Public case is supported by the candidate packet.",
        }
        for item in review_payload["selected"]
    ]
    unselected_reviews = [
        {
            "player_id": item["player_id"],
            "verdict": "pass",
            "note": "Not selected after comparing direct impact, match balance, and stronger public cases.",
        }
        for item in _review_required_unselected_items(review_payload)
    ]
    strongest_omitted_id = _first_review_player_id(review_payload["required_unselected_candidate_reviews"])
    impact_challenger_id = _first_review_player_id(review_payload["required_impact_candidate_reviews"])
    add_challenger_id = _first_review_player_id(review_payload["card_count_challengers"])
    good_review = {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": review_profile["required_dimensions"],
        "slate_assessment": {
            "reader_questions": ["Does the slate omit an obvious direct-impact player?"],
            "alternative_slate_comparison": [
                {"card_count": len(decision["selected"]), "tradeoff": "current slate"},
                {"card_count": max(0, len(decision["selected"]) - 1), "tradeoff": "drop weakest selected"},
            ],
            "weakest_selected_card": {
                "player_id": review_payload["selected"][-1]["player_id"],
                "reason": "Weakest selected card was checked against the omission list.",
            },
            "strongest_omitted_card": {
                "player_id": strongest_omitted_id,
                "reason": "Strongest omitted card does not beat the final public slate.",
            },
            "drop_weakest_verdict": {
                "decision": "keep",
                "reason": "The weakest selected card remains above the publishable line.",
            },
            "replace_weakest_verdict": {
                "decision": "keep",
                "replacement_player_id": strongest_omitted_id,
                "reason": "Replacement would not improve the slate.",
            },
            "impact_challenger_verdict": {
                "player_id": impact_challenger_id,
                "decision": "omit",
                "reason": "The strongest omitted impact challenger was compared with the weakest selected card.",
            },
            "add_card_verdict": {
                "player_id": add_challenger_id,
                "decision": "keep_count",
                "reason": "The strongest possible extra card would not improve the current slate.",
            },
            "preferred_card_count": len(decision["selected"]),
            "revision_decision": "keep",
        },
        "selected_player_reviews": selected_reviews,
        "unselected_candidate_reviews": unselected_reviews,
        "blocking_findings": [],
        "resolved_objections": [],
        "unresolved_objections": [],
        "revision_summary": "No blocking selection issue remains.",
    }

    good_validation = validate_selection_review(good_review, review_profile, review_payload)
    assert good_validation["status"] == "pass"

    missing_selected = json.loads(json.dumps(good_review, ensure_ascii=False))
    missing_selected["selected_player_reviews"] = missing_selected["selected_player_reviews"][:-1]
    missing_validation = validate_selection_review(missing_selected, review_profile, review_payload)
    assert missing_validation["status"] == "failed"
    assert any("missing selected player review" in warning for warning in missing_validation["warnings"])

    blocking = json.loads(json.dumps(good_review, ensure_ascii=False))
    blocking["blocking_findings"] = [
        {
            "category": "obvious_omission",
            "severity": "high",
            "evidence": "Two-goal winner is still outside the slate.",
            "recommended_action": "Revise selection before publishing.",
        }
    ]
    blocking_validation = validate_selection_review(blocking, review_profile, review_payload)
    assert blocking_validation["status"] == "failed"
    assert any("blocking finding" in warning for warning in blocking_validation["warnings"])

    unstructured = json.loads(json.dumps(good_review, ensure_ascii=False))
    unstructured["slate_assessment"]["weakest_selected_card"] = "No selected card raised a blocking concern."
    unstructured_validation = validate_selection_review(unstructured, review_profile, review_payload)
    assert unstructured_validation["status"] == "failed"
    assert any("weakest_selected_card must identify a selected player_id" in warning for warning in unstructured_validation["warnings"])


def test_selection_review_payload_includes_omission_context():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_loop import build_selection_review_payload
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
        load_selection_review_profile,
    )
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-16",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    decision = build_test_selection_decision(pool, experiment)
    review_payload = build_selection_review_payload(
        selection_decision=decision,
        candidate_pool=pool,
        selection_validation=validate_selection_decision(decision, pool, experiment),
        review_profile=load_selection_review_profile(experiment["selection_review_profile"]),
        selection_config=experiment["selection"],
    )

    assert review_payload["selected"]
    assert review_payload["required_unselected_candidate_reviews"]
    assert review_payload["audit_candidates"]
    assert review_payload["public_card_count"]["selected"] == len(decision["selected"])


def test_selection_review_payload_surfaces_impact_and_card_count_challengers():
    from football_data.editorial_loop import build_selection_review_payload

    selected = _review_test_candidate(
        player_id="selected-vlasic",
        player_name="Nikola VLASIC",
        headline_rank=8,
        headline_score=64.72,
        impact_rank=4,
        impact_score=19.5,
        eligible_awards=["impact_pick"],
        metrics={"goals": 1, "match_winning_goal": 1},
        chips=["match-winning goal"],
    )
    impact_challenger = _review_test_candidate(
        player_id="omitted-kalajdzic",
        player_name="Sasa KALAJDZIC",
        headline_rank=21,
        headline_score=46.91,
        impact_rank=5,
        impact_score=19.5,
        eligible_awards=["impact_pick"],
        metrics={"goals": 1, "stoppage_time_goal": 1, "comeback_equalizer": 1},
        chips=["stoppage-time equaliser"],
    )
    metric_trap = _review_test_candidate(
        player_id="omitted-paredes",
        player_name="Leandro PAREDES",
        headline_rank=5,
        headline_score=87.11,
        impact_rank=171,
        impact_score=0.0,
        eligible_awards=["player_of_the_day"],
        metrics={"line_breaks_completed": 40},
        chips=["repeated line breaks"],
    )
    candidate_pool = {
        "match_date": "2026-06-27",
        "selectable_candidates": [selected, impact_challenger, metric_trap],
        "audit_candidates": [],
    }
    selection_decision = {
        "selected": [
            {
                "award_type": "impact_pick",
                "player_id": selected["player_id"],
                "player_name": selected["player_name"],
            }
        ]
    }
    review_profile = {
        "id": "selection_review_v1",
        "required_unselected_headline_top_n": 8,
        "required_unselected_impact_top_n": 5,
    }

    review_payload = build_selection_review_payload(
        selection_decision=selection_decision,
        candidate_pool=candidate_pool,
        selection_validation={"status": "pass", "warnings": []},
        review_profile=review_profile,
        selection_config={"public_card_count": {"min": 3, "max": 6}},
    )

    assert [item["player_id"] for item in review_payload["required_impact_candidate_reviews"]] == [
        "omitted-kalajdzic"
    ]
    assert review_payload["card_count_challengers"][0]["player_id"] == "omitted-kalajdzic"


def test_selection_review_validation_requires_challenger_verdict_references():
    from football_data.editorial_loop import validate_selection_review

    review_profile = {
        "id": "selection_review_v1",
        "required_dimensions": [
            "selected_card_convincingness",
            "obvious_omission",
            "alternative_slate_comparison",
            "weakest_selected_card",
            "strongest_omitted_card",
            "impact_challenger_comparison",
            "card_count_verdict",
        ],
        "required_slate_assessment_fields": [
            "reader_questions",
            "alternative_slate_comparison",
            "weakest_selected_card",
            "strongest_omitted_card",
            "drop_weakest_verdict",
            "replace_weakest_verdict",
            "impact_challenger_verdict",
            "add_card_verdict",
            "preferred_card_count",
            "revision_decision",
        ],
    }
    review_payload = {
        "selected": [{"player_id": "selected-vlasic"}],
        "required_impact_candidate_reviews": [{"player_id": "omitted-kalajdzic"}],
        "card_count_challengers": [{"player_id": "omitted-kalajdzic"}],
        "public_card_count": {"selected": 5, "min": 3, "max": 6},
    }
    review = {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": review_profile["required_dimensions"],
        "selected_player_reviews": [
            {"player_id": "selected-vlasic", "status": "pass", "note": "checked"}
        ],
        "unselected_candidate_reviews": [
            {"player_id": "omitted-kalajdzic", "status": "omit", "note": "checked"}
        ],
        "slate_assessment": {
            "reader_questions": ["Should the omitted impact case be added?"],
            "alternative_slate_comparison": [
                {"card_count": 5, "tradeoff": "current slate"},
                {"card_count": 6, "tradeoff": "add omitted impact case"},
            ],
            "weakest_selected_card": {"player_id": "selected-vlasic", "reason": "checked"},
            "strongest_omitted_card": {"player_id": "omitted-kalajdzic", "reason": "checked"},
            "drop_weakest_verdict": {"decision": "keep", "reason": "checked"},
            "replace_weakest_verdict": {
                "decision": "keep",
                "replacement_player_id": "omitted-kalajdzic",
                "reason": "checked",
            },
            "impact_challenger_verdict": {
                "player_id": "wrong-omission",
                "decision": "omit",
                "reason": "This does not review the required top-impact challenger.",
            },
            "add_card_verdict": {
                "player_id": "wrong-omission",
                "decision": "keep_count",
                "reason": "This does not review the strongest sixth-card challenger.",
            },
            "preferred_card_count": 5,
            "revision_decision": "keep",
        },
        "blocking_findings": [],
        "unresolved_objections": [],
        "revision_summary": "No issue remains.",
    }

    wrong_reference = validate_selection_review(review, review_profile, review_payload)

    assert wrong_reference["status"] == "failed"
    assert any("impact_challenger_verdict" in warning for warning in wrong_reference["warnings"])
    assert any("add_card_verdict" in warning for warning in wrong_reference["warnings"])

    review["slate_assessment"]["impact_challenger_verdict"]["player_id"] = "omitted-kalajdzic"
    review["slate_assessment"]["add_card_verdict"]["player_id"] = "omitted-kalajdzic"
    valid_reference = validate_selection_review(review, review_profile, review_payload)
    assert valid_reference["status"] == "pass"


def test_selection_review_validation_requires_slate_assessment_fields():
    from football_data.editorial_loop import validate_selection_review

    review_profile = {
        "id": "selection_review_v1",
        "required_dimensions": ["selected_card_convincingness"],
        "required_slate_assessment_fields": [
            "reader_questions",
            "alternative_slate_comparison",
            "weakest_selected_card",
            "revision_decision",
        ],
    }
    review_payload = {
        "selected": [{"player_id": "p1"}],
        "required_unselected_candidate_reviews": [],
    }
    missing_assessment = {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": ["selected_card_convincingness"],
        "selected_player_reviews": [{"player_id": "p1", "verdict": "pass", "note": "checked"}],
        "unselected_candidate_reviews": [],
        "blocking_findings": [],
        "unresolved_objections": [],
        "revision_summary": "No issue remains.",
    }

    missing_validation = validate_selection_review(
        missing_assessment,
        review_profile,
        review_payload,
    )
    assert missing_validation["status"] == "failed"
    assert any(
        "missing slate_assessment.reader_questions" in warning
        for warning in missing_validation["warnings"]
    )

    passing = {
        **missing_assessment,
        "slate_assessment": {
            "reader_questions": ["Why only three cards from four matches?"],
            "alternative_slate_comparison": [
                {"card_count": 3, "tradeoff": "elite only"},
                {"card_count": 4, "tradeoff": "better match coverage"},
            ],
            "weakest_selected_card": {"player_id": "p1", "reason": "checked"},
            "strongest_omitted_card": {"player_id": "p2", "reason": "checked"},
            "drop_weakest_verdict": {"decision": "keep", "reason": "checked"},
            "replace_weakest_verdict": {
                "decision": "keep",
                "replacement_player_id": "p2",
                "reason": "checked",
            },
            "preferred_card_count": 3,
            "revision_decision": "keep",
        },
    }
    passing_validation = validate_selection_review(passing, review_profile, review_payload)
    assert passing_validation["status"] == "pass"


def test_editorial_v2_goalkeeper_score_is_keeper_only_for_latest_day():
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import load_editorial_experiment

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    haaland = _player(rankings, "Erling HAALAND")
    abulaila = _player(rankings, "YAZEED ABULAILA")

    assert haaland["position"] == "FW"
    assert haaland["role_scores"]["goalkeeper"] == 0
    assert all(
        component["metric"] not in {"opponent_xg", "keeper_saved_shots"}
        for component in haaland["score_components"]
    )
    assert abulaila["position"] == "GK"
    assert abulaila["role_scores"]["goalkeeper"] > 0


def test_editorial_v2_shootout_penalty_save_counts_as_goalkeeper_impact(tmp_path):
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import load_editorial_experiment
    from football_data.fifa_timeline import ensure_fifa_timeline_schema

    db_path = tmp_path / "latest.sqlite"
    shutil.copyfile("data/latest.sqlite", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_fifa_timeline_schema(conn)
        keeper = conn.execute(
            """
            select m.match_key, m.match_date, m.home_team, m.away_team,
                   a.team, a.player_name
            from matches m
            join player_appearances a using(match_key)
            where m.match_no = 73
              and a.team = m.home_team
              and a.position = 'GK'
              and a.started = 1
            """
        ).fetchone()
        teammate = conn.execute(
            """
            select a.player_name
            from player_appearances a
            where a.match_key = ?
              and a.team = ?
              and a.position <> 'GK'
            order by a.player_no
            limit 1
            """,
            (keeper["match_key"], keeper["team"]),
        ).fetchone()
        conn.execute(
            """
            insert into official_match_events(
              match_key, fifa_match_id, event_id, event_order, event_type,
              event_type_name, event_timestamp, period, match_minute, minute,
              stoppage_minute, absolute_minute, team_id, team_name, player_id,
              player_name, related_player_id, home_goals, away_goals,
              home_penalty_goals, away_penalty_goals, penalty_result,
              penalty_miss_type, penalty_keeper_player_id, penalty_keeper_name,
              penalty_keeper_team_id, penalty_keeper_team_name, description,
              raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                keeper["match_key"],
                "synthetic-match",
                "synthetic-shootout-save",
                1,
                60,
                "Penalty missed",
                "2026-06-28T22:00:00Z",
                11,
                None,
                None,
                None,
                None,
                "away-team",
                keeper["away_team"],
                "shooter",
                "Synthetic SHOOTER",
                "keeper-id",
                0,
                1,
                0,
                1,
                "missed",
                "saved",
                "keeper-id",
                keeper["player_name"],
                "keeper-team",
                keeper["team"],
                "Synthetic SHOOTER has their penalty shoot-out kick saved.",
                "{}",
            ),
        )
        conn.commit()
        match_date = keeper["match_date"]
        keeper_name = keeper["player_name"]
        teammate_name = teammate["player_name"]
    finally:
        conn.close()

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(db_path, match_date, experiment["scoring_config"])
    player = _player(rankings, keeper_name)
    teammate_player = _player(rankings, teammate_name)

    assert player["shootout_penalty_saves"] == 1
    assert player["metrics"]["shootout_penalty_saves"] == 1
    assert teammate_player["shootout_penalty_saves"] == 0
    assert player["role_scores"]["impact"] > 0
    assert player["role_scores"]["goalkeeper"] > 0
    assert any(component["metric"] == "shootout_penalty_saves" for component in player["score_components"])
    assert "shoot-out penalty save" in player["evidence_chips"]["en"]


def test_editorial_v2_candidate_pool_keeps_role_candidates_audit_only_latest_day():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )

    public_awards = {"player_of_the_day", "impact_pick"}
    assert all(
        set(candidate.get("eligible_awards", [])) <= public_awards
        for candidate in pool["selectable_candidates"]
    )
    assert not [
        candidate
        for candidate in pool["selectable_candidates"]
        if {"progression_pick", "defensive_pick", "goalkeeper_watch", "hidden_gem"}
        & set(candidate.get("eligible_awards", []))
    ]

    progression_candidates = [
        candidate
        for candidate in pool["audit_candidates"]
        if candidate.get("audit_type") == "progression_pick"
    ]
    progression_names = {candidate["player_name"] for candidate in progression_candidates}

    assert "Dayot UPAMECANO" not in progression_names
    assert {"ZIDANE IQBAL", "Rayan AIT-NOURI", "Enzo FERNANDEZ"} & progression_names
    assert all(
        (candidate.get("progression_benchmark") or {}).get("quality") in {"strong", "useful"}
        and not (candidate.get("progression_benchmark") or {}).get("pass_only_line_break_volume")
        for candidate in progression_candidates
    )
    assert not [
        candidate
        for candidate in pool["audit_candidates"]
        if candidate.get("audit_type") == "goalkeeper_watch"
    ]


def test_editorial_v2_candidate_pool_includes_configured_zh_display_names():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-23",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )

    ronaldo = _candidate(pool, "CRISTIANO RONALDO")
    bruno = _candidate(pool, "BRUNO FERNANDES")

    assert ronaldo["display_names"]["zh"]["display_name"] == "C罗"
    assert bruno["display_names"]["zh"] == {
        "display_name": "布鲁诺-费尔南德斯",
        "short_name": "B费",
    }


def test_editorial_v2_selector_input_keeps_audit_progression_guard_fields_out_of_public_selection():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_selection import build_selector_input

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    selector_input = build_selector_input(pool, experiment)
    assert all(
        "progression_pick" not in candidate.get("eligible_awards", [])
        for candidate in selector_input["candidate_pool"]["selectable_candidates"]
    )
    zidane = _selector_audit_candidate(selector_input, "ZIDANE IQBAL", "progression_pick")

    assert zidane["progression_benchmark"]["quality"] == "strong"
    assert zidane["progression_benchmark"]["support_actions"] > 0
    assert zidane["progression_benchmark"]["pass_only_line_break_volume"] is False


def test_editorial_v2_potd_context_keeps_off_ball_as_supporting_evidence():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    gouiri = _candidate(pool, "Amine GOUIRI")
    potd_context = gouiri["award_contexts"]["player_of_the_day"]

    assert {"goals", "on_target"} <= set(potd_context["metrics"])
    assert "in_between" not in potd_context["metrics"]
    assert "in_behind" not in potd_context["metrics"]
    assert "offers_received" not in potd_context["metrics"]
    assert "between-line presence" not in potd_context["evidence_chips"]["en"]
    assert "found again and again" not in potd_context["evidence_chips"]["en"]


def test_editorial_v2_hidden_gem_audit_excludes_headline_and_goal_involvement_cases():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool_config = load_candidate_pool_config(experiment["candidate_pool"])
    pool = build_candidate_pool(rankings, pool_config)
    hidden_candidates = [
        candidate
        for candidate in pool["audit_candidates"]
        if candidate.get("audit_type") == "hidden_gem"
    ]

    assert "Sadio MANE" not in {candidate["player_name"] for candidate in hidden_candidates}
    assert all(int(candidate.get("goal_involvements") or 0) == 0 for candidate in hidden_candidates)
    assert all(
        int(candidate.get("headline_rank") or 9999) > int(pool_config["potd_top_n"])
        for candidate in hidden_candidates
    )
    assert all(
        not (
            int(candidate.get("opponent_final_goals") or 0) >= 3
            and int(candidate.get("team_final_goals") or 0)
            - int(candidate.get("opponent_final_goals") or 0)
            <= -2
        )
        for candidate in hidden_candidates
    )


def test_editorial_v2_test_selector_prefers_direct_potd_case_and_slate_constraints():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    decision = build_test_selection_decision(pool, experiment)
    potd_names = [
        item["player_name"]
        for item in decision["selected"]
        if item["award_type"] == "player_of_the_day"
    ]
    validation = validate_selection_decision(decision, pool, experiment)

    assert [item["player_name"] for item in decision["selected"]][:3] == [
        "Kylian MBAPPE",
        "Lionel MESSI",
        "Erling HAALAND",
    ]
    assert 3 <= len(decision["selected"]) <= 6
    assert potd_names == [item["player_name"] for item in decision["selected"]]
    assert validation["status"] == "pass"

    overconcentrated = {
        "selected": [
            _selected(_candidate(pool, "Kylian MBAPPE"), "player_of_the_day"),
            _selected(_candidate(pool, "Ousmane DEMBELE"), "player_of_the_day"),
            _selected(_candidate(pool, "Michael OLISE"), "player_of_the_day"),
            _selected(_candidate(pool, "Kylian MBAPPE"), "impact_pick"),
            _selected(_candidate(pool, "Lionel MESSI"), "player_of_the_day"),
        ],
        "skipped_higher_ranked": [],
        "skipped_notable_candidates": [],
        "warnings": [],
    }
    bad_validation = validate_selection_decision(overconcentrated, pool, experiment)

    assert bad_validation["status"] == "failed"
    assert any("FIFA-2026-M42-FRA-IRQ exceeds max_per_match 3" in warning for warning in bad_validation["warnings"])

    duplicate_player = {
        "selected": [
            _selected(_candidate(pool, "Kylian MBAPPE"), "player_of_the_day"),
            _selected(_candidate(pool, "Kylian MBAPPE"), "impact_pick"),
        ],
        "skipped_higher_ranked": [],
        "skipped_notable_candidates": [],
        "warnings": [],
    }
    duplicate_validation = validate_selection_decision(duplicate_player, pool, experiment)

    assert duplicate_validation["status"] == "failed"
    assert any("selected for multiple awards" in warning for warning in duplicate_validation["warnings"])


def test_editorial_v2_slate_balance_allows_angle_omissions_and_blocks_fourth_match_card():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    balanced = {
        "selected": [
            _selected(_candidate(pool, "Kylian MBAPPE"), "player_of_the_day"),
            _selected(_candidate(pool, "Lionel MESSI"), "player_of_the_day"),
            _selected(_candidate(pool, "Erling HAALAND"), "player_of_the_day"),
            _selected(_candidate(pool, "Amine GOUIRI"), "impact_pick"),
            _selected(_candidate(pool, "Ismaila SARR"), "player_of_the_day"),
        ],
        "skipped_higher_ranked": [
            {
                "award_type": "player_of_the_day",
                "player_id": _candidate(pool, "Amine GOUIRI")["player_id"],
                "player_name": "Amine GOUIRI",
                "coarse_rank": 3,
                "reason": "Gouiri is kept as the impact pick so Haaland's brace and winner can stay in Player of the Day.",
            }
        ],
        "skipped_notable_candidates": [],
        "warnings": [],
    }
    overconcentrated = json.loads(json.dumps(balanced, ensure_ascii=False))
    overconcentrated["selected"] = [
        _selected(_candidate(pool, "Kylian MBAPPE"), "player_of_the_day"),
        _selected(_candidate(pool, "Ousmane DEMBELE"), "player_of_the_day"),
        _selected(_candidate(pool, "Michael OLISE"), "player_of_the_day"),
        _selected(_candidate(pool, "Kylian MBAPPE"), "impact_pick"),
        _selected(_candidate(pool, "Lionel MESSI"), "player_of_the_day"),
    ]

    balanced_validation = validate_selection_decision(balanced, pool, experiment)
    overconcentrated_validation = validate_selection_decision(overconcentrated, pool, experiment)

    assert balanced_validation["status"] == "pass"
    assert overconcentrated_validation["status"] == "failed"
    assert any("FIFA-2026-M42-FRA-IRQ exceeds max_per_match 3" in warning for warning in overconcentrated_validation["warnings"])


def test_editorial_v2_copy_validation_rejects_configured_chinese_public_terms():
    from football_data.editorial_copy_validation import validate_copy

    copy = {
        "en": {"items": [], "warnings": []},
        "zh": {
            "items": [
                {
                    "award_type": "player_of_the_day",
                    "player_id": "p1",
                    "title": "姆巴佩梅开二度",
                    "body": "这句包含禁用公共词，应该被拦住。",
                    "warnings": [],
                },
                {
                    "award_type": "player_of_the_day",
                    "player_id": "p2",
                    "title": "努诺-门德斯进球又推进",
                    "body": "他还有11次打穿防线、8次推进和6次夺回球权，这场不是只在边路补一个进球。",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }
    zh_profile = {
        "banned_public_terms": ["禁用公共词"],
        "unsupported_public_terms": ["不是只在", "补一个进球"],
    }

    validation = validate_copy(copy, {"zh": zh_profile})

    assert validation["status"] == "failed"
    assert any("banned zh public term '禁用公共词'" in warning for warning in validation["warnings"])
    assert any("unsupported zh public term '不是只在'" in warning for warning in validation["warnings"])
    assert any("unsupported zh public term '补一个进球'" in warning for warning in validation["warnings"])


def test_editorial_v2_copy_validation_requires_zh_title_core_fact():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_copy_validation import validate_copy
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_profile,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    messi = _candidate(pool, "Lionel MESSI")
    haaland = _candidate(pool, "Erling HAALAND")
    payload = build_copy_payloads(
        {
            "selected": [
                _selected(messi, "player_of_the_day"),
                _selected(haaland, "player_of_the_day"),
            ],
            "skipped_higher_ranked": [],
            "skipped_notable_candidates": [],
        },
        pool,
    )
    copy = {
        "en": {"items": [], "warnings": []},
        "zh": {
            "items": [
                {
                    "award_type": "player_of_the_day",
                    "player_id": messi["player_id"],
                    "title": "梅西补时再进",
                    "body": "梅西第37分钟先破门，补时阶段又进一个。阿根廷2-0赢奥地利。",
                    "warnings": [],
                },
                {
                    "award_type": "player_of_the_day",
                    "player_id": haaland["player_id"],
                    "title": "哈兰德双响制胜禁用标题词",
                    "body": "哈兰德第47分钟、第57分钟各进一球，第二球后来成了制胜球。",
                    "warnings": [],
                },
            ],
            "warnings": [],
        },
    }
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    zh_profile = {
        **zh_profile,
        "title_policy": {
            **zh_profile["title_policy"],
            "banned_title_terms": ["禁用标题词"],
        },
    }

    validation = validate_copy(copy, {"zh": zh_profile}, copy_payload=payload)

    assert validation["status"] == "failed"
    assert any("missing zh title core fact goals>=2" in warning for warning in validation["warnings"])
    assert any("banned zh title term '禁用标题词'" in warning for warning in validation["warnings"])


def test_editorial_v2_copy_validation_accepts_hat_trick_title_as_core_fact():
    from football_data.editorial_copy_validation import validate_copy

    copy_payload = {
        "choices": [
            {
                "player_id": "player-1",
                "metrics": {"goals": 3},
            }
        ]
    }
    copy = {
        "zh": {
            "items": [
                {
                    "award_type": "player_of_the_day",
                    "player_id": "player-1",
                    "title": "梅西帽子戏法",
                    "body": "阿根廷3-0赢球，三个球都由梅西打进。",
                    "warnings": [],
                }
            ],
            "warnings": [],
        }
    }

    validation = validate_copy(
        copy,
        {"zh": {"title_policy": {"mode": "core_fact_label"}}},
        copy_payload=copy_payload,
    )

    assert validation["status"] == "pass"


def test_editorial_v2_test_copy_is_publishable_static_copy():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-22",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )
    haaland = _candidate(pool, "Erling HAALAND")
    payload = build_copy_payloads(
        {
            "selected": [_selected(haaland, "player_of_the_day")],
            "skipped_higher_ranked": [],
            "skipped_notable_candidates": [],
        },
        pool,
    )

    copy = build_test_copy(payload)
    en_item = copy["en"]["items"][0]
    zh_item = copy["zh"]["items"][0]

    assert "candidate pool" not in en_item["body"]
    assert "stays in the edit" not in en_item["title"]
    assert "候选池" not in zh_item["body"]
    assert "留在编辑精选里" not in zh_item["title"]
    assert "without needing extra decoration" not in en_item["body"]
    assert "two goals" in en_item["body"]
    assert "match-winner" in en_item["body"]
    assert "梅开二度" in zh_item["body"]
    assert "制胜球" in zh_item["body"]
    assert "Erling HAALAND" in zh_item["body"]


def test_editorial_v2_rankings_and_candidate_pool_include_audit_context():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_selection import build_selector_input

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings(
        "data/latest.sqlite",
        "2026-06-21",
        experiment["scoring_config"],
    )
    pool = build_candidate_pool(
        rankings,
        load_candidate_pool_config(experiment["candidate_pool"]),
    )

    assert rankings["match_date"] == "2026-06-21"
    assert rankings["scoring_version"] == "v0.4"
    assert rankings["players"]
    assert rankings["rankings"]["headline"]
    first = rankings["rankings"]["headline"][0]
    assert first["player_id"]
    assert first["headline_rank"] == 1
    assert isinstance(first["score_components"], list)

    assert pool["selectable_candidates"]
    assert pool["audit_candidates"]
    assert pool["near_misses"]
    assert all(candidate["pool_reasons"] for candidate in pool["selectable_candidates"])
    assert {candidate["player_id"] for candidate in pool["selectable_candidates"]}
    assert all(candidate.get("award_contexts") for candidate in pool["selectable_candidates"])
    assert all(
        set(candidate.get("award_contexts", {})) <= {"player_of_the_day", "impact_pick"}
        for candidate in pool["selectable_candidates"]
    )
    assert any(candidate.get("audit_type") == "defensive_pick" for candidate in pool["audit_candidates"])
    selector_input = build_selector_input(pool, experiment)
    assert len(json.dumps(selector_input, ensure_ascii=False)) < 80_000
    selector_candidate = selector_input["candidate_pool"]["selectable_candidates"][0]
    assert "award_contexts" in selector_candidate
    assert "audit_candidates" in selector_input["candidate_pool"]
    assert "score_components" not in selector_candidate["award_contexts"]["player_of_the_day"]


def test_editorial_v2_selection_validation_requires_pool_membership_and_skip_reasons():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings("data/latest.sqlite", "2026-06-21", experiment["scoring_config"])
    pool = build_candidate_pool(rankings, load_candidate_pool_config(experiment["candidate_pool"]))

    decision = build_test_selection_decision(pool, experiment)
    validation = validate_selection_decision(decision, pool, experiment)
    assert validation["status"] == "pass"
    assert validation["warnings"] == []

    bad_decision = json.loads(json.dumps(decision))
    bad_decision["selected"][0]["player_id"] = "missing-player"
    bad_validation = validate_selection_decision(bad_decision, pool, experiment)
    assert bad_validation["status"] == "failed"
    assert any("not in candidate pool" in warning for warning in bad_validation["warnings"])

    lower_ranked = json.loads(json.dumps(decision))
    potd = [
        candidate
        for candidate in pool["selectable_candidates"]
        if candidate.get("headline_rank") and candidate["headline_rank"] > 1
    ][0]
    lower_ranked["selected"][0]["player_id"] = potd["player_id"]
    lower_ranked["selected"][0]["player_name"] = potd["player_name"]
    lower_ranked["selected"][0]["team"] = potd["team"]
    lower_ranked["skipped_higher_ranked"] = []
    lower_validation = validate_selection_decision(lower_ranked, pool, experiment)
    assert lower_validation["status"] == "failed"
    assert any("skipped_higher_ranked" in warning for warning in lower_validation["warnings"])

    too_few_public_cards = json.loads(json.dumps(decision))
    too_few_public_cards["selected"] = too_few_public_cards["selected"][:2]
    too_few_validation = validate_selection_decision(too_few_public_cards, pool, experiment)
    assert too_few_validation["status"] == "failed"
    assert any("outside public_card_count range 3-6" in warning for warning in too_few_validation["warnings"])

    four_public_cards = json.loads(json.dumps(decision))
    four_public_cards["selected"] = four_public_cards["selected"][:4]
    four_validation = validate_selection_decision(four_public_cards, pool, experiment)
    assert four_validation["status"] == "pass"

    from football_data.editorial_selection import normalize_selection_decision

    role_public_card = json.loads(json.dumps(decision))
    role_public_card["selected"][-1]["award_type"] = "progression_pick"
    role_validation = validate_selection_decision(role_public_card, pool, experiment)
    assert role_validation["status"] == "failed"
    assert any("progression_pick is not an allowed public award type" in warning for warning in role_validation["warnings"])

    polluted_experiment = json.loads(json.dumps(experiment))
    polluted_experiment["selection"]["award_limits"]["progression_pick"] = 1
    polluted_validation = validate_selection_decision(role_public_card, pool, polluted_experiment)
    assert polluted_validation["status"] == "failed"
    assert any(
        "progression_pick is not an allowed public award type" in warning
        for warning in polluted_validation["warnings"]
    )

    aliased = json.loads(json.dumps(decision))
    aliased["selected"][-2]["award_type"] = "progression"
    aliased["selected"][-1]["award_type"] = "defensive"
    maxi = _candidate(pool, "Maxi ARAUJO")
    aliased["skipped_higher_ranked"] = [
        {
            "award_type": "player_of_the_day",
            "player_id": maxi["player_id"],
            "player_name": "Maxi ARAUJO",
            "coarse_rank": maxi["headline_rank"],
            "reason": "Kept as a documented higher-ranked skip in the alias normalization regression scenario.",
        }
    ]
    normalized = normalize_selection_decision(aliased)
    normalized_validation = validate_selection_decision(normalized, pool, experiment)
    assert normalized_validation["status"] == "failed"
    assert not normalized["warnings"]
    assert any("progression is not an allowed public award type" in warning for warning in normalized_validation["warnings"])
    assert any("defensive is not an allowed public award type" in warning for warning in normalized_validation["warnings"])

    weak_selection = json.loads(json.dumps(decision))
    weak_selection["selected"][0]["editorial_reason"] = "en"
    weak_selection["selected"][0]["evidence_used"] = ["brce", "unsupported but long evidence phrase"]
    weak_selection["selected"][0]["selection_risk"] = "low"
    weak_validation = validate_selection_decision(weak_selection, pool, experiment)
    assert weak_validation["status"] == "failed"
    assert any("editorial_reason is too weak" in warning for warning in weak_validation["warnings"])
    assert any("evidence_used must include meaningful evidence" in warning for warning in weak_validation["warnings"])
    assert any("selection_risk is too weak" in warning for warning in weak_validation["warnings"])


def test_editorial_copy_sanitizes_common_metric_misread():
    from football_data.editorial_copy import sanitize_copy_body

    body = "He offered 28 times behind the defense and completed 9 line breaks."

    assert sanitize_copy_body(body) == "He received 28 offers and completed 9 line breaks."


def _player(rankings: dict, player_name: str) -> dict:
    return next(player for player in rankings["players"] if player["player_name"] == player_name)


def _candidate(candidate_pool: dict, player_name: str) -> dict:
    return next(
        candidate
        for candidate in candidate_pool["selectable_candidates"]
        if candidate["player_name"] == player_name
    )


def _selector_candidate(selector_input: dict, player_name: str) -> dict:
    return next(
        candidate
        for candidate in selector_input["candidate_pool"]["selectable_candidates"]
        if candidate["player_name"] == player_name
    )


def _selector_audit_candidate(selector_input: dict, player_name: str, audit_type: str) -> dict:
    return next(
        candidate
        for candidate in selector_input["candidate_pool"]["audit_candidates"]
        if candidate["player_name"] == player_name and candidate["audit_type"] == audit_type
    )


def _review_required_unselected_items(review_payload: dict) -> list[dict]:
    seen: set[str] = set()
    required: list[dict] = []
    for key in (
        "required_unselected_candidate_reviews",
        "required_impact_candidate_reviews",
        "card_count_challengers",
    ):
        for item in review_payload.get(key, []):
            if not isinstance(item, dict):
                continue
            player_id = str(item.get("player_id") or "")
            if not player_id or player_id in seen:
                continue
            seen.add(player_id)
            required.append(item)
    return required


def _first_review_player_id(items: list[dict]) -> str | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        player_id = str(item.get("player_id") or "").strip()
        if player_id:
            return player_id
    return None


def _selected(candidate: dict, award_type: str) -> dict:
    return {
        "award_type": award_type,
        "player_id": candidate["player_id"],
        "player_name": candidate["player_name"],
        "team": candidate["team"],
        "editorial_reason": "Selected in a regression scenario.",
        "evidence_used": ["Direct candidate evidence from regression fixture."],
        "selection_risk": "Review final copy for precise match context before publishing.",
    }


def _review_test_candidate(
    *,
    player_id: str,
    player_name: str,
    headline_rank: int,
    headline_score: float,
    impact_rank: int,
    impact_score: float,
    eligible_awards: list[str],
    metrics: dict,
    chips: list[str],
) -> dict:
    award_contexts = {
        award_type: {
            "metrics": metrics,
            "evidence_chips": {
                "en": chips,
                "zh": chips,
            },
        }
        for award_type in eligible_awards
    }
    return {
        "player_id": player_id,
        "player_name": player_name,
        "team": player_name.split()[-1],
        "opponent": "Opponent",
        "match_key": f"match-{player_id}",
        "match_no": headline_rank,
        "player_no": headline_rank,
        "headline_rank": headline_rank,
        "impact_rank": impact_rank,
        "headline_score": headline_score,
        "rank_score": headline_score,
        "role_scores": {"impact": impact_score},
        "eligible_awards": eligible_awards,
        "award_contexts": award_contexts,
        "display_names": {},
        "data_sources": {},
    }
