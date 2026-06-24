import json
from pathlib import Path

def test_editorial_v2_registry_resolves_default_experiment():
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_profile,
        load_editorial_experiment,
        load_selector_profile,
    )
    from football_data.editorial_display_names import player_display_entry, player_display_name

    experiment = load_editorial_experiment()

    assert experiment["id"] == "ai_rerank_slate_copy_v3"
    assert experiment["workflow_variant"] == "ai_rerank_selection_v1"
    assert experiment["selection"]["mode"] == "ai_rerank_only"
    assert experiment["candidate_pool"] == "guarded_packet_v2"
    assert experiment["selector_profile"] == "slate_balanced_editor_v3"
    assert experiment["copy_profiles"]["zh"] == "zh_matchnote_light_emotion_v1"
    assert experiment["selection"]["strategy"] == "overall_slate_v1"
    assert experiment["selection"]["target_public_cards"] == 5
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
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    en_profile = load_copy_profile(experiment["copy_profiles"]["en"])

    assert pool["potd_top_n"] == 8
    assert selector["allowed_selection_source"] == "candidate_pool_only"
    assert any("Fact accuracy" in item for item in selector["instructions"])
    assert any("same match" in item for item in selector["instructions"])
    assert any("not a quota" in item for item in selector["instructions"])
    assert zh_profile["language"] == "zh"
    assert zh_profile["instructions"]
    assert isinstance(zh_profile.get("banned_public_terms"), list)
    assert zh_profile["banned_public_terms"]
    assert zh_profile["title_policy"]["mode"] == "core_fact_label"
    assert isinstance(zh_profile["title_policy"].get("banned_title_terms"), list)
    assert en_profile["language"] == "en"
    assert en_profile["instructions"]

    baseline = load_editorial_experiment("ai_rerank_baseline_v1")
    assert baseline["status"] == "archived"


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
    assert len(decision["selected"]) == 5
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
    assert "哈兰德" in zh_item["body"]


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

    missing_public_card = json.loads(json.dumps(decision))
    missing_public_card["selected"] = missing_public_card["selected"][:-1]
    missing_validation = validate_selection_decision(missing_public_card, pool, experiment)
    assert missing_validation["status"] == "failed"
    assert any("target_public_cards 5" in warning for warning in missing_validation["warnings"])

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


def test_run_editorial_v2_fake_backend_writes_public_and_audit_artifacts(tmp_path):
    from football_data.editorial_v2_runner import run_editorial_v2

    result = run_editorial_v2(
        match_date="2026-06-21",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
        fake=True,
        research=False,
        rebuild_homepage=True,
    )

    assert result["status"] == "success"
    assert result["workflow_variant"] == "ai_rerank_selection_v1"
    assert result["selection_validation"]["status"] == "pass"

    latest = json.loads((tmp_path / "site" / "editorial" / "latest.json").read_text(encoding="utf-8"))
    choices = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-21" / "choices.json").read_text(
            encoding="utf-8"
        )
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-21"

    assert latest["match_date"] == "2026-06-21"
    assert choices["choices"]
    assert choices["editorial_generation"]["workflow_variant"] == "ai_rerank_selection_v1"
    assert choices["editorial_generation"]["uses_official_assists"] is True
    assert choices["editorial_generation"]["uses_goal_involvements"] is True
    assert len(choices["choices"]) == 5
    assert all(choice["award_type"] == "player_of_the_day" for choice in choices["choices"])
    assert (audit_dir / "rankings.json").exists()
    assert (audit_dir / "candidate_pool.json").exists()
    assert (audit_dir / "selector_input.json").exists()
    assert (audit_dir / "selection_decision.json").exists()
    assert (audit_dir / "selection_validation.json").exists()
    assert (audit_dir / "copy_payload.json").exists()
    assert (audit_dir / "copy.json").exists()
    assert "Editor's Choices" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "official assists" in (tmp_path / "site" / "editorial" / "index.html").read_text(
        encoding="utf-8"
    )


def test_run_editorial_v2_cli_fake_backend(tmp_path):
    import subprocess
    import sys

    run_path = tmp_path / "editorial-v2-run.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_v2.py",
            "--date",
            "2026-06-21",
            "--site-dir",
            str(tmp_path / "site"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--out",
            str(run_path),
            "--fake",
            "--no-research",
            "--json",
        ],
        check=True,
    )

    result = json.loads(run_path.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert (tmp_path / "site" / "editorial" / "latest.json").exists()

    subprocess.run(
        [
            sys.executable,
            "scripts/recompile_editorial_v2.py",
            "--date",
            "2026-06-21",
            "--site-dir",
            str(tmp_path / "site"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--out",
            str(tmp_path / "editorial-v2-run.json"),
            "--json",
        ],
        check=True,
    )
    recompiled = json.loads(run_path.read_text(encoding="utf-8"))
    assert recompiled["status"] == "success"
    assert "recompiled_at" in recompiled


def test_editorial_ai_config_process_env_overrides_env_file(tmp_path, monkeypatch):
    from football_data.llm_client import load_editorial_ai_config

    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=file-key",
                "EDITORIAL_AGENT_TIMEOUT_SECONDS=90",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")
    monkeypatch.setenv("EDITORIAL_AGENT_TIMEOUT_SECONDS", "181")

    config = load_editorial_ai_config(env_path)

    assert config.api_key == "process-key"
    assert config.timeout_seconds == 181


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
