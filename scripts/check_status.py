#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FIFA PMSR dataset update status.")
    parser.add_argument("--repo", default="apue/football-data")
    parser.add_argument("--workflow", default="update.yml")
    parser.add_argument("--db", default="data/latest.sqlite")
    parser.add_argument("--manifests", default="manifests")
    parser.add_argument("--pages-url", default="https://apue.github.io/football-data/")
    args = parser.parse_args()

    status = {
        "github_actions": _latest_run(args.repo, args.workflow),
        "latest_run": _load_json(Path(args.manifests) / "latest-run.json"),
        "sqlite": _sqlite_counts(Path(args.db)),
        "pages": _pages_health(args.pages_url),
    }
    print(json.dumps(status, indent=2))
    return 1 if _has_problem(status) else 0


def _latest_run(repo: str, workflow: str) -> dict[str, object]:
    if shutil.which("gh") is None:
        return {"status": "unknown", "message": "gh CLI not found"}
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--limit",
        "1",
        "--json",
        "databaseId,status,conclusion,event,displayTitle,createdAt,url",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return {"status": "unknown", "message": result.stderr.strip()}
    runs = json.loads(result.stdout)
    return runs[0] if runs else {"status": "missing", "message": "No workflow runs found"}


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _sqlite_counts(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    conn = sqlite3.connect(path)
    try:
        return {
            "status": "ok",
            "matches": _count(conn, "matches"),
            "source_documents": _count(conn, "source_documents"),
            "shots": _count(conn, "shots"),
            "player_physical_stats": _count(conn, "player_physical_stats"),
        }
    finally:
        conn.close()


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"select count(*) from {table}").fetchone()[0])


def _pages_health(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {
            "status": "ok",
            "http_status": response.status,
            "url": url,
            "has_demo_title": "FIFA PMSR Data Demo" in body,
            "has_update_summary": "Update Summary" in body,
        }
    except Exception as exc:
        return {"status": "failed", "url": url, "message": str(exc)}


def _has_problem(status: dict[str, object]) -> bool:
    actions = status["github_actions"]
    latest_run = status["latest_run"]
    sqlite = status["sqlite"]
    pages = status["pages"]
    if isinstance(actions, dict) and actions.get("conclusion") not in (None, "success"):
        return True
    if isinstance(latest_run, dict) and latest_run.get("status") == "failed":
        return True
    if isinstance(sqlite, dict) and sqlite.get("status") != "ok":
        return True
    if isinstance(pages, dict) and pages.get("status") != "ok":
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
