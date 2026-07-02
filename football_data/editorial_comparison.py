from __future__ import annotations

import json
from pathlib import Path
from typing import Any


COMPARISON_SCHEMA_VERSION = 1
DEFAULT_VARIANT_ID = "fresh_subagent_editorial_loop_v0"

CRITERIA: list[dict[str, str]] = [
    {
        "id": "selection_quality",
        "description": "Better overall public slate: strongest candidates, no obvious omission, no weak coverage filler.",
    },
    {
        "id": "award_typing",
        "description": "Player of the Day and Impact Pick labels match the player evidence and public angle.",
    },
    {
        "id": "factual_safety",
        "description": "No unsupported winner, equaliser, assist, shoot-out, scoreline, or metric claim.",
    },
    {
        "id": "english_copy",
        "description": "English is clear, compact, football-led, and not a metric dump.",
    },
    {
        "id": "chinese_copy",
        "description": "Chinese reads like it was written directly in Chinese, with core-fact titles and no abstract filler.",
    },
    {
        "id": "reader_value",
        "description": "The card count and angles improve the reader's understanding of the day.",
    },
]


def build_comparison_packet(
    *,
    match_date: str,
    control_root: str | Path = "agent-runs",
    variant_root: str | Path = f"agent-runs-ab/{DEFAULT_VARIANT_ID}",
    variant_id: str = DEFAULT_VARIANT_ID,
) -> dict[str, Any]:
    control_dir = Path(control_root) / match_date
    variant_dir = Path(variant_root) / match_date
    fact_pack_path = _first_existing(
        variant_dir / "editorial_fact_pack.md",
        control_dir / "editorial_fact_pack.md",
    )
    fact_pack_json_path = _first_existing(
        variant_dir / "editorial_fact_pack.json",
        control_dir / "editorial_fact_pack.json",
    )
    candidate_pool_path = _first_existing(
        variant_dir / "candidate_pool.json",
        control_dir / "candidate_pool.json",
    )

    packet = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "match_date": match_date,
        "variant_id": variant_id,
        "source_policy": "Use only FIFA-derived packet/fact-pack/candidate evidence in this repository.",
        "rubric": {
            "scale": "pairwise",
            "criteria": CRITERIA,
            "instructions": [
                "Do not prefer a candidate because it is longer.",
                "Do not prefer a candidate because it appears first.",
                "Ties are acceptable.",
                "Evidence must come before winner labels in the evaluation rationale.",
                "Process artifacts from upstream writers/reviewers are intentionally excluded.",
            ],
        },
        "evidence_paths": {
            "fact_pack_md": _path_string(fact_pack_path),
            "fact_pack_json": _path_string(fact_pack_json_path),
            "candidate_pool": _path_string(candidate_pool_path),
        },
        "candidates": {
            "A": _candidate_payload("A", "control", control_dir),
            "B": _candidate_payload("B", variant_id, variant_dir),
        },
    }
    return packet


def write_comparison_inputs(
    *,
    match_date: str,
    control_root: str | Path = "agent-runs",
    variant_root: str | Path = f"agent-runs-ab/{DEFAULT_VARIANT_ID}",
    variant_id: str = DEFAULT_VARIANT_ID,
) -> dict[str, Path]:
    variant_dir = Path(variant_root) / match_date
    comparison_dir = variant_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    packet = build_comparison_packet(
        match_date=match_date,
        control_root=control_root,
        variant_root=variant_root,
        variant_id=variant_id,
    )
    packet_path = comparison_dir / "comparison_packet.json"
    _write_json(packet_path, packet)
    brief_a_first = comparison_dir / "eval_a_first.md"
    brief_b_first = comparison_dir / "eval_b_first.md"
    brief_a_first.write_text(
        build_evaluator_brief(
            match_date=match_date,
            packet_path=packet_path,
            output_path=comparison_dir / "eval_a_first.json",
            first_label="A",
            second_label="B",
        ),
        encoding="utf-8",
    )
    brief_b_first.write_text(
        build_evaluator_brief(
            match_date=match_date,
            packet_path=packet_path,
            output_path=comparison_dir / "eval_b_first.json",
            first_label="B",
            second_label="A",
        ),
        encoding="utf-8",
    )
    return {
        "packet": packet_path,
        "eval_a_first": brief_a_first,
        "eval_b_first": brief_b_first,
    }


def build_evaluator_brief(
    *,
    match_date: str,
    packet_path: str | Path,
    output_path: str | Path,
    first_label: str,
    second_label: str,
) -> str:
    criteria_lines = "\n".join(
        f"- `{criterion['id']}`: {criterion['description']}" for criterion in CRITERIA
    )
    return f"""# Editorial A/B Comparison Evaluator

You are an independent comparison evaluator for the football-data editorial shadow A/B.

## Task

Compare two already-generated editorial outputs for `{match_date}` and decide whether candidate `{first_label}`, candidate `{second_label}`, or neither is better.

This is a judge task, not an editor task. Do not rewrite selections or copy.

## Required Input

Read this packet first:

`{packet_path}`

The packet contains paths to the fact pack, candidate pool, and final A/B artifacts. Read those referenced files as needed.

Do not read upstream writer/reviewer process artifacts such as `selection_review.json`, `copy_review.json`, or previous comparison outputs. They can bias you. Use only final selection/copy artifacts, deterministic validation summaries, and source evidence.

## Candidate Order

- First candidate: `{first_label}`
- Second candidate: `{second_label}`

Do not prefer a candidate because it appears first. Do not prefer longer copy or longer rationale.

## Criteria

{criteria_lines}

## Edge Cases

- If both candidates are acceptable and the difference is taste-level only, use `tie`.
- If one candidate adds a card, prefer it only when that card materially improves reader value without weakening slate focus.
- If one candidate has better Chinese but a worse slate, separate those criteria and choose the overall winner by impact on public quality.
- If either candidate has an unsupported goal, assist, scoreline, shoot-out, winner, or equaliser claim, factual safety should dominate the verdict.
- If the fact pack is unclear but another allowed packet artifact supports the claim, mark a fact-pack clarity risk rather than a factual error.

## Output

Write exactly this JSON file:

`{output_path}`

Required shape:

```json
{{
  "schema_version": 1,
  "match_date": "{match_date}",
  "candidate_order": ["{first_label}", "{second_label}"],
  "criteria": [
    {{
      "id": "selection_quality",
      "winner": "A",
      "confidence": 0.75,
      "evidence": ["Specific observable evidence before judgment."],
      "rationale": "Why this criterion winner follows from the evidence."
    }}
  ],
  "overall": {{
    "winner": "A",
    "confidence": 0.75,
    "rationale": "Overall judgment with the most important tradeoffs.",
    "key_reasons": ["..."]
  }},
  "risk_flags": [
    {{
      "category": "selection_drift",
      "candidate": "B",
      "severity": "medium",
      "evidence": "..."
    }}
  ],
  "recommended_action": "prefer_a"
}}
```

Valid winner values are `A`, `B`, `tie`, and `needs_human`.
Valid recommended_action values are `prefer_a`, `prefer_b`, `tie`, and `needs_human`.

Return only `DONE`, the overall winner, and one-line rationale after writing the file.
"""


def aggregate_date_comparison(comparison_dir: str | Path) -> dict[str, Any]:
    comparison_dir = Path(comparison_dir)
    first = _load_json(comparison_dir / "eval_a_first.json")
    second = _load_json(comparison_dir / "eval_b_first.json")
    final = resolve_swapped_pairwise(first, second)
    _write_json(comparison_dir / "comparison_verdict.json", final)
    return final


def resolve_swapped_pairwise(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    match_date = str(first.get("match_date") or second.get("match_date") or "")
    first_winner = _canonical_winner(((first.get("overall") or {}).get("winner")))
    second_winner = _canonical_winner(((second.get("overall") or {}).get("winner")))
    if first_winner == second_winner and first_winner in {"A", "B", "tie", "needs_human"}:
        confidence = _average_confidence(first, second)
        verdict = first_winner
        consistency = "consistent"
    else:
        confidence = 0.5
        verdict = "tie"
        consistency = "inconsistent"
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "match_date": match_date,
        "status": "pass",
        "verdict": verdict,
        "recommended_action": _action_for_winner(verdict),
        "confidence": confidence,
        "position_consistency": consistency,
        "pass_winners": {
            "eval_a_first": first_winner,
            "eval_b_first": second_winner,
        },
        "criteria_summary": _criteria_summary(first, second),
        "risk_flags": list(first.get("risk_flags") or []) + list(second.get("risk_flags") or []),
        "rationales": {
            "eval_a_first": ((first.get("overall") or {}).get("rationale") or ""),
            "eval_b_first": ((second.get("overall") or {}).get("rationale") or ""),
        },
    }


def write_overall_summary(
    *,
    dates: list[str],
    variant_root: str | Path = f"agent-runs-ab/{DEFAULT_VARIANT_ID}",
    variant_id: str = DEFAULT_VARIANT_ID,
) -> dict[str, Any]:
    variant_root = Path(variant_root)
    rows = []
    for match_date in dates:
        comparison_dir = variant_root / match_date / "comparison"
        verdict = aggregate_date_comparison(comparison_dir)
        packet = _load_json(comparison_dir / "comparison_packet.json")
        rows.append(
            {
                "match_date": match_date,
                "verdict": verdict["verdict"],
                "recommended_action": verdict["recommended_action"],
                "confidence": verdict["confidence"],
                "position_consistency": verdict["position_consistency"],
                "pass_winners": verdict["pass_winners"],
                "a_selected": _selected_names(packet["candidates"]["A"]["selection_decision"]),
                "b_selected": _selected_names(packet["candidates"]["B"]["selection_decision"]),
                "risk_flag_count": len(verdict.get("risk_flags") or []),
            }
        )
    summary = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "variant_id": variant_id,
        "dates": dates,
        "rows": rows,
        "counts": {
            "prefer_a": sum(1 for row in rows if row["recommended_action"] == "prefer_a"),
            "prefer_b": sum(1 for row in rows if row["recommended_action"] == "prefer_b"),
            "tie": sum(1 for row in rows if row["recommended_action"] == "tie"),
            "needs_human": sum(1 for row in rows if row["recommended_action"] == "needs_human"),
            "inconsistent": sum(1 for row in rows if row["position_consistency"] == "inconsistent"),
        },
    }
    _write_json(variant_root / "comparison_evaluator_summary.json", summary)
    (variant_root / "comparison_evaluator_summary.md").write_text(
        _summary_markdown(summary),
        encoding="utf-8",
    )
    return summary


def _candidate_payload(label: str, run_label: str, run_dir: Path) -> dict[str, Any]:
    selection_path = run_dir / "selection_decision.json"
    copy_path = run_dir / "copy.json"
    return {
        "label": label,
        "run_label": run_label,
        "root": _path_string(run_dir),
        "selection_decision_path": _path_string(selection_path),
        "copy_path": _path_string(copy_path),
        "validation_summary": _validation_summary(run_dir),
        "selection_decision": _load_json(selection_path),
        "copy": _load_json(copy_path),
    }


def _validation_summary(run_dir: Path) -> dict[str, Any]:
    loop_summary = _load_json(run_dir / "editorial_loop_summary.json") if (run_dir / "editorial_loop_summary.json").exists() else {}
    copy_loop = loop_summary.get("copy_loop") if isinstance(loop_summary.get("copy_loop"), dict) else {}
    selected_copy_round = int(copy_loop.get("selected_round") or 1)
    selection_loop = loop_summary.get("selection_loop") if isinstance(loop_summary.get("selection_loop"), dict) else {}
    selected_selection_round = int(selection_loop.get("selected_round") or 1)
    names = {
        "selection": run_dir / "selection_validation.json",
        "copy": run_dir / "copy_validation.json",
        "loop": run_dir / "editorial_loop_validation.json",
        "round_selection": run_dir / "selection_rounds" / f"round_{selected_selection_round}" / "selection_validation.json",
        "round_selection_review": run_dir / "selection_rounds" / f"round_{selected_selection_round}" / "selection_review_validation.json",
        "round_copy": run_dir / "copy_rounds" / f"round_{selected_copy_round}" / "copy_validation.json",
        "round_copy_review": run_dir / "copy_rounds" / f"round_{selected_copy_round}" / "copy_review_validation.json",
    }
    summary: dict[str, Any] = {}
    if selected_selection_round:
        summary["selected_selection_round"] = selected_selection_round
    if selected_copy_round:
        summary["selected_copy_round"] = selected_copy_round
    for key, path in names.items():
        if path.exists():
            payload = _load_json(path)
            summary[key] = {
                "status": payload.get("status"),
                "warnings": payload.get("warnings", []),
            }
    return summary


def _criteria_summary(first: dict[str, Any], second: dict[str, Any]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for pass_name, payload in (("eval_a_first", first), ("eval_b_first", second)):
        for item in payload.get("criteria", []):
            if not isinstance(item, dict):
                continue
            criterion_id = str(item.get("id") or "")
            if not criterion_id:
                continue
            entry = by_id.setdefault(criterion_id, {"id": criterion_id})
            entry[pass_name] = {
                "winner": _canonical_winner(item.get("winner")),
                "confidence": _confidence(item.get("confidence")),
                "rationale": item.get("rationale"),
            }
    return [by_id[key] for key in sorted(by_id)]


def _selected_names(selection_decision: dict[str, Any]) -> list[str]:
    return [
        str(item.get("player_name") or item.get("player_id") or "")
        for item in selection_decision.get("selected", [])
        if isinstance(item, dict)
    ]


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Comparison Evaluator Summary",
        "",
        f"Variant: `{summary['variant_id']}`",
        "",
        "## Counts",
        "",
    ]
    for key, value in summary["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Dates", ""])
    for row in summary["rows"]:
        lines.append(
            "- "
            f"{row['match_date']}: {row['recommended_action']} "
            f"(verdict={row['verdict']}, confidence={row['confidence']:.2f}, "
            f"position={row['position_consistency']})"
        )
    return "\n".join(lines) + "\n"


def _average_confidence(first: dict[str, Any], second: dict[str, Any]) -> float:
    return round(
        (_confidence((first.get("overall") or {}).get("confidence")) + _confidence((second.get("overall") or {}).get("confidence")))
        / 2,
        3,
    )


def _confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _canonical_winner(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "a": "A",
        "candidate_a": "A",
        "candidate a": "A",
        "control": "A",
        "b": "B",
        "candidate_b": "B",
        "candidate b": "B",
        "variant": "B",
        "fresh_subagent": "B",
        "tie": "tie",
        "draw": "tie",
        "needs_human": "needs_human",
        "needs human": "needs_human",
        "human": "needs_human",
    }
    return aliases.get(text, text)


def _action_for_winner(winner: str) -> str:
    if winner == "A":
        return "prefer_a"
    if winner == "B":
        return "prefer_b"
    if winner == "needs_human":
        return "needs_human"
    return "tie"


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"None of these paths exist: {', '.join(str(path) for path in paths)}")


def _path_string(path: Path) -> str:
    return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing comparison input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
