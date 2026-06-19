#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_loop import run_editorial_loop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Editor's Choices review-repair-validate loop."
    )
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Loop audit directory.")
    parser.add_argument("--scoring-config", default="config/scoring/v0.3.json")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum loop iterations before requiring human review.",
    )
    parser.add_argument(
        "--skip-homepage",
        action="store_true",
        help="Do not rebuild site/index.html after a publish decision.",
    )
    parser.add_argument(
        "--use-existing-markdown",
        action="store_true",
        help="Validate and compile an existing reports/editorial/YYYY-MM-DD.md without overwriting it.",
    )
    parser.add_argument("--json", action="store_true", help="Print final audit JSON.")
    args = parser.parse_args()

    result = run_editorial_loop(
        match_date=args.date,
        db_path=args.db,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        manifests_dir=args.manifests_dir,
        agent_runs_dir=args.agent_runs_dir,
        scoring_config_path=args.scoring_config,
        max_iterations=args.max_iterations,
        rebuild_homepage=not args.skip_homepage,
        use_existing_markdown=args.use_existing_markdown,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "Editorial loop completed "
            f"{args.date}: {result['status']} ({result['decision']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
