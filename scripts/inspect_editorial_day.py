#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_fact_pack import write_editorial_fact_pack


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic editorial fact pack from a prepared packet."
    )
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--json", action="store_true", help="Print fact-pack JSON.")
    args = parser.parse_args()

    result = write_editorial_fact_pack(
        match_date=args.date,
        db_path=args.db,
        agent_runs_dir=args.agent_runs_dir,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote editorial fact pack for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
