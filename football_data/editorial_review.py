from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from football_data.llm_client import AgentTextClient


class PlayerReview(BaseModel):
    player_id: str
    verdict: str
    note: str


class BlockingFinding(BaseModel):
    category: str
    severity: str
    evidence: str
    recommended_action: str


class EditorialReviewOutput(BaseModel):
    schema_version: int = 1
    review_profile: str
    status: str
    reviewed_dimensions: list[str] = Field(default_factory=list)
    selected_player_reviews: list[PlayerReview] = Field(default_factory=list)
    unselected_candidate_reviews: list[PlayerReview] = Field(default_factory=list)
    blocking_findings: list[BlockingFinding] = Field(default_factory=list)
    revision_summary: str


def build_editorial_review_payload(
    *,
    selection_decision: dict[str, Any],
    candidate_pool: dict[str, Any],
    copy: dict[str, Any],
    selection_validation: dict[str, Any] | None = None,
    copy_validation: dict[str, Any] | None = None,
    review_profile: dict[str, Any] | None = None,
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
    required_top_n = int((review_profile or {}).get("required_unselected_headline_top_n") or 8)
    required_unselected = [
        _review_candidate(candidate, "player_of_the_day")
        for candidate in sorted(
            candidate_pool.get("selectable_candidates", []),
            key=lambda item: int(item.get("headline_rank") or 9999),
        )
        if int(candidate.get("headline_rank") or 9999) <= required_top_n
        and str(candidate.get("player_id") or "") not in selected_ids
    ]
    match_counts = Counter(str(item.get("match_key") or "") for item in selected if item.get("match_key"))
    payload = {
        "schema_version": 1,
        "match_date": candidate_pool.get("match_date"),
        "review_profile": (review_profile or {}).get("id"),
        "selected": selected,
        "required_unselected_candidate_reviews": required_unselected,
        "slate_counts": {
            "matches": dict(match_counts),
        },
        "selection_validation": selection_validation,
        "copy_validation": copy_validation,
        "copy": {
            language: [
                {
                    "player_id": item.get("player_id"),
                    "title": item.get("title"),
                    "body": item.get("body"),
                }
                for item in payload.get("items", [])
                if isinstance(item, dict)
            ]
            for language, payload in copy.items()
            if isinstance(payload, dict)
        },
    }
    public_card_count = _public_card_count_context(
        selected_count=len(selected),
        candidate_pool=candidate_pool,
        selection_config=selection_config,
    )
    if public_card_count:
        payload["public_card_count"] = public_card_count
    return payload


def run_ai_editorial_review(
    review_payload: dict[str, Any],
    text_client: AgentTextClient,
    review_profile: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    instructions = "\n".join(str(item) for item in review_profile.get("instructions", []))
    response = text_client.complete(
        role="review_editor",
        model=model,
        instructions=instructions,
        user_input=json.dumps(review_payload, ensure_ascii=False),
        output_type=EditorialReviewOutput,
    )
    payload = json.loads(response)
    if not isinstance(payload, dict):
        raise ValueError("Editorial review agent must return a JSON object")
    return payload


def validate_editorial_review(
    review: dict[str, Any],
    review_profile: dict[str, Any],
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    if int(review.get("schema_version") or 0) != 1:
        warnings.append("editorial_review.schema_version must be 1")
    if str(review.get("review_profile") or "") != str(review_profile.get("id") or ""):
        warnings.append("editorial_review.review_profile does not match active review profile")
    required_dimensions = [str(item) for item in review_profile.get("required_dimensions", [])]
    reviewed_dimensions = {
        str(item)
        for item in review.get("reviewed_dimensions", [])
        if str(item).strip()
    }
    for dimension in required_dimensions:
        if dimension not in reviewed_dimensions:
            warnings.append(f"missing reviewed dimension {dimension}")

    selected_review_ids = {
        str(item.get("player_id") or "")
        for item in review.get("selected_player_reviews", [])
        if isinstance(item, dict)
    }
    for item in review_payload.get("selected", []):
        player_id = str(item.get("player_id") or "")
        if player_id and player_id not in selected_review_ids:
            warnings.append(f"missing selected player review for {item.get('player_name') or player_id}")

    unselected_review_ids = {
        str(item.get("player_id") or "")
        for item in review.get("unselected_candidate_reviews", [])
        if isinstance(item, dict)
    }
    for item in review_payload.get("required_unselected_candidate_reviews", []):
        player_id = str(item.get("player_id") or "")
        if player_id and player_id not in unselected_review_ids:
            warnings.append(f"missing unselected candidate review for {item.get('player_name') or player_id}")

    blocking_findings = review.get("blocking_findings", [])
    if not isinstance(blocking_findings, list):
        warnings.append("editorial_review.blocking_findings must be a list")
        blocking_findings = []
    for finding in blocking_findings:
        if not isinstance(finding, dict):
            warnings.append("blocking finding must be an object")
            continue
        category = str(finding.get("category") or "").strip()
        severity = str(finding.get("severity") or "").strip()
        evidence = str(finding.get("evidence") or "").strip()
        action = str(finding.get("recommended_action") or "").strip()
        if not category or not severity or not evidence or not action:
            warnings.append("blocking finding must include category, severity, evidence, and recommended_action")
        else:
            warnings.append(f"blocking finding {category}: {evidence}")

    status = str(review.get("status") or "").strip()
    if status != "pass":
        warnings.append(f"editorial_review.status must be pass, got {status or 'missing'}")
    if not str(review.get("revision_summary") or "").strip():
        warnings.append("editorial_review.revision_summary is required")

    return {
        "schema_version": 1,
        "status": "failed" if warnings else "pass",
        "warnings": warnings,
    }


def passing_editorial_review(
    review_profile: dict[str, Any],
    review_payload: dict[str, Any],
    *,
    revision_summary: str = "No blocking reader-intuition issue remains.",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "review_profile": review_profile["id"],
        "status": "pass",
        "reviewed_dimensions": list(review_profile.get("required_dimensions", [])),
        "selected_player_reviews": [
            {
                "player_id": item["player_id"],
                "verdict": "pass",
                "note": "Public case is supported by the selected evidence packet.",
            }
            for item in review_payload.get("selected", [])
        ],
        "unselected_candidate_reviews": [
            {
                "player_id": item["player_id"],
                "verdict": "pass",
                "note": "Not selected after comparing direct impact, slate balance, and stronger public cases.",
            }
            for item in review_payload.get("required_unselected_candidate_reviews", [])
        ],
        "blocking_findings": [],
        "revision_summary": revision_summary,
    }


def _public_card_count_context(
    *,
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
    if min_count <= 0 or max_count <= 0:
        return None
    if min_count > max_count:
        min_count, max_count = max_count, min_count
    match_count = len(
        {
            str(candidate.get("match_key") or "")
            for candidate in candidate_pool.get("selectable_candidates", [])
            if isinstance(candidate, dict) and candidate.get("match_key")
        }
    )
    return {
        "selected": selected_count,
        "min": min_count,
        "max": max_count,
        "match_count": match_count,
    }


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
        "progression_benchmark": candidate.get("progression_benchmark"),
        "display_names": candidate.get("display_names", {}),
    }
