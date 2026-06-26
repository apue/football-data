import json
from pathlib import Path


def test_cloud_editorial_workflow_is_retired():
    assert not Path(".github/workflows/editorial.yml").exists()


def test_prepare_editorial_packet_writes_handoff_audit_without_public_artifacts(tmp_path):
    from football_data.editorial_local import prepare_editorial_packet

    result = prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"

    assert result["status"] == "prepared"
    assert result["editor_runtime"] == "local_codex"
    assert (audit_dir / "rankings.json").exists()
    assert (audit_dir / "candidate_pool.json").exists()
    assert (audit_dir / "selector_input.json").exists()
    assert (audit_dir / "run.json").exists()
    assert not (audit_dir / "selection_decision.json").exists()
    assert not (tmp_path / "site").exists()


def test_inspect_editorial_day_writes_fact_pack_with_reader_traps(tmp_path):
    from football_data.editorial_fact_pack import write_editorial_fact_pack
    from football_data.editorial_local import prepare_editorial_packet

    prepare_editorial_packet(
        match_date="2026-06-19",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )

    fact_pack = write_editorial_fact_pack(
        match_date="2026-06-19",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-19"

    assert (audit_dir / "editorial_fact_pack.json").exists()
    assert (audit_dir / "editorial_fact_pack.md").exists()
    assert any(goal.get("own_goal_by") == "Australia" for goal in fact_pack["goal_timeline"])
    trap_messages = "\n".join(trap["message"] for trap in fact_pack["candidate_traps"])
    assert "Alex FREEMAN scored" in trap_messages
    assert "Arda GULER ranks #5 without G/A" in trap_messages
    assert [keeper["player_name"] for keeper in fact_pack["goalkeeper_pressure_candidates"]] == [
        "Orlando GILL"
    ]


def test_compile_local_editorial_uses_local_decision_and_copy(tmp_path):
    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_selection import fake_selection_decision
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_registry import load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    experiment = load_editorial_experiment()
    decision = fake_selection_decision(candidate_pool, experiment)
    copy = generate_copy(build_copy_payloads(decision, candidate_pool), fake=True)
    (audit_dir / "selection_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "copy.json").write_text(
        json.dumps(copy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_passing_review(audit_dir, decision, candidate_pool, copy, experiment)

    result = compile_local_editorial(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    choices = _load_json(tmp_path / "site" / "editorial" / "2026-06-22" / "choices.json")

    assert result["status"] == "success"
    assert result["editor_runtime"] == "local_codex"
    assert result["selection_validation"]["status"] == "pass"
    assert choices["editorial_generation"]["experiment_id"] == "ai_rerank_reader_loop_v5"
    assert choices["editorial_generation"]["editorial_review_status"] == "pass"
    assert [choice["player_name"] for choice in choices["choices"]][:3] == [
        "Kylian MBAPPE",
        "Lionel MESSI",
        "Erling HAALAND",
    ]
    assert (audit_dir / "copy_payload.json").exists()
    assert (audit_dir / "selection_validation.json").exists()
    assert (audit_dir / "copy_validation.json").exists()
    assert (audit_dir / "editorial_review_payload.json").exists()
    assert (audit_dir / "editorial_review_validation.json").exists()
    assert "Editor's Choices" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_compile_local_editorial_requires_passing_reader_review(tmp_path):
    import pytest

    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_selection import fake_selection_decision
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_registry import load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    decision = fake_selection_decision(candidate_pool, load_editorial_experiment())
    copy = generate_copy(build_copy_payloads(decision, candidate_pool), fake=True)
    (audit_dir / "selection_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "copy.json").write_text(
        json.dumps(copy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="editorial review failed"):
        compile_local_editorial(
            match_date="2026-06-22",
            db_path="data/latest.sqlite",
            site_dir=tmp_path / "site",
            reports_dir=tmp_path / "reports",
            manifests_dir="manifests",
            agent_runs_dir=tmp_path / "agent-runs",
            run_out_path=tmp_path / "editorial-v2-run.json",
        )

    assert (audit_dir / "editorial_review_payload.json").exists()
    validation = _load_json(audit_dir / "editorial_review_validation.json")
    assert validation["status"] == "failed"
    assert any("Missing local editorial file" in warning for warning in validation["warnings"])


def test_compile_local_editorial_rejects_ai_sounding_zh_copy(tmp_path):
    import pytest

    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_selection import fake_selection_decision
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_registry import load_copy_profile, load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    experiment = load_editorial_experiment()
    decision = fake_selection_decision(candidate_pool, experiment)
    copy = generate_copy(build_copy_payloads(decision, candidate_pool), fake=True)
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    term = zh_profile["banned_public_terms"][0]
    copy["zh"]["items"][0]["body"] = f"这句包含{term}，应该被拦住。"
    (audit_dir / "selection_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "copy.json").write_text(
        json.dumps(copy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="copy validation failed"):
        compile_local_editorial(
            match_date="2026-06-22",
            db_path="data/latest.sqlite",
            site_dir=tmp_path / "site",
            reports_dir=tmp_path / "reports",
            manifests_dir="manifests",
            agent_runs_dir=tmp_path / "agent-runs",
            run_out_path=tmp_path / "editorial-v2-run.json",
        )

    validation = _load_json(audit_dir / "copy_validation.json")
    assert validation["status"] == "failed"
    assert any(f"banned zh public term {term!r}" in warning for warning in validation["warnings"])


def test_compile_local_editorial_rejects_zh_title_missing_core_fact(tmp_path):
    import pytest

    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_selection import fake_selection_decision
    from football_data.editorial_copy import build_copy_payloads, generate_copy
    from football_data.editorial_registry import load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    decision = fake_selection_decision(candidate_pool, load_editorial_experiment())
    copy = generate_copy(build_copy_payloads(decision, candidate_pool), fake=True)
    messi = next(item for item in copy["zh"]["items"] if item["player_id"].endswith("|Argentina|10"))
    messi["title"] = "梅西补时再进"
    (audit_dir / "selection_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "copy.json").write_text(
        json.dumps(copy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="copy validation failed"):
        compile_local_editorial(
            match_date="2026-06-22",
            db_path="data/latest.sqlite",
            site_dir=tmp_path / "site",
            reports_dir=tmp_path / "reports",
            manifests_dir="manifests",
            agent_runs_dir=tmp_path / "agent-runs",
            run_out_path=tmp_path / "editorial-v2-run.json",
        )

    validation = _load_json(audit_dir / "copy_validation.json")
    assert validation["status"] == "failed"
    assert any("missing zh title core fact goals>=2" in warning for warning in validation["warnings"])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_passing_review(
    audit_dir: Path,
    decision: dict,
    candidate_pool: dict,
    copy: dict,
    experiment: dict,
) -> None:
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_copy_validation import validate_copy
    from football_data.editorial_registry import load_copy_profile, load_review_profile
    from football_data.editorial_review import build_editorial_review_payload, passing_editorial_review
    from football_data.editorial_validation import validate_selection_decision

    copy_profiles = {
        language: load_copy_profile(str(profile_id))
        for language, profile_id in experiment["copy_profiles"].items()
    }
    review_profile = load_review_profile(experiment["review_profile"])
    copy_payload = build_copy_payloads(decision, candidate_pool)
    review_payload = build_editorial_review_payload(
        selection_decision=decision,
        candidate_pool=candidate_pool,
        copy=copy,
        selection_validation=validate_selection_decision(decision, candidate_pool, experiment),
        copy_validation=validate_copy(copy, copy_profiles, copy_payload=copy_payload),
        review_profile=review_profile,
        selection_config=experiment.get("selection"),
    )
    review = passing_editorial_review(review_profile, review_payload)
    (audit_dir / "editorial_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
