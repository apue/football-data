import json
from pathlib import Path

def test_editorial_v2_registry_resolves_default_experiment():
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_copy_profile,
        load_editorial_experiment,
        load_selector_profile,
    )

    experiment = load_editorial_experiment()

    assert experiment["id"] == "ai_rerank_baseline_v1"
    assert experiment["workflow_variant"] == "ai_rerank_selection_v1"
    assert experiment["selection"]["mode"] == "ai_rerank_only"
    assert experiment["candidate_pool"] == "rich_packet_v1"
    assert experiment["selector_profile"] == "strict_editor_v1"

    pool = load_candidate_pool_config(experiment["candidate_pool"])
    selector = load_selector_profile(experiment["selector_profile"])
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    en_profile = load_copy_profile(experiment["copy_profiles"]["en"])

    assert pool["potd_top_n"] == 8
    assert selector["allowed_selection_source"] == "candidate_pool_only"
    assert any("Fact accuracy" in item for item in selector["instructions"])
    assert zh_profile["language"] == "zh"
    assert zh_profile["instructions"]
    assert en_profile["language"] == "en"
    assert en_profile["instructions"]


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
    assert decision["skipped_higher_ranked"]

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

    missing_required_slot = json.loads(json.dumps(decision))
    missing_required_slot["selected"] = [
        item
        for item in missing_required_slot["selected"]
        if item["award_type"] != "defensive_pick"
    ]
    missing_validation = validate_selection_decision(missing_required_slot, pool, experiment)
    assert missing_validation["status"] == "failed"
    assert any("missing required slot defensive_pick" in warning for warning in missing_validation["warnings"])

    from football_data.editorial_selection import normalize_selection_decision, repair_selection_decision

    aliased = json.loads(json.dumps(decision))
    for item in aliased["selected"]:
        if item["award_type"] == "progression_pick":
            item["award_type"] = "progression"
        if item["award_type"] == "defensive_pick":
            item["award_type"] = "defensive"
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
    keeper = next(choice for choice in choices["choices"] if choice["award_type"] == "goalkeeper_watch")
    assert "faced heavy on-target pressure" in keeper["evidence_chips"]["en"]
    assert "ball-winning profile" not in keeper["evidence_chips"]["en"]
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
