#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.calibration import discover_potm_evidence_candidates
from football_data.firecrawl import search_firecrawl


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover POTM evidence candidates with Firecrawl.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--limit", type=int, default=5, help="Search results per query.")
    parser.add_argument("--env", default=".env.local", help="Env file with KEYPOOL_URL/KEYPOOL_KEY.")
    parser.add_argument(
        "--out",
        default=None,
        help="JSON output path. Defaults to calibration/evidence/YYYY-MM-DD.json.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write generated queries only.")
    args = parser.parse_args()

    search_fn = None
    if not args.dry_run:
        search_fn = lambda query, limit: search_firecrawl(
            query=query,
            limit=limit,
            env_path=args.env,
        )

    report = discover_potm_evidence_candidates(
        db_path=args.db,
        match_date=args.date,
        search_fn=search_fn,
        limit=args.limit,
    )
    out_path = Path(args.out or f"calibration/evidence/{args.date}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote POTM evidence candidates to {out_path}")


if __name__ == "__main__":
    main()
