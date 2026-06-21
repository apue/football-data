#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.calibration import (
    build_potm_calibration_report,
    render_potm_calibration_markdown,
)
from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG


def main() -> None:
    parser = argparse.ArgumentParser(description="Build POTM calibration reports.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument(
        "--labels",
        default="calibration/potm-labels.json",
        help="POTM labels JSON path.",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Local match date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--scoring-config",
        default=DEFAULT_SCORING_CONFIG,
        help="Scoring configuration JSON.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Markdown report output path. Defaults to calibration/reports/YYYY-MM-DD.md.",
    )
    parser.add_argument("--json", action="store_true", help="Print report JSON.")
    args = parser.parse_args()

    report = build_potm_calibration_report(
        db_path=args.db,
        labels_path=args.labels,
        match_date=args.date,
        scoring_config_path=args.scoring_config,
    )
    out_path = Path(args.out or f"calibration/reports/{args.date}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_potm_calibration_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote POTM calibration report to {out_path}")


if __name__ == "__main__":
    main()
