#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_v2_runner import run_editorial_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Editorial v2 AI rerank workflow.")
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--config-dir", default="config/editorial", help="Editorial registry directory.")
    parser.add_argument("--experiment", default=None, help="Experiment id. Defaults to production active experiment.")
    parser.add_argument("--env", default=".env.local", help="Local env file.")
    parser.add_argument("--out", default="manifests/editorial-v2-run.json", help="Run manifest output.")
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake agent backend.")
    parser.add_argument("--no-research", action="store_true", help="Reserved for compatibility; research is not used in v2 selector input yet.")
    parser.add_argument("--no-homepage", action="store_true", help="Do not rebuild site/index.html.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()

    result = run_editorial_v2(
        match_date=args.date,
        db_path=args.db,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        manifests_dir=args.manifests_dir,
        agent_runs_dir=args.agent_runs_dir,
        config_dir=args.config_dir,
        experiment_id=args.experiment,
        env_path=args.env,
        run_out_path=args.out,
        fake=args.fake,
        research=not args.no_research,
        rebuild_homepage=not args.no_homepage,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Editorial v2 completed {args.date}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
