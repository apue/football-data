from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football_data.demo import build_demo_site
from football_data.editorial_artifacts import (
    _audit_rankings,
    build_compiled_report,
    write_v2_artifacts,
)
from football_data.editorial_candidates import build_candidate_pool
from football_data.editorial_copy import build_copy_payloads
from football_data.editorial_rankings import build_editorial_rankings
from football_data.editorial_registry import (
    load_candidate_pool_config,
    load_editorial_experiment,
)
from football_data.editorial_selection import (
    build_selector_input,
    normalize_selection_decision,
    repair_selection_decision,
)
from football_data.editorial_validation import validate_selection_decision


def prepare_editorial_packet(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    agent_runs_dir: str | Path = "agent-runs",
    config_dir: str | Path = "config/editorial",
    experiment_id: str | None = None,
    run_out_path: str | Path = "manifests/editorial-v2-run.json",
) -> dict[str, Any]:
    experiment = load_editorial_experiment(experiment_id, config_dir)
    pool_config = load_candidate_pool_config(experiment["candidate_pool"], config_dir)
    rankings = build_editorial_rankings(db_path, match_date, experiment["scoring_config"])
    candidate_pool = build_candidate_pool(rankings, pool_config)
    selector_input = build_selector_input(candidate_pool, experiment)
    run_payload = _run_payload(
        status="prepared",
        match_date=match_date,
        experiment=experiment,
        rankings=rankings,
        selection_validation=None,
        choices=[],
    )

    audit_dir = Path(agent_runs_dir) / match_date
    audit_dir.mkdir(parents=True, exist_ok=True)
    for stale_name in (
        "selection_decision",
        "selection_validation",
        "copy_payload",
        "copy",
    ):
        stale_path = audit_dir / f"{stale_name}.json"
        if stale_path.exists():
            stale_path.unlink()
    for name, payload in {
        "rankings": _audit_rankings(rankings),
        "candidate_pool": candidate_pool,
        "selector_input": selector_input,
        "run": run_payload,
    }.items():
        _write_json(audit_dir / f"{name}.json", payload)
    _write_json(run_out_path, run_payload)
    return run_payload


def compile_local_editorial(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    config_dir: str | Path = "config/editorial",
    run_out_path: str | Path = "manifests/editorial-v2-run.json",
    rebuild_homepage: bool = True,
) -> dict[str, Any]:
    audit_dir = Path(agent_runs_dir) / match_date
    rankings = _load_json(audit_dir / "rankings.json")
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    selector_input = _load_json(audit_dir / "selector_input.json")
    selection_decision = normalize_selection_decision(
        _load_json(audit_dir / "selection_decision.json")
    )
    copy = _load_json(audit_dir / "copy.json")
    previous_run = _load_json(audit_dir / "run.json")

    experiment = load_editorial_experiment(previous_run.get("experiment_id"), config_dir)
    selection_decision = repair_selection_decision(selection_decision, candidate_pool)
    selection_validation = validate_selection_decision(selection_decision, candidate_pool, experiment)
    if selection_validation["status"] != "pass":
        _write_json(audit_dir / "selection_validation.json", selection_validation)
        raise RuntimeError(f"Local editorial selection validation failed: {selection_validation['warnings']}")

    copy_payload = build_copy_payloads(selection_decision, candidate_pool)
    compiled = build_compiled_report(
        experiment=experiment,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy=copy,
    )
    run_payload = _run_payload(
        status="success",
        match_date=match_date,
        experiment=experiment,
        rankings=rankings,
        selection_validation=selection_validation,
        choices=[
            {
                "award_type": choice["award_type"],
                "player_name": choice["player_name"],
                "team": choice["team"],
            }
            for choice in compiled["choices"]
        ],
    )
    write_v2_artifacts(
        compiled=compiled,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selector_input=selector_input,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy_payload=copy_payload,
        copy=copy,
        run_payload=run_payload,
        site_dir=site_dir,
        reports_dir=reports_dir,
        agent_runs_dir=agent_runs_dir,
        run_out_path=run_out_path,
    )
    if rebuild_homepage:
        build_demo_site(db_path, site_dir, manifests_dir)
    return run_payload


def _run_payload(
    *,
    status: str,
    match_date: str,
    experiment: dict[str, Any],
    rankings: dict[str, Any],
    selection_validation: dict[str, Any] | None,
    choices: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "match_date": match_date,
        "workflow_variant": experiment["workflow_variant"],
        "experiment_id": experiment["id"],
        "editor_runtime": "local_codex",
        "scoring_version": rankings["scoring_version"],
        "selection_validation": selection_validation,
        "choices": choices,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing local editorial file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Local editorial file must contain a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
