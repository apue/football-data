from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_data.editorial_queue import build_editorial_queue, write_editorial_queue
from football_data.editorial_registry import load_editorial_experiment
from football_data.editorial_v2_runner import run_editorial_v2
from football_data.llm_client import load_editorial_ai_config


def run_editorial_queue(
    *,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    config_dir: str | Path = "config/editorial",
    experiment_id: str | None = None,
    env_path: str | Path = ".env.local",
    run_out_path: str | Path = "manifests/editorial-run.json",
    queue_out_path: str | Path = "manifests/editorial-queue.json",
    research: bool = True,
    fake: bool = False,
    max_dates: int | None = None,
    match_dates: list[str] | None = None,
) -> dict[str, Any]:
    experiment = load_editorial_experiment(experiment_id, config_dir)
    queue = build_editorial_queue(
        db_path=db_path,
        site_dir=site_dir,
        manifests_dir=manifests_dir,
        scoring_config_path=experiment["scoring_config"],
    )
    write_editorial_queue(queue, queue_out_path)
    pending_dates = list(match_dates or queue.get("pending_dates", []))
    if max_dates is not None:
        pending_dates = pending_dates[:max_dates]

    if not pending_dates:
        payload = _run_payload(status="up_to_date", queue=queue, pending_dates=[])
        _write_json(run_out_path, payload)
        return payload

    if not fake:
        missing_reason = _missing_credentials_reason(env_path)
        if missing_reason:
            payload = _run_payload(
                status="needs_credentials",
                queue=queue,
                pending_dates=pending_dates,
                failures=[{"stage": "credentials", "message": missing_reason}],
            )
            _write_json(run_out_path, payload)
            return payload

    published_dates: list[str] = []
    failures: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for match_date in pending_dates:
        try:
            v2_run_path = Path(run_out_path).with_name("editorial-v2-run.json")
            agent_result = run_editorial_v2(
                match_date=match_date,
                db_path=db_path,
                site_dir=site_dir,
                reports_dir=reports_dir,
                manifests_dir=manifests_dir,
                agent_runs_dir=agent_runs_dir,
                config_dir=config_dir,
                experiment_id=experiment["id"],
                env_path=env_path,
                run_out_path=v2_run_path,
                fake=fake,
                research=research,
                rebuild_homepage=True,
            )
            if agent_result.get("status") != "success":
                raise RuntimeError(f"Editorial v2 did not publish: {agent_result.get('status')}")
            published_dates.append(match_date)
            runs.append(
                {
                    "match_date": match_date,
                    "agent_status": agent_result.get("status"),
                    "experiment_id": agent_result.get("experiment_id"),
                    "workflow_variant": agent_result.get("workflow_variant"),
                    "selection_validation": agent_result.get("selection_validation", {}).get("status"),
                    "choices": agent_result.get("choices", []),
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "match_date": match_date,
                    "stage": "editorial",
                    "message": str(exc)[:1000],
                }
            )

    payload = _run_payload(
        status="failed" if failures else "success",
        queue=queue,
        pending_dates=pending_dates,
        published_dates=published_dates,
        failures=failures,
        runs=runs,
    )
    _write_json(run_out_path, payload)
    return payload


def _missing_credentials_reason(env_path: str | Path) -> str | None:
    try:
        load_editorial_ai_config(env_path, require_credentials=True)
    except ValueError as exc:
        return str(exc)
    return None


def _run_payload(
    *,
    status: str,
    queue: dict[str, Any],
    pending_dates: list[str],
    published_dates: list[str] | None = None,
    failures: list[dict[str, Any]] | None = None,
    runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": status,
        "queue_status": queue.get("status"),
        "queue_reason": queue.get("reason"),
        "latest_data_date": queue.get("latest_data_date"),
        "latest_editorial_date": queue.get("latest_editorial_date"),
        "pending_dates": pending_dates,
        "published_dates": published_dates or [],
        "failures": failures or [],
        "runs": runs or [],
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
