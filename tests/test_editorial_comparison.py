from __future__ import annotations

import json


def test_resolve_swapped_pairwise_keeps_consistent_winner():
    from football_data.editorial_comparison import resolve_swapped_pairwise

    first = {
        "match_date": "2026-06-29",
        "overall": {"winner": "B", "confidence": 0.8, "rationale": "B is better."},
        "criteria": [],
        "risk_flags": [],
    }
    second = {
        "match_date": "2026-06-29",
        "overall": {"winner": "B", "confidence": 0.6, "rationale": "B is still better."},
        "criteria": [],
        "risk_flags": [],
    }

    result = resolve_swapped_pairwise(first, second)

    assert result["verdict"] == "B"
    assert result["recommended_action"] == "prefer_b"
    assert result["confidence"] == 0.7
    assert result["position_consistency"] == "consistent"


def test_resolve_swapped_pairwise_downgrades_inconsistent_winner_to_tie():
    from football_data.editorial_comparison import resolve_swapped_pairwise

    first = {
        "match_date": "2026-06-29",
        "overall": {"winner": "A", "confidence": 0.9, "rationale": "A is better."},
        "criteria": [],
        "risk_flags": [],
    }
    second = {
        "match_date": "2026-06-29",
        "overall": {"winner": "B", "confidence": 0.9, "rationale": "B is better."},
        "criteria": [],
        "risk_flags": [],
    }

    result = resolve_swapped_pairwise(first, second)

    assert result["verdict"] == "tie"
    assert result["recommended_action"] == "tie"
    assert result["confidence"] == 0.5
    assert result["position_consistency"] == "inconsistent"


def test_validation_summary_uses_promoted_copy_round(tmp_path):
    from football_data.editorial_comparison import _validation_summary

    run_dir = tmp_path / "run"
    (run_dir / "copy_rounds" / "round_1").mkdir(parents=True)
    (run_dir / "copy_rounds" / "round_2").mkdir(parents=True)
    (run_dir / "editorial_loop_summary.json").write_text(
        json.dumps(
            {
                "copy_loop": {
                    "selected_round": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "copy_rounds" / "round_1" / "copy_review_validation.json").write_text(
        json.dumps({"status": "failed", "warnings": ["round 1 failed"]}),
        encoding="utf-8",
    )
    (run_dir / "copy_rounds" / "round_2" / "copy_review_validation.json").write_text(
        json.dumps({"status": "pass", "warnings": []}),
        encoding="utf-8",
    )

    summary = _validation_summary(run_dir)

    assert summary["selected_copy_round"] == 2
    assert summary["round_copy_review"] == {"status": "pass", "warnings": []}
