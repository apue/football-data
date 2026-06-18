#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from football_data.firecrawl import search_firecrawl


def main() -> None:
    parser = argparse.ArgumentParser(description="Search external POTM evidence with Firecrawl.")
    parser.add_argument("query", help="Search query.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum search results.")
    parser.add_argument("--env", default=".env.local", help="Env file with KEYPOOL_URL/KEYPOOL_KEY.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()

    results = search_firecrawl(query=args.query, limit=args.limit, env_path=args.env)
    if args.json:
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
        return
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result['title']}")
        print(f"   {result['url']}")
        if result["description"]:
            print(f"   {result['description']}")


if __name__ == "__main__":
    main()
