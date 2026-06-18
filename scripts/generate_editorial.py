from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.demo import build_demo_site
from football_data.editorial import build_editorial_report, write_editorial_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Editor's Choices artifacts.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument(
        "--date",
        default=None,
        help="Local match date in YYYY-MM-DD. Defaults to latest match date in the database.",
    )
    parser.add_argument(
        "--scoring-config",
        default="config/scoring/v0.1.json",
        help="Scoring configuration JSON.",
    )
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument(
        "--manifests-dir",
        default="manifests",
        help="Manifests directory used when rebuilding the homepage.",
    )
    parser.add_argument(
        "--skip-homepage",
        action="store_true",
        help="Do not rebuild site/index.html after writing editorial artifacts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print generated report JSON to stdout.",
    )
    args = parser.parse_args()

    report = build_editorial_report(
        args.db,
        match_date=args.date,
        scoring_config_path=args.scoring_config,
    )
    write_editorial_artifacts(
        report,
        site_dir=Path(args.site_dir),
        reports_dir=Path(args.reports_dir),
    )
    if not args.skip_homepage:
        build_demo_site(args.db, args.site_dir, args.manifests_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "Generated Editor's Choices for "
            f"{report['match_date']} with {len(report['choices'])} choices."
        )


if __name__ == "__main__":
    main()
