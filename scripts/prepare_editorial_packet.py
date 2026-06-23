#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_local import prepare_editorial_packet


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an editorial packet for local Codex review without publishing choices."
    )
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--config-dir", default="config/editorial", help="Editorial registry directory.")
    parser.add_argument("--experiment", default=None, help="Experiment id. Defaults to production active experiment.")
    parser.add_argument("--out", default="manifests/editorial-v2-run.json", help="Run manifest output.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()

    result = prepare_editorial_packet(
        match_date=args.date,
        db_path=args.db,
        agent_runs_dir=args.agent_runs_dir,
        config_dir=args.config_dir,
        experiment_id=args.experiment,
        run_out_path=args.out,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Prepared editorial packet for {args.date}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
