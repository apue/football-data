from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_data.editorial_agent import (
    FakeEditorialAgentClient,
    load_editorial_agent_config,
    run_editorial_agent,
)
from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG
from football_data.editorial_queue import build_editorial_queue, write_editorial_queue


def run_editorial_queue(
    *,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
    style_dir: str | Path = ".agents/editorial-skills",
    env_path: str | Path = ".env.local",
    run_out_path: str | Path = "manifests/editorial-run.json",
    queue_out_path: str | Path = "manifests/editorial-queue.json",
    research: bool = True,
    fake: bool = False,
    max_dates: int | None = None,
    match_dates: list[str] | None = None,
    review_feedback_path: str | Path | None = None,
    max_review_loops: int = 1,
) -> dict[str, Any]:
    queue = build_editorial_queue(
        db_path=db_path,
        site_dir=site_dir,
        manifests_dir=manifests_dir,
        scoring_config_path=scoring_config_path,
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
            client = FakeEditorialAgentClient() if fake else None
            agent_result = run_editorial_agent(
                match_date=match_date,
                db_path=db_path,
                site_dir=site_dir,
                reports_dir=reports_dir,
                manifests_dir=manifests_dir,
                agent_runs_dir=agent_runs_dir,
                scoring_config_path=scoring_config_path,
                style_dir=style_dir,
                env_path=env_path,
                client=client,
                research=research,
                rebuild_homepage=True,
                review_feedback_path=review_feedback_path,
                max_review_loops=max_review_loops,
            )
            if agent_result.get("status") != "success":
                raise RuntimeError(f"Editorial agent did not publish: {agent_result.get('status')}")
            published_dates.append(match_date)
            runs.append(
                {
                    "match_date": match_date,
                    "agent_status": agent_result.get("status"),
                    "fact_check": agent_result.get("fact_check", {}).get("status"),
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
        load_editorial_agent_config(env_path, require_credentials=True)
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
