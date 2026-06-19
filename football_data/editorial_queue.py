from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG, editorial_input_fingerprint


def build_editorial_queue(
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    manifests_dir: str | Path = "manifests",
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
) -> dict[str, Any]:
    latest_data_date = _latest_data_date(db_path)
    latest_editorial_date = _latest_editorial_date(site_dir)
    pending_items = _pending_items(
        db_path=db_path,
        site_dir=site_dir,
        latest_editorial_date=latest_editorial_date,
        scoring_config_path=scoring_config_path,
    )
    pending_dates = [item["match_date"] for item in pending_items]
    update_events = _load_json(Path(manifests_dir) / "update-events.json")
    latest_run = _load_json(Path(manifests_dir) / "latest-run.json")

    queue = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "pending" if pending_dates else "up_to_date",
        "latest_data_date": latest_data_date,
        "latest_editorial_date": latest_editorial_date,
        "pending_dates": pending_dates,
        "pending_items": pending_items,
        "pending_matches": _matches_for_dates(db_path, pending_dates),
        "new_matches": update_events.get("new_matches", latest_run.get("new_matches", [])),
        "version_updates": update_events.get(
            "version_updates",
            latest_run.get("version_updates", []),
        ),
        "failures": update_events.get("failures", latest_run.get("failures", [])),
        "reason": _reason(pending_items, update_events, latest_run),
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


def _pending_items(
    *,
    db_path: str | Path,
    site_dir: str | Path,
    latest_editorial_date: str | None,
    scoring_config_path: str | Path,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match_date in _data_dates(db_path):
        fingerprint = editorial_input_fingerprint(db_path, match_date, scoring_config_path)
        published_hash = _published_input_hash(site_dir, match_date)
        reason: str | None = None
        if latest_editorial_date is None or match_date > latest_editorial_date:
            reason = "data_date_ahead_of_editorial"
        elif published_hash and published_hash != fingerprint["input_hash"]:
            reason = "editorial_input_changed"

        if reason is not None:
            items.append(
                {
                    "match_date": match_date,
                    "reason": reason,
                    "current_input_hash": fingerprint["input_hash"],
                    "published_input_hash": published_hash,
                    "scoring_version": fingerprint.get("scoring_version"),
                    "source_ids": [
                        source["source_id"]
                        for source in fingerprint.get("source_documents", [])
                    ],
                }
            )
    return items


def _data_dates(db_path: str | Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
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


def _published_input_hash(site_dir: str | Path, match_date: str) -> str | None:
    editorial_dir = Path(site_dir) / "editorial" / match_date
    for filename in ("choices.json", "evidence.json"):
        payload = _load_json(editorial_dir / filename)
        value = payload.get("editorial_input_hash")
        if value:
            return str(value)
    return None


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
    pending_items: list[dict[str, Any]],
    update_events: dict[str, Any],
    latest_run: dict[str, Any],
) -> str:
    if not pending_items:
        return "editorial_up_to_date"
    new_matches = update_events.get("new_matches") or latest_run.get("new_matches") or []
    version_updates = update_events.get("version_updates") or latest_run.get("version_updates") or []
    if any(item.get("reason") == "editorial_input_changed" for item in pending_items):
        return "editorial_input_changed"
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
