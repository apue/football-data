from __future__ import annotations

import argparse
import json

from football_data.editorial_comparison import (
    DEFAULT_VARIANT_ID,
    write_comparison_inputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare editorial A/B comparison evaluator packet and briefs.")
    parser.add_argument("--date", required=True, help="Local match date in YYYY-MM-DD.")
    parser.add_argument("--control-root", default="agent-runs", help="Control artifact root.")
    parser.add_argument(
        "--variant-root",
        default=f"agent-runs-ab/{DEFAULT_VARIANT_ID}",
        help="Variant artifact root.",
    )
    parser.add_argument("--variant-id", default=DEFAULT_VARIANT_ID, help="Variant identifier.")
    parser.add_argument("--json", action="store_true", help="Print paths as JSON.")
    args = parser.parse_args()

    paths = write_comparison_inputs(
        match_date=args.date,
        control_root=args.control_root,
        variant_root=args.variant_root,
        variant_id=args.variant_id,
    )
    payload = {key: str(value) for key, value in paths.items()}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
