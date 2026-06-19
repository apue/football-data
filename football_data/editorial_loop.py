from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_data.demo import build_demo_site
from football_data.editorial import build_editorial_report, write_editorial_artifacts
from football_data.editorial_agent import _deterministic_fact_check


def run_editorial_loop(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    scoring_config_path: str | Path = "config/scoring/v0.3.json",
    max_iterations: int = 3,
    rebuild_homepage: bool = True,
    use_existing_markdown: bool = False,
) -> dict[str, Any]:
    loop_dir = Path(agent_runs_dir) / match_date
    loop_dir.mkdir(parents=True, exist_ok=True)

    report = build_editorial_report(
        db_path,
        match_date=match_date,
        scoring_config_path=scoring_config_path,
    )
    write_editorial_artifacts(
        report,
        site_dir=site_dir,
        reports_dir=reports_dir,
        preserve_existing_markdown=use_existing_markdown,
    )
    markdown_path = Path(reports_dir) / "editorial" / f"{match_date}.md"
    evidence_path = Path(site_dir) / "editorial" / match_date / "evidence.json"
    markdown_text = markdown_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    iteration_dir = loop_dir / "iteration-001"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "iteration": 1,
        "match_date": match_date,
        "choices": _choice_identities(report["choices"]),
    }
    selection_review = report.get("selection_review") or {"status": "unknown", "alerts": []}
    copy_review = _review_copy(markdown_text)
    validation = _validate_editorial(evidence, markdown_text, selection_review, copy_review)
    decision = _decide(validation, iteration=1, max_iterations=max_iterations)

    _write_json(iteration_dir / "state.json", state)
    _write_json(iteration_dir / "selection_review.json", selection_review)
    _write_json(iteration_dir / "copy_review.zh.json", copy_review)
    _write_json(iteration_dir / "validation.json", validation)
    _write_json(iteration_dir / "decision.json", decision)

    if decision["decision"] == "publish" and rebuild_homepage:
        build_demo_site(db_path, site_dir, manifests_dir)

    final = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "published" if decision["decision"] == "publish" else "needs_review",
        "decision": decision["decision"],
        "match_date": match_date,
        "orchestrator": {
            "pattern": "review_repair_validate",
            "iterations": 1,
            "max_iterations": max_iterations,
        },
        "selection_review": selection_review,
        "copy_review": copy_review,
        "validation": validation,
        "choices": _choice_identities(report["choices"]),
        "artifacts": {
            "markdown": str(markdown_path),
            "evidence": str(evidence_path),
            "site": str(Path(site_dir) / "editorial" / match_date / "index.html"),
        },
    }
    _write_json(loop_dir / "final.json", final)
    return final


def _review_copy(markdown_text: str) -> dict[str, Any]:
    return {
        "status": "pass",
        "reviewer": "chinese_copy_reviewer",
        "method": "rubric_placeholder",
        "findings": [],
        "notes": [
            "Copy review is an explicit loop phase. The default local reviewer only records the phase; model-backed rubric review can replace it without changing the orchestrator contract."
        ],
    }


def _validate_editorial(
    evidence: dict[str, Any],
    markdown_text: str,
    selection_review: dict[str, Any],
    copy_review: dict[str, Any],
) -> dict[str, Any]:
    deterministic_warnings = _deterministic_fact_check(evidence, markdown_text)
    high_selection_alerts = [
        alert
        for alert in selection_review.get("alerts", [])
        if alert.get("level") == "high"
    ]
    checks = {
        "selection": "pass" if not high_selection_alerts else "fail",
        "copy": "pass" if copy_review.get("status") == "pass" else "fail",
        "facts": "pass" if not deterministic_warnings else "fail",
    }
    return {
        "status": "pass" if all(value == "pass" for value in checks.values()) else "fail",
        "checks": checks,
        "warnings": deterministic_warnings,
        "high_selection_alerts": high_selection_alerts,
    }


def _decide(validation: dict[str, Any], *, iteration: int, max_iterations: int) -> dict[str, Any]:
    if validation["status"] == "pass":
        return {
            "decision": "publish",
            "reason": "all_validation_checks_passed",
        }
    if iteration >= max_iterations:
        return {
            "decision": "needs_human_review",
            "reason": "max_iterations_reached",
        }
    return {
        "decision": "repair",
        "reason": "validation_failed",
    }


def _choice_identities(choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "award_type": choice["award_type"],
            "player_name": choice["player_name"],
            "team": choice["team"],
        }
        for choice in choices
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
