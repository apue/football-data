from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_data.demo import build_demo_site
from football_data.editorial import render_editorial_markdown_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render an existing Editor's Choices Markdown report to site artifacts."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Local match date in YYYY-MM-DD. Defaults to site/editorial/latest.json.",
    )
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
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
        help="Do not rebuild site/index.html after rendering editorial artifacts.",
    )
    parser.add_argument("--json", action="store_true", help="Print compiled JSON to stdout.")
    args = parser.parse_args()

    match_date = args.date or _latest_editorial_date(Path(args.site_dir))
    compiled = render_editorial_markdown_file(
        match_date=match_date,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
    )
    if not args.skip_homepage:
        build_demo_site(args.db, args.site_dir, args.manifests_dir)
    if args.json:
        print(json.dumps(compiled, ensure_ascii=False, indent=2))
    else:
        print(f"Rendered Editor's Choices Markdown for {compiled['match_date']}.")


def _latest_editorial_date(site_dir: Path) -> str:
    latest_path = site_dir / "editorial" / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError("Missing site/editorial/latest.json; pass --date explicitly.")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    return str(latest["match_date"])


if __name__ == "__main__":
    main()
