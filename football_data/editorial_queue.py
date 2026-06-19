from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_editorial_queue(
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    manifests_dir: str | Path = "manifests",
) -> dict[str, Any]:
    latest_data_date = _latest_data_date(db_path)
    latest_editorial_date = _latest_editorial_date(site_dir)
    pending_dates = _pending_dates(db_path, latest_editorial_date)
    update_events = _load_json(Path(manifests_dir) / "update-events.json")
    latest_run = _load_json(Path(manifests_dir) / "latest-run.json")

    queue = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "pending" if pending_dates else "up_to_date",
        "latest_data_date": latest_data_date,
        "latest_editorial_date": latest_editorial_date,
        "pending_dates": pending_dates,
        "pending_matches": _matches_for_dates(db_path, pending_dates),
        "new_matches": update_events.get("new_matches", latest_run.get("new_matches", [])),
        "version_updates": update_events.get(
            "version_updates",
            latest_run.get("version_updates", []),
        ),
        "failures": update_events.get("failures", latest_run.get("failures", [])),
        "reason": _reason(pending_dates, update_events, latest_run),
    }
    return queue


def write_editorial_queue(
    queue: dict[str, Any],
    out_path: str | Path = "manifests/editorial-queue.json",
) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _latest_data_date(db_path: str | Path) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("select max(match_date) from matches").fetchone()
    finally:
        conn.close()
    return str(row[0]) if row and row[0] else None


def _latest_editorial_date(site_dir: str | Path) -> str | None:
    path = Path(site_dir) / "editorial" / "latest.json"
    if not path.exists():
        return None
    payload = _load_json(path)
    value = payload.get("match_date")
    return str(value) if value else None


def _pending_dates(db_path: str | Path, latest_editorial_date: str | None) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        if latest_editorial_date:
            rows = conn.execute(
                """
                select distinct match_date
                from matches
                where match_date > ?
                order by match_date
                """,
                (latest_editorial_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select distinct match_date
                from matches
                order by match_date
                """
            ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _matches_for_dates(db_path: str | Path, match_dates: list[str]) -> list[dict[str, Any]]:
    if not match_dates:
        return []
    placeholders = ",".join("?" for _ in match_dates)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            select match_no, match_key, match_date, home_team, away_team, home_score, away_score
            from matches
            where match_date in ({placeholders})
            order by match_date, match_no
            """,
            match_dates,
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _reason(
    pending_dates: list[str],
    update_events: dict[str, Any],
    latest_run: dict[str, Any],
) -> str:
    if not pending_dates:
        return "editorial_up_to_date"
    new_matches = update_events.get("new_matches") or latest_run.get("new_matches") or []
    version_updates = update_events.get("version_updates") or latest_run.get("version_updates") or []
    if new_matches and version_updates:
        return "new_matches_and_version_updates"
    if new_matches:
        return "new_matches"
    if version_updates:
        return "version_updates"
    return "data_date_ahead_of_editorial"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
