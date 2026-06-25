from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football_data.editorial import AWARD_LABELS, write_compiled_editorial_artifacts
from football_data.editorial_copy import content_html


def build_compiled_report(
    *,
    experiment: dict[str, Any],
    rankings: dict[str, Any],
    candidate_pool: dict[str, Any],
    selection_decision: dict[str, Any],
    selection_validation: dict[str, Any],
    copy: dict[str, Any],
    editorial_review_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = {
        str(candidate["player_id"]): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
    }
    copy_by_language = {
        language: {
            str(item["player_id"]): item
            for item in payload.get("items", [])
            if isinstance(item, dict)
        }
        for language, payload in copy.items()
    }
    uses_goal_involvements = _uses_goal_involvements(rankings)
    event_sources = _event_sources(rankings, uses_goal_involvements=uses_goal_involvements)
    choices = []
    for selected in selection_decision.get("selected", []):
        candidate = candidates[str(selected["player_id"])]
        award_type = str(selected["award_type"])
        award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
        en = copy_by_language.get("en", {}).get(candidate["player_id"], {})
        zh = copy_by_language.get("zh", {}).get(candidate["player_id"], {})
        choices.append(
            {
                "award_type": award_type,
                "award_types": [award_type],
                "award_label": AWARD_LABELS.get(award_type, {"en": award_type, "zh": award_type}),
                "player_id": candidate["player_id"],
                "player_name": candidate["player_name"],
                "team": candidate["team"],
                "opponent": candidate["opponent"],
                "match_key": candidate["match_key"],
                "match_no": candidate["match_no"],
                "player_no": candidate["player_no"],
                "position": candidate.get("position"),
                "score": candidate.get("headline_score"),
                "metrics": award_context.get("metrics", candidate.get("metrics", {})),
                "evidence_chips": award_context.get(
                    "evidence_chips",
                    candidate.get("evidence_chips", {"en": [], "zh": []}),
                ),
                "selection_reason": selected.get("editorial_reason"),
                "content": {
                    "en": {
                        "title": en.get("title") or f"{candidate['player_name']} made the edit",
                        "html": content_html(en.get("body") or selected.get("editorial_reason") or ""),
                    },
                    "zh": {
                        "title": zh.get("title") or f"{candidate['player_name']} 入选",
                        "html": content_html(zh.get("body") or selected.get("editorial_reason") or ""),
                    },
                },
            }
        )
    return {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "compiled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": rankings["match_date"],
        "scoring_version": rankings["scoring_version"],
        "editorial_generation": {
            "workflow_variant": experiment["workflow_variant"],
            "experiment_id": experiment["id"],
            "selection_mode": experiment["selection"]["mode"],
            "review_profile": experiment.get("review_profile"),
            "revision_policy": experiment.get("revision_policy"),
            "editorial_review_status": (editorial_review_validation or {}).get("status"),
            "uses_official_assists": uses_goal_involvements,
            "uses_goal_involvements": uses_goal_involvements,
            "event_source": "fifa_timeline_api" if uses_goal_involvements else None,
            "event_sources": event_sources,
        },
        "matches": rankings["matches"],
        "match_flows": rankings.get("match_flows", {}),
        "choices": choices,
        "selection_validation": selection_validation,
        "audit": [],
    }


def write_v2_artifacts(
    *,
    compiled: dict[str, Any],
    rankings: dict[str, Any],
    candidate_pool: dict[str, Any],
    selector_input: dict[str, Any],
    selection_decision: dict[str, Any],
    selection_validation: dict[str, Any],
    copy_payload: dict[str, Any],
    copy: dict[str, Any],
    run_payload: dict[str, Any],
    site_dir: str | Path,
    reports_dir: str | Path,
    agent_runs_dir: str | Path,
    run_out_path: str | Path,
    copy_validation: dict[str, Any] | None = None,
    editorial_review_payload: dict[str, Any] | None = None,
    editorial_review: dict[str, Any] | None = None,
    editorial_review_validation: dict[str, Any] | None = None,
) -> None:
    write_compiled_editorial_artifacts(compiled, site_dir)
    reports_path = Path(reports_dir) / "editorial"
    reports_path.mkdir(parents=True, exist_ok=True)
    _remove_retired_sidecars(site_dir, reports_path, compiled["match_date"])
    (reports_path / f"{compiled['match_date']}.md").write_text(
        _markdown_report(compiled),
        encoding="utf-8",
    )
    audit_dir = Path(agent_runs_dir) / compiled["match_date"]
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_payloads = {
        "rankings": _audit_rankings(rankings),
        "candidate_pool": candidate_pool,
        "selector_input": selector_input,
        "selection_decision": selection_decision,
        "selection_validation": selection_validation,
        "copy_payload": copy_payload,
        "copy": copy,
        "run": run_payload,
    }
    if copy_validation is not None:
        audit_payloads["copy_validation"] = copy_validation
    if editorial_review_payload is not None:
        audit_payloads["editorial_review_payload"] = editorial_review_payload
    if editorial_review is not None:
        audit_payloads["editorial_review"] = editorial_review
    if editorial_review_validation is not None:
        audit_payloads["editorial_review_validation"] = editorial_review_validation
    for name, payload in audit_payloads.items():
        (audit_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    out = Path(run_out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_report(compiled: dict[str, Any]) -> str:
    lines = [
        f"# Editor's Choices - {compiled['match_date']}",
        "",
        f"Workflow: `{compiled['editorial_generation']['workflow_variant']}`",
        f"Scoring version: `{compiled['scoring_version']}`",
        "",
        "## Choices",
        "",
    ]
    for choice in compiled["choices"]:
        lines.extend(
            [
                f"### {choice['award_label']['en']}: {choice['player_name']}",
                "",
                f"- Team: {choice['team']}",
                f"- Reason: {choice.get('selection_reason')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _audit_rankings(rankings: dict[str, Any]) -> dict[str, Any]:
    role_rankings = rankings.get("rankings", {}).get("roles", {})
    return {
        "schema_version": 1,
        "match_date": rankings.get("match_date"),
        "scoring_version": rankings.get("scoring_version"),
        "event_sources": rankings.get("event_sources", {}),
        "matches": rankings.get("matches", []),
        "match_flows": rankings.get("match_flows", {}),
        "rankings": {
            "headline": list(rankings.get("rankings", {}).get("headline", []))[:50],
            "roles": {
                role: list(items)[:25]
                for role, items in role_rankings.items()
            },
        },
        "rank_lookup": {
            str(player.get("player_id")): {
                "player_name": player.get("player_name"),
                "team": player.get("team"),
                "match_no": player.get("match_no"),
                "headline_rank": player.get("headline_rank"),
                "headline_score": player.get("headline_score"),
                "role_ranks": {
                    key.removesuffix("_rank"): value
                    for key, value in player.items()
                    if key.endswith("_rank")
                },
            }
            for player in rankings.get("players", [])
            if isinstance(player, dict) and player.get("player_id")
        },
    }


def _uses_goal_involvements(rankings: dict[str, Any]) -> bool:
    event_sources = rankings.get("event_sources")
    if isinstance(event_sources, dict) and event_sources.get("goal_involvements"):
        return event_sources.get("goal_involvements") == "fifa_timeline_api"
    return str(rankings.get("scoring_version") or "") == "v0.4"


def _event_sources(rankings: dict[str, Any], *, uses_goal_involvements: bool) -> dict[str, str]:
    event_sources = rankings.get("event_sources")
    if isinstance(event_sources, dict):
        return {str(key): str(value) for key, value in event_sources.items()}
    if uses_goal_involvements:
        return {"goal_involvements": "fifa_timeline_api"}
    return {}


def _remove_retired_sidecars(
    site_dir: str | Path,
    reports_path: Path,
    match_date: str,
) -> None:
    dated_path = Path(site_dir) / "editorial" / match_date
    for filename in (
        "evidence.json",
        "fact_bank.zh.json",
        "brief.en.json",
        "external_evidence.json",
    ):
        path = dated_path / filename
        if path.exists():
            path.unlink()
    pre_review = reports_path / f"{match_date}.pre-review.md"
    if pre_review.exists():
        pre_review.unlink()
