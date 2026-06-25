import json
from pathlib import Path

def test_editorial_v2_registry_resolves_default_experiment():
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_profile,
        load_editorial_experiment,
        load_review_profile,
        load_selector_profile,
    )
    from football_data.editorial_display_names import player_display_entry, player_display_name

    experiment = load_editorial_experiment()

    assert experiment["id"] == "ai_rerank_reader_loop_v5"
    assert experiment["workflow_variant"] == "ai_rerank_selection_v1"
    assert experiment["selection"]["mode"] == "ai_rerank_only"
    assert experiment["candidate_pool"] == "guarded_packet_v2"
    assert experiment["selector_profile"] == "slate_balanced_editor_v3"
    assert experiment["review_profile"] == "reader_intuition_loop_v2"
    assert experiment["revision_policy"]["mode"] == "reader_critic_revise_review_loop"
    assert experiment["reader_intuition_loop"]["mode"] == "slate_critic_then_revision"
    assert experiment["copy_profiles"]["zh"] == "zh_matchnote_light_emotion_v1"
    assert experiment["selection"]["strategy"] == "overall_slate_v1"
    assert experiment["selection"]["public_card_count"]["min"] == 3
    assert experiment["selection"]["public_card_count"]["max"] == 6
    assert experiment["selection"]["public_card_count"]["recommended_by_match_count"][0] == {
        "match_count_min": 1,
        "match_count_max": 2,
        "recommended": 4,
    }
    assert experiment["selection"]["award_limits"]["progression_pick"] == 1
    assert experiment["selection"]["optional_awards"] == [
        "player_of_the_day",
        "impact_pick",
        "progression_pick",
        "defensive_pick",
        "goalkeeper_watch",
        "hidden_gem",
    ]
    assert experiment["selection"]["slate_constraints"] == {
        "max_per_match": 3,
        "max_per_team": 3,
    }
    assert player_display_name("CRISTIANO RONALDO", "zh") == "C罗"
    assert player_display_entry("BRUNO FERNANDES", "zh") == {
        "display_name": "布鲁诺-费尔南德斯",
        "short_name": "B费",
    }

    pool = load_candidate_pool_config(experiment["candidate_pool"])
    selector = load_selector_profile(experiment["selector_profile"])
    review_profile = load_review_profile(experiment["review_profile"])
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    en_profile = load_copy_profile(experiment["copy_profiles"]["en"])

    assert pool["potd_top_n"] == 8
    assert selector["allowed_selection_source"] == "candidate_pool_only"
    assert any("Fact accuracy" in item for item in selector["instructions"])
    assert any("same match" in item for item in selector["instructions"])
    assert any("not a quota" in item for item in selector["instructions"])
    assert review_profile["required_dimensions"] == [
        "obvious_omission",
        "slate_balance",
        "match_coverage_pressure",
        "reader_question_prediction",
        "alternative_slate_comparison",
        "metric_misuse",
        "copy_style",
        "display_names",
    ]
    assert review_profile["required_slate_assessment_fields"] == [
        "match_coverage_pressure",
        "reader_questions",
        "alternative_slate_comparison",
        "weakest_selected_card",
        "strongest_omitted_card",
        "revision_decision",
    ]
    assert zh_profile["language"] == "zh"
    assert zh_profile["instructions"]
    assert isinstance(zh_profile.get("banned_public_terms"), list)
    assert zh_profile["banned_public_terms"]
    assert zh_profile["title_policy"]["mode"] == "core_fact_label"
    assert isinstance(zh_profile["title_policy"].get("banned_title_terms"), list)
    assert en_profile["language"] == "en"
    assert en_profile["instructions"]

    retired_paths = [
        "config/editorial/experiments/ai_rerank_baseline_v1.json",
        "config/editorial/experiments/ai_rerank_guardrails_v2.json",
        "config/editorial/experiments/ai_rerank_slate_copy_v3.json",
        "config/editorial/experiments/ai_rerank_slate_self_review_v4.json",
        "config/editorial/review_profiles/reader_intuition_v1.json",
        "config/editorial/candidate_pools/rich_packet_v1.json",
        "config/editorial/selector_profiles/strict_editor_v1.json",
        "config/editorial/selector_profiles/guarded_editor_v2.json",
        "config/editorial/copy_profiles/zh_natural_v1.json",
    ]
    assert not [path for path in retired_paths if Path(path).exists()]


def test_editorial_review_validation_requires_reader_intuition_coverage():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
        load_review_profile,
    )
    from football_data.editorial_review import build_editorial_review_payload, validate_editorial_review
    from football_data.editorial_selection import fake_selection_decision
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
    decision = fake_selection_decision(pool, experiment)
    copy_payload = build_copy_payloads(decision, pool)
    copy = generate_copy(copy_payload, fake=True)
    review_payload = build_editorial_review_payload(
        selection_decision=decision,
        candidate_pool=pool,
        copy=copy,
        selection_validation=validate_selection_decision(decision, pool, experiment),
        review_profile=load_review_profile(experiment["review_profile"]),
        selection_config=experiment["selection"],
    )
    review_profile = load_review_profile(experiment["review_profile"])
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
        for item in review_payload["required_unselected_candidate_reviews"]
    ]
    good_review = {
        "schema_version": 1,
        "review_profile": review_profile["id"],
        "status": "pass",
        "reviewed_dimensions": review_profile["required_dimensions"],
        "slate_assessment": {
            "match_coverage_pressure": "Selected count was reviewed against the day's match count.",
            "reader_questions": ["Does the slate omit an obvious direct-impact player?"],
            "alternative_slate_comparison": [
                {"card_count": len(decision["selected"]), "tradeoff": "current slate"},
                {"card_count": len(decision["selected"]) + 1, "tradeoff": "broader coverage"},
            ],
            "weakest_selected_card": "No selected card raised a blocking concern.",
            "strongest_omitted_card": "No omitted card required revision.",
            "revision_decision": "No blocking reader-intuition issue remains.",
        },
        "selected_player_reviews": selected_reviews,
        "unselected_candidate_reviews": unselected_reviews,
        "blocking_findings": [],
        "revision_summary": "No blocking reader-intuition issue remains.",
    }

    good_validation = validate_editorial_review(good_review, review_profile, review_payload)
    assert good_validation["status"] == "pass"

    missing_unselected = json.loads(json.dumps(good_review, ensure_ascii=False))
    missing_unselected["unselected_candidate_reviews"] = missing_unselected["unselected_candidate_reviews"][:-1]
    missing_validation = validate_editorial_review(missing_unselected, review_profile, review_payload)
    assert missing_validation["status"] == "failed"
    assert any("missing unselected candidate review" in warning for warning in missing_validation["warnings"])

    blocking = json.loads(json.dumps(good_review, ensure_ascii=False))
    blocking["blocking_findings"] = [
        {
            "category": "obvious_omission",
            "severity": "high",
            "evidence": "Two-goal winner is still outside the slate.",
            "recommended_action": "Revise selection before publishing.",
        }
    ]
    blocking_validation = validate_editorial_review(blocking, review_profile, review_payload)
    assert blocking_validation["status"] == "failed"
    assert any("blocking finding" in warning for warning in blocking_validation["warnings"])


def test_editorial_review_payload_includes_slate_coverage_context():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
        load_review_profile,
    )
    from football_data.editorial_review import build_editorial_review_payload
    from football_data.editorial_selection import fake_selection_decision
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
    decision = fake_selection_decision(pool, experiment)
    copy = generate_copy(build_copy_payloads(decision, pool), fake=True)
    review_payload = build_editorial_review_payload(
        selection_decision=decision,
        candidate_pool=pool,
        copy=copy,
        selection_validation=validate_selection_decision(decision, pool, experiment),
        review_profile=load_review_profile(experiment["review_profile"]),
        selection_config=experiment["selection"],
    )

    coverage = review_payload["match_coverage"]
    assert coverage["match_count"] == 4
    assert coverage["recommended_public_cards"] == 5
    assert coverage["selected_count"] == len(decision["selected"])
    assert coverage["top_candidates_by_match"]
    assert all("top_candidates" in item for item in coverage["top_candidates_by_match"])


def test_editorial_review_validation_requires_slate_assessment_fields():
    from football_data.editorial_review import validate_editorial_review

    review_profile = {
        "id": "reader_intuition_loop_v2",
        "required_dimensions": ["match_coverage_pressure"],
        "required_slate_assessment_fields": [
            "match_coverage_pressure",
            "reader_questions",
            "alternative_slate_comparison",
        ],
    }
    review_payload = {
        "selected": [],
        "required_unselected_candidate_reviews": [],
    }
    missing_assessment = {
        "schema_version": 1,
        "review_profile": "reader_intuition_loop_v2",
        "status": "pass",
        "reviewed_dimensions": ["match_coverage_pressure"],
        "selected_player_reviews": [],
        "unselected_candidate_reviews": [],
        "blocking_findings": [],
        "revision_summary": "No issue remains.",
    }

    missing_validation = validate_editorial_review(
        missing_assessment,
        review_profile,
        review_payload,
    )
    assert missing_validation["status"] == "failed"
    assert any(
        "missing slate_assessment.match_coverage_pressure" in warning
        for warning in missing_validation["warnings"]
    )

    passing = {
        **missing_assessment,
        "slate_assessment": {
            "match_coverage_pressure": "Four matches need a conscious slate-size decision.",
            "reader_questions": ["Why only three cards from four matches?"],
            "alternative_slate_comparison": [
                {"card_count": 3, "tradeoff": "elite only"},
                {"card_count": 4, "tradeoff": "better match coverage"},
            ],
        },
    }
    passing_validation = validate_editorial_review(passing, review_profile, review_payload)
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


def test_editorial_v2_candidate_pool_guards_progression_and_goalkeeper_watch_latest_day():
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

    progression_candidates = [
        candidate
        for candidate in pool["selectable_candidates"]
        if "progression_pick" in candidate.get("eligible_awards", [])
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
        for candidate in pool["selectable_candidates"]
        if "goalkeeper_watch" in candidate.get("eligible_awards", [])
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


def test_editorial_v2_selector_input_keeps_progression_guard_fields():
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
    zidane = _selector_candidate(selector_input, "ZIDANE IQBAL")

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


def test_editorial_v2_hidden_gem_excludes_headline_and_goal_involvement_cases():
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
        for candidate in pool["selectable_candidates"]
        if "hidden_gem" in candidate.get("eligible_awards", [])
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


def test_editorial_v2_fake_selector_prefers_direct_potd_case_and_slate_constraints():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_selection import fake_selection_decision
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
    decision = fake_selection_decision(pool, experiment)
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
            _selected(_candidate(pool, "Amine GOUIRI"), "player_of_the_day"),
            _selected(_candidate(pool, "Nadhir BENBOUALI"), "impact_pick"),
            _selected(_candidate(pool, "Rayan AIT-NOURI"), "progression_pick"),
            _selected(_candidate(pool, "MOHANNAD ABUTAHA"), "defensive_pick"),
            _selected(_candidate(pool, "Kylian MBAPPE"), "player_of_the_day"),
        ],
        "skipped_higher_ranked": [],
        "skipped_notable_candidates": [],
        "warnings": [],
    }
    bad_validation = validate_selection_decision(overconcentrated, pool, experiment)

    assert bad_validation["status"] == "failed"
    assert any("FIFA-2026-M44-JOR-ALG exceeds max_per_match 3" in warning for warning in bad_validation["warnings"])

    duplicate_player = {
        "selected": [
            _selected(_candidate(pool, "Ibrahim MAZA"), "progression_pick"),
            _selected(_candidate(pool, "Ibrahim MAZA"), "hidden_gem"),
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
            _selected(_candidate(pool, "Ibrahim MAZA"), "progression_pick"),
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
        _selected(_candidate(pool, "Amine GOUIRI"), "player_of_the_day"),
        _selected(_candidate(pool, "Nadhir BENBOUALI"), "impact_pick"),
        _selected(_candidate(pool, "Rayan AIT-NOURI"), "progression_pick"),
        _selected(_candidate(pool, "MOHANNAD ABUTAHA"), "defensive_pick"),
    ]

    balanced_validation = validate_selection_decision(balanced, pool, experiment)
    overconcentrated_validation = validate_selection_decision(overconcentrated, pool, experiment)

    assert balanced_validation["status"] == "pass"
    assert overconcentrated_validation["status"] == "failed"
    assert any("FIFA-2026-M44-JOR-ALG exceeds max_per_match 3" in warning for warning in overconcentrated_validation["warnings"])


def test_editorial_v2_copy_validation_rejects_abstract_chinese_public_terms():
    from football_data.editorial_copy_validation import validate_copy

    term = "禁用公共词"
    zh_profile = {"banned_public_terms": [term]}
    copy = {
        "en": {"items": [], "warnings": []},
        "zh": {
            "items": [
                {
                    "award_type": "player_of_the_day",
                    "player_id": "p1",
                    "title": "姆巴佩梅开二度",
                    "body": f"这句包含{term}，应该被拦住。",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validation = validate_copy(copy, {"zh": zh_profile})

    assert validation["status"] == "failed"
    assert any(f"banned zh public term {term!r}" in warning for warning in validation["warnings"])


def test_editorial_v2_copy_validation_rejects_configured_unsupported_claim_terms():
    from football_data.editorial_copy_validation import validate_copy

    copy = {
        "en": {"items": [], "warnings": []},
        "zh": {
            "items": [
                {
                    "award_type": "player_of_the_day",
                    "player_id": "p1",
                    "title": "努诺-门德斯进球又推进",
                    "body": "他还有11次打穿防线、8次推进和6次夺回球权，这场不是只在边路补一个进球。",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }
    zh_profile = {"unsupported_public_terms": ["不是只在", "补一个进球"]}

    validation = validate_copy(copy, {"zh": zh_profile})

    assert validation["status"] == "failed"
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


def test_editorial_v2_fake_copy_is_publishable_static_copy():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_copy import build_copy_payloads, generate_copy
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

    copy = generate_copy(payload, fake=True)
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
    assert pool["near_misses"]
    assert all(candidate["pool_reasons"] for candidate in pool["selectable_candidates"])
    assert {candidate["player_id"] for candidate in pool["selectable_candidates"]}
    assert all(candidate.get("award_contexts") for candidate in pool["selectable_candidates"])
    assert any(
        "defensive_pick" in candidate.get("award_contexts", {})
        for candidate in pool["selectable_candidates"]
    )
    selector_input = build_selector_input(pool, experiment)
    assert len(json.dumps(selector_input, ensure_ascii=False)) < 80_000
    selector_candidate = selector_input["candidate_pool"]["selectable_candidates"][0]
    assert "award_contexts" in selector_candidate
    assert "score_components" not in selector_candidate["award_contexts"]["player_of_the_day"]


def test_editorial_v2_selection_validation_requires_pool_membership_and_skip_reasons():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )
    from football_data.editorial_selection import fake_selection_decision
    from football_data.editorial_validation import validate_selection_decision

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings("data/latest.sqlite", "2026-06-21", experiment["scoring_config"])
    pool = build_candidate_pool(rankings, load_candidate_pool_config(experiment["candidate_pool"]))

    decision = fake_selection_decision(pool, experiment)
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

    from football_data.editorial_selection import normalize_selection_decision, repair_selection_decision

    aliased = json.loads(json.dumps(decision))
    aliased["selected"][-2] = _selected(_candidate(pool, "Pau CUBARSI"), "progression")
    aliased["selected"][-1] = _selected(_candidate(pool, "Brandon MECHELE"), "defensive")
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
    assert normalized_validation["status"] == "pass"
    assert any("normalized award_type progression to progression_pick" in warning for warning in normalized["warnings"])

    weak_reason = json.loads(json.dumps(decision))
    weak_reason["selected"][0]["editorial_reason"] = "en"
    weak_reason["selected"][0]["evidence_used"] = ["brce", "unsupported but long evidence phrase"]
    repaired = repair_selection_decision(weak_reason, pool)
    assert len(repaired["selected"][0]["editorial_reason"]) > 20
    assert repaired["selected"][0]["evidence_used"] != ["brce", "unsupported but long evidence phrase"]
    assert any("repaired weak editorial_reason" in warning for warning in repaired["warnings"])
    assert any("repaired weak evidence_used" in warning for warning in repaired["warnings"])


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


def _selected(candidate: dict, award_type: str) -> dict:
    return {
        "award_type": award_type,
        "player_id": candidate["player_id"],
        "player_name": candidate["player_name"],
        "team": candidate["team"],
        "editorial_reason": "Selected in a regression scenario.",
        "evidence_used": [],
        "selection_risk": "",
    }
