#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG
from football_data.editorial_queue import build_editorial_queue, write_editorial_queue


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Editor's Choices pending queue.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--scoring-config", default=DEFAULT_SCORING_CONFIG)
    parser.add_argument(
        "--out",
        default="manifests/editorial-queue.json",
        help="Queue JSON output path.",
    )
    parser.add_argument("--json", action="store_true", help="Print queue JSON to stdout.")
    args = parser.parse_args()

    queue = build_editorial_queue(
        db_path=args.db,
        site_dir=args.site_dir,
        manifests_dir=args.manifests_dir,
        scoring_config_path=args.scoring_config,
    )
    write_editorial_queue(queue, args.out)
    if args.json:
        print(json.dumps(queue, ensure_ascii=False, indent=2))
    else:
        pending = ", ".join(queue["pending_dates"]) or "none"
        print(f"Editorial queue status: {queue['status']} pending={pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
