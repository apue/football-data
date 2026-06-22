#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.fifa_timeline import backfill_fifa_timelines


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill FIFA public timeline events.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument(
        "--manifest",
        default="manifests/timeline-run.json",
        help="Path for the backfill summary JSON.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on supplemental API errors.")
    args = parser.parse_args()

    summary = backfill_fifa_timelines(args.db, raise_on_error=args.strict)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
