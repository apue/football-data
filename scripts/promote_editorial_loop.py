#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_loop import promote_editorial_loop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate bounded editorial selection/copy rounds and promote final artifacts."
    )
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--config-dir", default="config/editorial", help="Editorial registry directory.")
    parser.add_argument("--max-selection-rounds", type=int, default=3, help="Maximum selection review rounds.")
    parser.add_argument("--max-copy-rounds", type=int, default=3, help="Maximum copy review rounds.")
    parser.add_argument("--json", action="store_true", help="Print promotion JSON.")
    args = parser.parse_args()

    result = promote_editorial_loop(
        match_date=args.date,
        agent_runs_dir=args.agent_runs_dir,
        config_dir=args.config_dir,
        max_selection_rounds=args.max_selection_rounds,
        max_copy_rounds=args.max_copy_rounds,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Promoted editorial loop for {args.date}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
