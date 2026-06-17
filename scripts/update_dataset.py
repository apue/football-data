#!/usr/bin/env python3
from __future__ import annotations

from football_data.demo import build_demo_site
from football_data.pipeline import update_dataset


def main() -> None:
    records = update_dataset()
    build_demo_site("data/latest.sqlite", "site")
    print(f"Updated data/latest.sqlite from {len(records)} source PDFs")


if __name__ == "__main__":
    main()

