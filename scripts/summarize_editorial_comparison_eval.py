from __future__ import annotations

import argparse
import json

from football_data.editorial_comparison import (
    DEFAULT_VARIANT_ID,
    write_overall_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize editorial A/B comparison evaluator outputs.")
    parser.add_argument("--dates", nargs="+", required=True, help="Local match dates in YYYY-MM-DD.")
    parser.add_argument(
        "--variant-root",
        default=f"agent-runs-ab/{DEFAULT_VARIANT_ID}",
        help="Variant artifact root.",
    )
    parser.add_argument("--variant-id", default=DEFAULT_VARIANT_ID, help="Variant identifier.")
    parser.add_argument("--json", action="store_true", help="Print summary JSON.")
    args = parser.parse_args()

    summary = write_overall_summary(
        dates=args.dates,
        variant_root=args.variant_root,
        variant_id=args.variant_id,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{args.variant_root}/comparison_evaluator_summary.md")


if __name__ == "__main__":
    main()
