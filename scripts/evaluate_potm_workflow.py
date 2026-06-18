#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.calibration import (
    build_potm_calibration_report,
    discover_potm_evidence_candidates,
)
from football_data.firecrawl import search_firecrawl
from football_data.potm_evaluation import (
    evaluate_potm_workflow,
    render_potm_evaluation_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the POTM evidence and calibration workflow.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--labels", default="calibration/potm-labels.json", help="POTM labels JSON.")
    parser.add_argument(
        "--scoring-config",
        default="config/scoring/v0.1.json",
        help="Scoring configuration JSON.",
    )
    parser.add_argument("--evidence", default=None, help="Existing evidence candidate JSON.")
    parser.add_argument("--discover", action="store_true", help="Run Firecrawl discovery first.")
    parser.add_argument("--limit", type=int, default=5, help="Search results per query when discovering.")
    parser.add_argument("--env", default=".env.local", help="Env file with KEYPOOL_URL/KEYPOOL_KEY.")
    parser.add_argument(
        "--evidence-out",
        default=None,
        help="Where to write discovered evidence. Defaults to calibration/evidence/YYYY-MM-DD.json.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="JSON evaluation output. Defaults to calibration/evaluation/YYYY-MM-DD.json.",
    )
    parser.add_argument(
        "--markdown-out",
        default=None,
        help="Markdown output. Defaults to calibration/evaluation/YYYY-MM-DD.md.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    evidence_report = _load_or_discover_evidence(args)
    calibration_report = build_potm_calibration_report(
        db_path=args.db,
        labels_path=args.labels,
        match_date=args.date,
        scoring_config_path=args.scoring_config,
    )
    report = evaluate_potm_workflow(
        evidence_report=evidence_report,
        calibration_report=calibration_report,
    )

    out_path = Path(args.out or f"calibration/evaluation/{args.date}.json")
    markdown_path = Path(args.markdown_out or f"calibration/evaluation/{args.date}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_potm_evaluation_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote POTM workflow evaluation to {out_path}")
        print(f"Wrote POTM workflow evaluation Markdown to {markdown_path}")


def _load_or_discover_evidence(args: argparse.Namespace) -> dict:
    if args.discover:
        search_fn = lambda query, limit: search_firecrawl(
            query=query,
            limit=limit,
            env_path=args.env,
        )
        evidence_report = discover_potm_evidence_candidates(
            db_path=args.db,
            match_date=args.date,
            search_fn=search_fn,
            limit=args.limit,
        )
        evidence_path = Path(args.evidence_out or f"calibration/evidence/{args.date}.json")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return evidence_report

    evidence_path = Path(args.evidence or f"calibration/evidence/{args.date}.json")
    if not evidence_path.exists():
        raise FileNotFoundError(
            f"Missing evidence file: {evidence_path}. Pass --discover to fetch candidates."
        )
    return json.loads(evidence_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
