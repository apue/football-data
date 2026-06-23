import json
from pathlib import Path


def test_editorial_workflow_is_manual_only_for_local_editor_review():
    workflow = Path(".github/workflows/editorial.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "workflows: [\"Update Dataset\"]" not in workflow


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
    assert choices["editorial_generation"]["experiment_id"] == "ai_rerank_guardrails_v2"
    assert [choice["player_name"] for choice in choices["choices"]][:3] == [
        "Kylian MBAPPE",
        "Lionel MESSI",
        "Erling HAALAND",
    ]
    assert (audit_dir / "copy_payload.json").exists()
    assert (audit_dir / "selection_validation.json").exists()
    assert "Editor's Choices" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
