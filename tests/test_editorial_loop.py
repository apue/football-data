import json
from pathlib import Path

import pytest

from editorial_test_helpers import build_test_copy, build_test_selection_decision


def test_editorial_loop_promotes_auditable_rounds_into_canonical_artifacts(tmp_path):
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
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
    selection = build_test_selection_decision(candidate_pool, experiment)
    copy = build_test_copy(build_copy_payloads(selection, candidate_pool))

    _write_json(audit_dir / "selection_rounds" / "round_1" / "selection_decision.json", selection)
    _write_json(
        audit_dir / "selection_rounds" / "round_1" / "selection_review.json",
        _passing_selection_review(selection, candidate_pool, experiment),
    )
    _write_json(audit_dir / "copy_rounds" / "round_1" / "copy.json", copy)
    _write_json(
        audit_dir / "copy_rounds" / "round_1" / "copy_review.json",
        _passing_copy_review(copy),
    )

    summary = promote_editorial_loop(
        match_date="2026-06-22",
        agent_runs_dir=tmp_path / "agent-runs",
    )

    assert summary["status"] == "success"
    assert summary["selection_loop"]["rounds"] == 1
    assert summary["copy_loop"]["rounds"] == 1
    assert summary["selection_loop"]["stop_reason"] == "no_blocking_selection_issues"
    assert summary["copy_loop"]["stop_reason"] == "no_blocking_copy_issues"
    assert (audit_dir / "selection_rounds" / "round_1" / "selection_review_payload.json").exists()
    assert (audit_dir / "selection_rounds" / "round_1" / "selection_review_validation.json").exists()
    assert (audit_dir / "copy_rounds" / "round_1" / "copy_review_payload.json").exists()
    assert (audit_dir / "copy_rounds" / "round_1" / "copy_review_validation.json").exists()
    final_selection = _load_json(audit_dir / "final_selection_decision.json")
    assert [item["player_id"] for item in final_selection["selected"]] == [
        item["player_id"] for item in selection["selected"]
    ]
    assert _load_json(audit_dir / "final_copy.json") == copy
    assert _load_json(audit_dir / "selection_decision.json") == final_selection
    assert _load_json(audit_dir / "copy.json") == copy
    assert _load_json(audit_dir / "editorial_loop_summary.json")["status"] == "success"

    result = compile_local_editorial(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )

    assert result["status"] == "success"
    choices = _load_json(tmp_path / "site" / "editorial" / "2026-06-22" / "choices.json")
    generation = choices["editorial_generation"]
    assert generation["experiment_id"] == "bounded_editorial_loop_v1"
    assert generation["editorial_loop_status"] == "pass"
    assert generation["selection_rounds"] == 1
    assert generation["copy_rounds"] == 1


def test_compile_local_editorial_rejects_unpromoted_one_shot_artifacts(tmp_path):
    from football_data.editorial_copy import build_copy_payloads
    from football_data.editorial_local import compile_local_editorial, prepare_editorial_packet
    from football_data.editorial_registry import load_editorial_experiment

    prepare_editorial_packet(
        match_date="2026-06-22",
        db_path="data/latest.sqlite",
        agent_runs_dir=tmp_path / "agent-runs",
        run_out_path=tmp_path / "editorial-v2-run.json",
    )
    audit_dir = tmp_path / "agent-runs" / "2026-06-22"
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    selection = build_test_selection_decision(candidate_pool, load_editorial_experiment())
    copy = build_test_copy(build_copy_payloads(selection, candidate_pool))
    _write_json(audit_dir / "selection_decision.json", selection)
    _write_json(audit_dir / "copy.json", copy)

    with pytest.raises(RuntimeError, match="promoted editorial loop"):
        compile_local_editorial(
            match_date="2026-06-22",
            db_path="data/latest.sqlite",
            site_dir=tmp_path / "site",
            reports_dir=tmp_path / "reports",
            manifests_dir="manifests",
            agent_runs_dir=tmp_path / "agent-runs",
            run_out_path=tmp_path / "editorial-v2-run.json",
        )


def test_editorial_loop_blocks_failed_selection_review(tmp_path):
    from football_data.editorial_local import prepare_editorial_packet
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
    selection = build_test_selection_decision(candidate_pool, load_editorial_experiment())
    review = _passing_selection_review(selection, candidate_pool, load_editorial_experiment())
    review["status"] = "failed"
    review["blocking_findings"] = [
        {
            "category": "obvious_omission",
            "severity": "high",
            "evidence": "The slate omits a stronger direct-impact candidate.",
            "recommended_action": "Replace the weakest selected card.",
        }
    ]
    _write_json(audit_dir / "selection_rounds" / "round_1" / "selection_decision.json", selection)
    _write_json(audit_dir / "selection_rounds" / "round_1" / "selection_review.json", review)

    with pytest.raises(RuntimeError, match="selection loop did not pass"):
        promote_editorial_loop(
            match_date="2026-06-22",
            agent_runs_dir=tmp_path / "agent-runs",
            max_selection_rounds=1,
        )

    summary = _load_json(audit_dir / "editorial_loop_summary.json")
    assert summary["status"] == "needs_human_review"
    assert summary["selection_loop"]["stop_reason"] == "max_selection_rounds_exceeded"


def _passing_selection_review(
    selection: dict,
    candidate_pool: dict,
    experiment: dict,
) -> dict:
    from football_data.editorial_loop import build_selection_review_payload
    from football_data.editorial_registry import load_selection_review_profile
    from football_data.editorial_validation import validate_selection_decision

    selected = list(selection["selected"])
    review_profile = load_selection_review_profile(experiment["selection_review_profile"])
    review_payload = build_selection_review_payload(
        selection_decision=selection,
        candidate_pool=candidate_pool,
        selection_validation=validate_selection_decision(selection, candidate_pool, experiment),
        review_profile=review_profile,
        selection_config=experiment["selection"],
    )
    required_unselected = _required_unselected_reviews(review_payload)
    strongest_omitted = _first_player_id(review_payload.get("required_unselected_candidate_reviews")) or _first_player_id(
        review_payload.get("required_impact_candidate_reviews")
    )
    impact_challenger = _first_player_id(review_payload.get("required_impact_candidate_reviews"))
    add_challenger = _first_player_id(review_payload.get("card_count_challengers"))
    return {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": review_profile["required_dimensions"],
        "selected_player_reviews": [
            {
                "player_id": item["player_id"],
                "verdict": "pass",
                "note": "The public case is supported by direct match evidence.",
            }
            for item in selected
        ],
        "unselected_candidate_reviews": required_unselected,
        "slate_assessment": {
            "reader_questions": ["Is there a stronger direct-impact omission?"],
            "alternative_slate_comparison": [
                {"card_count": len(selected), "tradeoff": "current slate"},
                {"card_count": len(selected) + 1, "tradeoff": "add strongest omitted card"},
                {"card_count": max(0, len(selected) - 1), "tradeoff": "drop weakest selected"},
            ],
            "weakest_selected_card": {
                "player_id": selected[-1]["player_id"],
                "reason": "Checked against available omissions.",
            },
            "strongest_omitted_card": {
                "player_id": strongest_omitted,
                "reason": "No omitted candidate forced a replacement.",
            },
            "drop_weakest_verdict": {
                "decision": "keep",
                "reason": "The weakest selected card remains above the publishable line.",
            },
            "replace_weakest_verdict": {
                "decision": "keep",
                "replacement_player_id": strongest_omitted,
                "reason": "No replacement improves the slate.",
            },
            "impact_challenger_verdict": {
                "player_id": impact_challenger,
                "decision": "omit",
                "reason": "The strongest omitted impact challenger was checked.",
            },
            "add_card_verdict": {
                "player_id": add_challenger,
                "decision": "keep_count",
                "reason": "Adding the strongest omitted card would not improve the slate.",
            },
            "preferred_card_count": len(selected),
            "revision_decision": "keep",
        },
        "blocking_findings": [],
        "resolved_objections": [],
        "unresolved_objections": [],
        "revision_summary": "No blocking selection issue remains.",
    }


def _required_unselected_reviews(review_payload: dict) -> list[dict[str, str]]:
    seen: set[str] = set()
    reviews: list[dict[str, str]] = []
    for key in (
        "required_unselected_candidate_reviews",
        "required_impact_candidate_reviews",
        "card_count_challengers",
    ):
        for item in review_payload.get(key, []):
            if not isinstance(item, dict):
                continue
            player_id = str(item.get("player_id") or "")
            if not player_id or player_id in seen:
                continue
            seen.add(player_id)
            reviews.append(
                {
                    "player_id": player_id,
                    "status": "omit",
                    "note": "Checked as a required omitted candidate.",
                }
            )
    return reviews


def _first_player_id(items) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        player_id = str(item.get("player_id") or "").strip()
        if player_id:
            return player_id
    return None


def _passing_copy_review(copy: dict) -> dict:
    player_ids = [
        item["player_id"]
        for language in ("en", "zh")
        for item in copy.get(language, {}).get("items", [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": [
            "fact_support",
            "english_flow",
            "zh_style",
            "title_core_fact",
            "unsupported_claims",
        ],
        "item_reviews": [
            {
                "player_id": player_id,
                "language": language,
                "verdict": "pass",
                "note": "The copy is supported by the selected evidence packet.",
            }
            for language in ("en", "zh")
            for player_id in player_ids
        ],
        "blocking_findings": [],
        "resolved_comments": [],
        "unresolved_comments": [],
        "revision_summary": "No blocking copy issue remains.",
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
