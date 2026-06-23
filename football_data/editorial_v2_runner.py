from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football_data.demo import build_demo_site
from football_data.llm_client import (
    AgentsSdkTextClient,
    FakeEditorialAgentClient,
    load_editorial_ai_config,
)
from football_data.editorial_artifacts import build_compiled_report, write_v2_artifacts
from football_data.editorial_candidates import build_candidate_pool
from football_data.editorial_copy import build_copy_payloads, generate_copy
from football_data.editorial_rankings import build_editorial_rankings
from football_data.editorial_registry import (
    load_candidate_pool_config,
    load_copy_profile,
    load_editorial_experiment,
    load_selector_profile,
)
from football_data.editorial_selection import (
    build_selector_input,
    fake_selection_decision,
    repair_selection_decision,
    run_ai_rerank_selector,
)
from football_data.editorial_validation import validate_selection_decision


def run_editorial_v2(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    config_dir: str | Path = "config/editorial",
    experiment_id: str | None = None,
    env_path: str | Path = ".env.local",
    run_out_path: str | Path = "manifests/editorial-v2-run.json",
    fake: bool = False,
    research: bool = True,
    rebuild_homepage: bool = True,
) -> dict[str, Any]:
    del research
    experiment = load_editorial_experiment(experiment_id, config_dir)
    pool_config = load_candidate_pool_config(experiment["candidate_pool"], config_dir)
    selector_profile = load_selector_profile(experiment["selector_profile"], config_dir)
    copy_profiles = {
        "zh": load_copy_profile(experiment["copy_profiles"]["zh"], config_dir),
        "en": load_copy_profile(experiment["copy_profiles"]["en"], config_dir),
    }
    config = load_editorial_ai_config(env_path, require_credentials=not fake)
    text_client = FakeEditorialAgentClient() if fake else AgentsSdkTextClient(config)

    rankings = build_editorial_rankings(db_path, match_date, experiment["scoring_config"])
    candidate_pool = build_candidate_pool(rankings, pool_config)
    selector_input = build_selector_input(candidate_pool, experiment)
    if fake:
        selection_decision = fake_selection_decision(candidate_pool, experiment)
    else:
        model_key = str(selector_profile.get("model_key") or "revision_editor")
        selection_decision = run_ai_rerank_selector(
            selector_input,
            text_client,
            selector_profile,
            model=config.models[model_key],
        )
    selection_decision = repair_selection_decision(selection_decision, candidate_pool)
    selection_validation = validate_selection_decision(selection_decision, candidate_pool, experiment)
    if selection_validation["status"] != "pass":
        raise RuntimeError(f"Editorial v2 selection validation failed: {selection_validation['warnings']}")

    copy_payload = build_copy_payloads(selection_decision, candidate_pool)
    copy = generate_copy(
        copy_payload,
        fake=fake,
        text_client=text_client,
        profiles=copy_profiles,
        models=config.models,
    )
    compiled = build_compiled_report(
        experiment=experiment,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy=copy,
    )
    run_payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "success",
        "match_date": match_date,
        "workflow_variant": experiment["workflow_variant"],
        "experiment_id": experiment["id"],
        "scoring_version": rankings["scoring_version"],
        "selection_validation": selection_validation,
        "choices": [
            {
                "award_type": choice["award_type"],
                "player_name": choice["player_name"],
                "team": choice["team"],
            }
            for choice in compiled["choices"]
        ],
    }
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
