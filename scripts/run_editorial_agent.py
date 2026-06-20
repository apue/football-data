#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_agent import (
    FakeEditorialAgentClient,
    run_editorial_agent,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local/cloud Editor's Choices agent.")
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent run audit directory.")
    parser.add_argument("--env", default=".env.local", help="Local env file.")
    parser.add_argument("--style-dir", default=".agents/editorial-skills", help="Style pack directory.")
    parser.add_argument("--scoring-config", default="config/scoring/v0.3.json")
    parser.add_argument("--no-research", action="store_true", help="Skip Firecrawl research.")
    parser.add_argument("--no-homepage", action="store_true", help="Do not rebuild site/index.html.")
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake agent backend.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()
    client = None
    if args.fake:
        client = FakeEditorialAgentClient()

    result = run_editorial_agent(
        match_date=args.date,
        db_path=args.db,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        manifests_dir=args.manifests_dir,
        agent_runs_dir=args.agent_runs_dir,
        scoring_config_path=args.scoring_config,
        style_dir=args.style_dir,
        env_path=args.env,
        client=client,
        research=not args.no_research,
        rebuild_homepage=not args.no_homepage,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Editorial agent completed {args.date}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
