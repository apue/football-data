import json
from pathlib import Path

from editorial_test_helpers import (
    build_test_copy,
    build_test_selection_decision,
    write_passing_test_editorial_loop,
)


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
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_loop import promote_editorial_loop
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
    decision = build_test_selection_decision(candidate_pool, experiment)
    copy = build_test_copy(build_copy_payloads(decision, candidate_pool))
    write_passing_test_editorial_loop(audit_dir, decision, copy, candidate_pool, experiment)
    promote_editorial_loop(match_date="2026-06-22", agent_runs_dir=tmp_path / "agent-runs")

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
    assert choices["editorial_generation"]["experiment_id"] == "bounded_editorial_loop_v1"
    assert choices["editorial_generation"]["editorial_loop_status"] == "pass"
    assert choices["editorial_generation"]["selection_rounds"] == 1
    assert choices["editorial_generation"]["copy_rounds"] == 1
    assert [choice["player_name"] for choice in choices["choices"]][:3] == [
        "Kylian MBAPPE",
        "Lionel MESSI",
        "Erling HAALAND",
    ]
    assert (audit_dir / "copy_payload.json").exists()
    assert (audit_dir / "selection_validation.json").exists()
    assert (audit_dir / "copy_validation.json").exists()
    assert (audit_dir / "editorial_loop_summary.json").exists()
    assert (audit_dir / "editorial_loop_validation.json").exists()
    assert "Editor's Choices" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_compile_local_editorial_rejects_ai_sounding_zh_copy(tmp_path):
    import pytest

    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_loop import promote_editorial_loop
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
    decision = build_test_selection_decision(candidate_pool, experiment)
    copy = build_test_copy(build_copy_payloads(decision, candidate_pool))
    zh_profile = load_copy_profile(experiment["copy_profiles"]["zh"])
    term = zh_profile["banned_public_terms"][0]
    copy["zh"]["items"][0]["body"] = f"这句包含{term}，应该被拦住。"
    write_passing_test_editorial_loop(audit_dir, decision, copy, candidate_pool, experiment)

    with pytest.raises(RuntimeError, match="copy loop did not pass"):
        promote_editorial_loop(match_date="2026-06-22", agent_runs_dir=tmp_path / "agent-runs")

    validation = _load_json(audit_dir / "copy_rounds" / "round_1" / "copy_validation.json")
    assert validation["status"] == "failed"
    assert any(f"banned zh public term {term!r}" in warning for warning in validation["warnings"])


def test_compile_local_editorial_rejects_zh_title_missing_core_fact(tmp_path):
    import pytest

    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_loop import promote_editorial_loop
    from football_data.editorial_registry import load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    decision = build_test_selection_decision(candidate_pool, load_editorial_experiment())
    copy = build_test_copy(build_copy_payloads(decision, candidate_pool))
    messi = next(item for item in copy["zh"]["items"] if item["player_id"].endswith("|Argentina|10"))
    messi["title"] = "梅西补时再进"
    write_passing_test_editorial_loop(
        audit_dir,
        decision,
        copy,
        candidate_pool,
        load_editorial_experiment(),
    )

    with pytest.raises(RuntimeError, match="copy loop did not pass"):
        promote_editorial_loop(match_date="2026-06-22", agent_runs_dir=tmp_path / "agent-runs")

    validation = _load_json(audit_dir / "copy_rounds" / "round_1" / "copy_validation.json")
    assert validation["status"] == "failed"
    assert any("missing zh title core fact goals>=2" in warning for warning in validation["warnings"])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
