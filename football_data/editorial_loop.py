from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from football_data.editorial_copy import build_copy_payloads
from football_data.editorial_copy_validation import validate_copy
from football_data.editorial_registry import (
    load_copy_profile,
    load_copy_review_profile,
    load_editorial_experiment,
    load_selection_review_profile,
)
from football_data.editorial_selection import normalize_selection_decision, repair_selection_decision
from football_data.editorial_style_calibration import load_style_calibration
from football_data.editorial_validation import validate_selection_decision


DEFAULT_MAX_SELECTION_ROUNDS = 3
DEFAULT_MAX_COPY_ROUNDS = 3


def promote_editorial_loop(
    *,
    match_date: str,
    agent_runs_dir: str | Path = "agent-runs",
    config_dir: str | Path = "config/editorial",
    max_selection_rounds: int = DEFAULT_MAX_SELECTION_ROUNDS,
    max_copy_rounds: int = DEFAULT_MAX_COPY_ROUNDS,
) -> dict[str, Any]:
    audit_dir = Path(agent_runs_dir) / match_date
    run = _load_json(audit_dir / "run.json")
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    experiment = load_editorial_experiment(run.get("experiment_id"), config_dir)
    selection_profile = load_selection_review_profile(str(experiment["selection_review_profile"]), config_dir)
    copy_review_profile = load_copy_review_profile(str(experiment["copy_review_profile"]), config_dir)
    copy_profiles = {
        language: load_copy_profile(str(profile_id), config_dir)
        for language, profile_id in (experiment.get("copy_profiles") or {}).items()
    }

    selection_result = _promote_selection_round(
        audit_dir=audit_dir,
        candidate_pool=candidate_pool,
        experiment=experiment,
        review_profile=selection_profile,
        max_rounds=max_selection_rounds,
    )
    if selection_result["status"] != "pass":
        summary = _loop_summary(
            status="needs_human_review",
            match_date=match_date,
            experiment=experiment,
            selection_loop=selection_result,
            copy_loop=None,
        )
        _write_json(audit_dir / "editorial_loop_summary.json", summary)
        raise RuntimeError("selection loop did not pass")

    copy_result = _promote_copy_round(
        audit_dir=audit_dir,
        candidate_pool=candidate_pool,
        selection_decision=selection_result["selection_decision"],
        copy_profiles=copy_profiles,
        review_profile=copy_review_profile,
        config_dir=config_dir,
        max_rounds=max_copy_rounds,
    )
    if copy_result["status"] != "pass":
        summary = _loop_summary(
            status="needs_human_review",
            match_date=match_date,
            experiment=experiment,
            selection_loop=selection_result,
            copy_loop=copy_result,
        )
        _write_json(audit_dir / "editorial_loop_summary.json", summary)
        raise RuntimeError("copy loop did not pass")

    selection_decision = selection_result["selection_decision"]
    copy = copy_result["copy"]
    _write_json(audit_dir / "final_selection_decision.json", selection_decision)
    _write_json(audit_dir / "final_copy.json", copy)
    _write_json(audit_dir / "selection_decision.json", selection_decision)
    _write_json(audit_dir / "copy.json", copy)
    summary = _loop_summary(
        status="success",
        match_date=match_date,
        experiment=experiment,
        selection_loop=selection_result,
        copy_loop=copy_result,
    )
    _write_json(audit_dir / "editorial_loop_summary.json", summary)
    return summary


def validate_editorial_loop_summary(
    summary: dict[str, Any],
    selection_decision: dict[str, Any],
    copy: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    if int(summary.get("schema_version") or 0) != 1:
        warnings.append("editorial_loop_summary.schema_version must be 1")
    if str(summary.get("status") or "") != "success":
        warnings.append("editorial_loop_summary.status must be success")
    selection_loop = summary.get("selection_loop")
    if not isinstance(selection_loop, dict) or selection_loop.get("status") != "pass":
        warnings.append("selection_loop.status must be pass")
    copy_loop = summary.get("copy_loop")
    if not isinstance(copy_loop, dict) or copy_loop.get("status") != "pass":
        warnings.append("copy_loop.status must be pass")
    summary_selected = [
        str(player_id)
        for player_id in summary.get("selected_player_ids", [])
        if str(player_id).strip()
    ]
    actual_selected = [
        str(item.get("player_id") or "")
        for item in selection_decision.get("selected", [])
        if isinstance(item, dict)
    ]
    if summary_selected and summary_selected != actual_selected:
        warnings.append("editorial_loop_summary.selected_player_ids do not match selection_decision")
    copied_ids = {
        str(item.get("player_id") or "")
        for payload in copy.values()
        if isinstance(payload, dict)
        for item in payload.get("items", [])
        if isinstance(item, dict)
    }
    missing_copy = [player_id for player_id in actual_selected if player_id not in copied_ids]
    if missing_copy:
        warnings.append(f"copy missing selected player {missing_copy[0]}")
    return {
        "schema_version": 1,
        "status": "failed" if warnings else "pass",
        "warnings": warnings,
    }


def _promote_selection_round(
    *,
    audit_dir: Path,
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
    review_profile: dict[str, Any],
    max_rounds: int,
) -> dict[str, Any]:
    last_validation: dict[str, Any] | None = None
    saw_round = False
    for round_no in range(1, max_rounds + 1):
        round_dir = audit_dir / "selection_rounds" / f"round_{round_no}"
        if not round_dir.exists():
            break
        saw_round = True
        try:
            decision = normalize_selection_decision(_load_json(round_dir / "selection_decision.json"))
            decision = repair_selection_decision(decision, candidate_pool)
            selection_validation = validate_selection_decision(decision, candidate_pool, experiment)
            _write_json(round_dir / "selection_validation.json", selection_validation)
            review_payload = build_selection_review_payload(
                selection_decision=decision,
                candidate_pool=candidate_pool,
                selection_validation=selection_validation,
                review_profile=review_profile,
                selection_config=experiment.get("selection"),
            )
            _write_json(round_dir / "selection_review_payload.json", review_payload)
            review = _load_json(round_dir / "selection_review.json")
            review_validation = validate_selection_review(review, review_profile, review_payload)
        except (FileNotFoundError, ValueError) as exc:
            review_validation = {
                "schema_version": 1,
                "status": "failed",
                "warnings": [str(exc)],
            }
            decision = {}
            selection_validation = {
                "schema_version": 1,
                "status": "failed",
                "warnings": [str(exc)],
            }
        _write_json(round_dir / "selection_review_validation.json", review_validation)
        last_validation = review_validation
        if selection_validation["status"] == "pass" and review_validation["status"] == "pass":
            return {
                "status": "pass",
                "rounds": round_no,
                "selected_round": round_no,
                "stop_reason": "no_blocking_selection_issues",
                "selection_decision": decision,
                "selection_validation": selection_validation,
                "selection_review_validation": review_validation,
            }
    return {
        "status": "needs_human_review",
        "rounds": max_rounds if saw_round else 0,
        "stop_reason": "max_selection_rounds_exceeded" if saw_round else "no_selection_rounds_submitted",
        "last_validation": last_validation,
    }


def _promote_copy_round(
    *,
    audit_dir: Path,
    candidate_pool: dict[str, Any],
    selection_decision: dict[str, Any],
    copy_profiles: dict[str, dict[str, Any]],
    review_profile: dict[str, Any],
    config_dir: str | Path,
    max_rounds: int,
) -> dict[str, Any]:
    copy_payload = build_copy_payloads(selection_decision, candidate_pool)
    last_validation: dict[str, Any] | None = None
    saw_round = False
    for round_no in range(1, max_rounds + 1):
        round_dir = audit_dir / "copy_rounds" / f"round_{round_no}"
        if not round_dir.exists():
            break
        saw_round = True
        try:
            copy = _load_json(round_dir / "copy.json")
            copy_validation = validate_copy(copy, copy_profiles, copy_payload=copy_payload)
            _write_json(round_dir / "copy_validation.json", copy_validation)
            review_payload = build_copy_review_payload(
                copy=copy,
                copy_payload=copy_payload,
                copy_validation=copy_validation,
                review_profile=review_profile,
                config_dir=config_dir,
            )
            _write_json(round_dir / "copy_review_payload.json", review_payload)
            review = _load_json(round_dir / "copy_review.json")
            review_validation = validate_copy_review(review, review_profile, review_payload)
        except (FileNotFoundError, ValueError) as exc:
            review_validation = {
                "schema_version": 1,
                "status": "failed",
                "warnings": [str(exc)],
            }
            copy = {}
            copy_validation = {
                "schema_version": 1,
                "status": "failed",
                "warnings": [str(exc)],
            }
        _write_json(round_dir / "copy_review_validation.json", review_validation)
        last_validation = review_validation
        if copy_validation["status"] == "pass" and review_validation["status"] == "pass":
            return {
                "status": "pass",
                "rounds": round_no,
                "selected_round": round_no,
                "stop_reason": "no_blocking_copy_issues",
                "copy": copy,
                "copy_validation": copy_validation,
                "copy_review_validation": review_validation,
            }
    return {
        "status": "needs_human_review",
        "rounds": max_rounds if saw_round else 0,
        "stop_reason": "max_copy_rounds_exceeded" if saw_round else "no_copy_rounds_submitted",
        "last_validation": last_validation,
    }


def build_selection_review_payload(
    *,
    selection_decision: dict[str, Any],
    candidate_pool: dict[str, Any],
    selection_validation: dict[str, Any],
    review_profile: dict[str, Any],
    selection_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_ids = {
        str(item.get("player_id") or "")
        for item in selection_decision.get("selected", [])
        if isinstance(item, dict)
    }
    selectable = {
        str(candidate.get("player_id") or ""): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
        if isinstance(candidate, dict)
    }
    selected = [
        _review_candidate(selectable[str(item.get("player_id"))], str(item.get("award_type") or ""))
        for item in selection_decision.get("selected", [])
        if isinstance(item, dict) and str(item.get("player_id") or "") in selectable
    ]
    required_top_n = int(review_profile.get("required_unselected_headline_top_n") or 8)
    required_unselected = [
        _review_candidate(candidate, "player_of_the_day")
        for candidate in sorted(
            candidate_pool.get("selectable_candidates", []),
            key=lambda item: int(item.get("headline_rank") or 9999),
        )
        if int(candidate.get("headline_rank") or 9999) <= required_top_n
        and str(candidate.get("player_id") or "") not in selected_ids
    ]
    return {
        "schema_version": 1,
        "match_date": candidate_pool.get("match_date"),
        "review_profile": review_profile["id"],
        "selected": selected,
        "required_unselected_candidate_reviews": required_unselected,
        "audit_candidates": [
            _review_audit_candidate(candidate)
            for candidate in candidate_pool.get("audit_candidates", [])[:12]
            if isinstance(candidate, dict)
        ],
        "selection_validation": selection_validation,
        "public_card_count": _public_card_count_context(
            len(selected),
            candidate_pool,
            selection_config,
        ),
    }


def validate_selection_review(
    review: dict[str, Any],
    review_profile: dict[str, Any],
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings = _base_review_warnings(review, review_profile, "selection_review")
    selected_ids = {
        str(item.get("player_id") or "")
        for item in review_payload.get("selected", [])
        if isinstance(item, dict) and item.get("player_id")
    }
    reviewed_selected = {
        str(item.get("player_id") or "")
        for item in review.get("selected_player_reviews", [])
        if isinstance(item, dict)
    }
    for player_id in selected_ids:
        if player_id not in reviewed_selected:
            warnings.append(f"missing selected player review for {player_id}")
    slate = review.get("slate_assessment")
    if not isinstance(slate, dict):
        warnings.append("selection_review.slate_assessment must be an object")
        slate = {}
    required_slate_fields = [
        str(item)
        for item in review_profile.get("required_slate_assessment_fields", [])
        if str(item).strip()
    ]
    for field in required_slate_fields:
        if not _has_review_value(slate.get(field)):
            warnings.append(f"missing slate_assessment.{field}")
    weakest = slate.get("weakest_selected_card")
    if selected_ids and not _card_refers_to_id(weakest, selected_ids):
        warnings.append("weakest_selected_card must identify a selected player_id")
    alternative = slate.get("alternative_slate_comparison")
    if isinstance(alternative, list) and len(alternative) < 2:
        warnings.append("alternative_slate_comparison must compare at least two slate options")
    revision = str(slate.get("revision_decision") or "").strip()
    if revision != "keep":
        warnings.append("passing selection_review must finish with revision_decision keep")
    unresolved = review.get("unresolved_objections", [])
    if unresolved:
        warnings.append("selection_review has unresolved objections")
    warnings.extend(_blocking_warnings(review, "selection_review"))
    return _validation_result(warnings)


def build_copy_review_payload(
    *,
    copy: dict[str, Any],
    copy_payload: dict[str, Any],
    copy_validation: dict[str, Any],
    review_profile: dict[str, Any],
    config_dir: str | Path = "config/editorial",
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "match_date": copy_payload.get("match_date"),
        "review_profile": review_profile["id"],
        "copy_validation": copy_validation,
        "copy_payload": copy_payload,
        "copy": {
            language: [
                {
                    "player_id": item.get("player_id"),
                    "title": item.get("title"),
                    "body": item.get("body"),
                }
                for item in language_payload.get("items", [])
                if isinstance(item, dict)
            ]
            for language, language_payload in copy.items()
            if isinstance(language_payload, dict)
        },
    }
    style_calibration = _style_calibration_context(review_profile, config_dir)
    if style_calibration:
        payload["style_calibration"] = style_calibration
    return payload


def validate_copy_review(
    review: dict[str, Any],
    review_profile: dict[str, Any],
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings = _base_review_warnings(review, review_profile, "copy_review")
    required_reviews = {
        (str(item.get("player_id") or ""), language)
        for language, items in review_payload.get("copy", {}).items()
        for item in items
        if isinstance(item, dict) and item.get("player_id")
    }
    item_reviews = {
        (str(item.get("player_id") or ""), str(item.get("language") or ""))
        for item in review.get("item_reviews", [])
        if isinstance(item, dict)
    }
    for player_id, language in required_reviews:
        if (player_id, language) not in item_reviews:
            warnings.append(f"missing copy review for {language}:{player_id}")
    unresolved = review.get("unresolved_comments", [])
    if unresolved:
        warnings.append("copy_review has unresolved comments")
    warnings.extend(_blocking_warnings(review, "copy_review"))
    return _validation_result(warnings)


def _base_review_warnings(
    review: dict[str, Any],
    review_profile: dict[str, Any],
    label: str,
) -> list[str]:
    warnings: list[str] = []
    if int(review.get("schema_version") or 0) != 1:
        warnings.append(f"{label}.schema_version must be 1")
    status = str(review.get("status") or "").strip()
    if status != "pass":
        warnings.append(f"{label}.status must be pass, got {status or 'missing'}")
    required_dimensions = [str(item) for item in review_profile.get("required_dimensions", [])]
    reviewed_dimensions = {
        str(item)
        for item in review.get("reviewed_dimensions", [])
        if str(item).strip()
    }
    for dimension in required_dimensions:
        if dimension not in reviewed_dimensions:
            warnings.append(f"missing reviewed dimension {dimension}")
    if not str(review.get("revision_summary") or "").strip():
        warnings.append(f"{label}.revision_summary is required")
    return warnings


def _blocking_warnings(review: dict[str, Any], label: str) -> list[str]:
    warnings: list[str] = []
    blocking_findings = review.get("blocking_findings", [])
    if not isinstance(blocking_findings, list):
        return [f"{label}.blocking_findings must be a list"]
    for finding in blocking_findings:
        if not isinstance(finding, dict):
            warnings.append("blocking finding must be an object")
            continue
        category = str(finding.get("category") or "").strip()
        evidence = str(finding.get("evidence") or "").strip()
        if category and evidence:
            warnings.append(f"blocking finding {category}: {evidence}")
        else:
            warnings.append("blocking finding must include category and evidence")
    return warnings


def _loop_summary(
    *,
    status: str,
    match_date: str,
    experiment: dict[str, Any],
    selection_loop: dict[str, Any],
    copy_loop: dict[str, Any] | None,
) -> dict[str, Any]:
    selection_decision = selection_loop.get("selection_decision") if isinstance(selection_loop, dict) else {}
    selected_ids = [
        str(item.get("player_id") or "")
        for item in (selection_decision or {}).get("selected", [])
        if isinstance(item, dict)
    ]
    copy_loop = copy_loop or {
        "status": "not_started",
        "rounds": 0,
        "stop_reason": "selection_loop_not_passed",
    }
    return {
        "schema_version": 1,
        "status": status,
        "match_date": match_date,
        "experiment_id": experiment["id"],
        "workflow_variant": experiment["workflow_variant"],
        "selection_review_profile": experiment.get("selection_review_profile"),
        "copy_review_profile": experiment.get("copy_review_profile"),
        "selection_loop": _loop_public(selection_loop),
        "copy_loop": _loop_public(copy_loop),
        "selected_player_ids": selected_ids,
    }


def _loop_public(loop: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in loop.items()
        if key
        in {
            "status",
            "rounds",
            "selected_round",
            "stop_reason",
            "selection_validation",
            "selection_review_validation",
            "copy_validation",
            "copy_review_validation",
            "last_validation",
        }
    }


def _public_card_count_context(
    selected_count: int,
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any] | None,
) -> dict[str, int] | None:
    if not isinstance(selection_config, dict):
        return None
    raw_count = selection_config.get("public_card_count")
    if not isinstance(raw_count, dict):
        return None
    min_count = int(raw_count.get("min") or 0)
    max_count = int(raw_count.get("max") or 0)
    match_count = len(
        {
            str(candidate.get("match_key") or "")
            for candidate in candidate_pool.get("selectable_candidates", [])
            if isinstance(candidate, dict) and candidate.get("match_key")
        }
    )
    return {
        "selected": selected_count,
        "min": min(min_count, max_count),
        "max": max(min_count, max_count),
        "match_count": match_count,
    }


def _style_calibration_context(
    review_profile: dict[str, Any],
    config_dir: str | Path,
) -> dict[str, Any] | None:
    raw = review_profile.get("style_calibration")
    if not isinstance(raw, dict):
        return None
    languages = [str(language) for language in raw.get("languages", []) if str(language).strip()]
    max_count = int(raw.get("max_examples_per_language") or 0) or None
    categories = [str(category) for category in raw.get("categories", []) if str(category).strip()] or None
    context: dict[str, Any] = {
        "review_instruction": str(
            raw.get("review_instruction")
            or "Use these examples to detect repeatable taste failures."
        )
    }
    for language in languages:
        examples = load_style_calibration(
            language,
            config_dir,
            categories=categories,
            max_examples=max_count,
        )
        if examples:
            context[language] = examples
    return context if len(context) > 1 else None


def _review_candidate(candidate: dict[str, Any], award_type: str) -> dict[str, Any]:
    active_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
    return {
        "player_id": candidate.get("player_id"),
        "player_name": candidate.get("player_name"),
        "team": candidate.get("team"),
        "opponent": candidate.get("opponent"),
        "match_key": candidate.get("match_key"),
        "match_no": candidate.get("match_no"),
        "award_type": award_type,
        "headline_rank": candidate.get("headline_rank"),
        "headline_score": candidate.get("headline_score"),
        "eligible_awards": candidate.get("eligible_awards", []),
        "metrics": active_context.get("metrics", {}),
        "evidence_chips": active_context.get("evidence_chips", {"en": [], "zh": []}),
        "display_names": candidate.get("display_names", {}),
        "data_sources": candidate.get("data_sources", {}),
    }


def _review_audit_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    audit_type = str(candidate.get("audit_type") or "")
    active_context = (candidate.get("audit_contexts") or {}).get(audit_type) or {}
    return {
        "player_id": candidate.get("player_id"),
        "player_name": candidate.get("player_name"),
        "team": candidate.get("team"),
        "opponent": candidate.get("opponent"),
        "match_key": candidate.get("match_key"),
        "match_no": candidate.get("match_no"),
        "audit_type": audit_type,
        "headline_rank": candidate.get("headline_rank"),
        "headline_score": candidate.get("headline_score"),
        "metrics": active_context.get("metrics", {}),
        "evidence_chips": active_context.get("evidence_chips", {"en": [], "zh": []}),
        "display_names": candidate.get("display_names", {}),
        "data_sources": candidate.get("data_sources", {}),
    }


def _has_review_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def _card_refers_to_id(value: Any, valid_ids: set[str]) -> bool:
    if not isinstance(value, dict):
        return False
    player_id = str(value.get("player_id") or "")
    return bool(player_id and player_id in valid_ids)


def _validation_result(warnings: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "failed" if warnings else "pass",
        "warnings": warnings,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing local editorial loop file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Local editorial loop file must contain a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
