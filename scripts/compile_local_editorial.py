#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_local import compile_local_editorial


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile local Codex editorial decision/copy into public artifacts."
    )
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--config-dir", default="config/editorial", help="Editorial registry directory.")
    parser.add_argument("--out", default="manifests/editorial-v2-run.json", help="Run manifest output.")
    parser.add_argument("--no-homepage", action="store_true", help="Do not rebuild homepage.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()

    result = compile_local_editorial(
        match_date=args.date,
        db_path=args.db,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        manifests_dir=args.manifests_dir,
        agent_runs_dir=args.agent_runs_dir,
        config_dir=args.config_dir,
        run_out_path=args.out,
        rebuild_homepage=not args.no_homepage,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Compiled local editorial for {args.date}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
