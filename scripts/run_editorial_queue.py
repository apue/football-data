#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG
from football_data.editorial_queue_runner import run_editorial_queue


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run pending Editor's Choices dates from the editorial queue."
    )
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--style-dir", default=".agents/editorial-skills", help="Style pack directory.")
    parser.add_argument("--env", default=".env.local", help="Local env file.")
    parser.add_argument("--scoring-config", default=DEFAULT_SCORING_CONFIG)
    parser.add_argument(
        "--out",
        default="manifests/editorial-run.json",
        help="Editorial run manifest path.",
    )
    parser.add_argument(
        "--queue-out",
        default="manifests/editorial-queue.json",
        help="Editorial queue manifest path.",
    )
    parser.add_argument("--max-dates", type=int, default=None, help="Limit pending dates processed.")
    parser.add_argument(
        "--date",
        action="append",
        dest="match_dates",
        help="Publish a specific match date. Can be passed multiple times for manual backfills.",
    )
    parser.add_argument("--no-research", action="store_true", help="Skip Firecrawl research.")
    parser.add_argument(
        "--review-feedback",
        default=None,
        help="Optional JSON comments from a local Codex/publication review.",
    )
    parser.add_argument(
        "--max-review-loops",
        type=int,
        default=1,
        help="Maximum publication review/revision loops before final validation.",
    )
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake agent backend.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()

    result = run_editorial_queue(
        db_path=args.db,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        manifests_dir=args.manifests_dir,
        agent_runs_dir=args.agent_runs_dir,
        scoring_config_path=args.scoring_config,
        style_dir=args.style_dir,
        env_path=args.env,
        run_out_path=args.out,
        queue_out_path=args.queue_out,
        research=not args.no_research,
        fake=args.fake,
        max_dates=args.max_dates,
        match_dates=args.match_dates,
        review_feedback_path=args.review_feedback,
        max_review_loops=args.max_review_loops,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "Editorial queue completed: "
            f"{result['status']} pending={','.join(result['pending_dates']) or 'none'}"
        )
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
