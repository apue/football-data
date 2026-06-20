import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from football_data.editorial_queue import build_editorial_queue


def test_build_editorial_queue_detects_pending_latest_match_day(tmp_path):
    db_path = _queue_db(tmp_path)
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-17")

    queue = build_editorial_queue(
        db_path=db_path,
        site_dir=site_dir,
        manifests_dir=tmp_path / "manifests",
    )

    assert queue["latest_data_date"] == "2026-06-18"
    assert queue["latest_editorial_date"] == "2026-06-17"
    assert queue["pending_dates"] == ["2026-06-18"]
    assert queue["status"] == "pending"
    assert [item["match_no"] for item in queue["pending_matches"]] == [25, 26, 27, 28]
    assert isinstance(queue["version_updates"], list)


def test_build_editorial_queue_reports_up_to_date_when_editorial_matches_data(tmp_path):
    db_path = _queue_db(tmp_path)
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-18")

    queue = build_editorial_queue(
        db_path=db_path,
        site_dir=site_dir,
        manifests_dir=tmp_path / "manifests",
    )

    assert queue["pending_dates"] == []
    assert queue["status"] == "up_to_date"


def test_build_editorial_queue_detects_stale_editorial_input_hash(tmp_path):
    db_path = _queue_db(tmp_path)
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-18")
    dated_dir = site_dir / "editorial" / "2026-06-18"
    dated_dir.mkdir(parents=True)
    (dated_dir / "choices.json").write_text(
        json.dumps(
            {
                "match_date": "2026-06-18",
                "editorial_input_hash": "stale-hash",
                "choices": [],
            }
        ),
        encoding="utf-8",
    )

    queue = build_editorial_queue(
        db_path=db_path,
        site_dir=site_dir,
        manifests_dir=tmp_path / "manifests",
    )

    assert queue["pending_dates"] == ["2026-06-18"]
    assert queue["pending_items"][0]["reason"] == "editorial_input_changed"
    assert queue["pending_items"][0]["current_input_hash"] != "stale-hash"


def test_check_editorial_queue_cli_writes_json(tmp_path):
    db_path = _queue_db(tmp_path)
    out_path = tmp_path / "editorial-queue.json"
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-17")

    subprocess.run(
        [
            sys.executable,
            "scripts/check_editorial_queue.py",
            "--db",
            str(db_path),
            "--site-dir",
            str(site_dir),
            "--manifests-dir",
            str(tmp_path / "manifests"),
            "--out",
            str(out_path),
        ],
        check=True,
    )

    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved["pending_dates"] == ["2026-06-18"]
    assert saved["latest_editorial_date"] == "2026-06-17"


def _site_with_latest_editorial(tmp_path: Path, match_date: str) -> Path:
    site_dir = tmp_path / f"site-{match_date}"
    editorial_dir = site_dir / "editorial"
    editorial_dir.mkdir(parents=True)
    (editorial_dir / "latest.json").write_text(
        json.dumps({"match_date": match_date}),
        encoding="utf-8",
    )
    return site_dir


def _queue_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "queue.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            create table meta (key text primary key, value text);
            create table matches (
                match_key text primary key,
                source_id text,
                match_no integer,
                match_date text,
                home_team text,
                away_team text,
                home_score integer,
                away_score integer
            );
            create table source_documents (
                source_id text,
                match_key text,
                match_no integer,
                version integer,
                sha256 text,
                file_size integer,
                source_url text,
                active integer
            );
            """
        )
        conn.execute("insert into meta values (?, ?)", ("schema_version", "test"))
        for match_no in range(25, 29):
            match_key = f"m{match_no:02d}"
            source_id = f"test-pmsr-{match_key}"
            conn.execute(
                """
                insert into matches values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_key,
                    source_id,
                    match_no,
                    "2026-06-18",
                    f"Home {match_no}",
                    f"Away {match_no}",
                    match_no % 3,
                    (match_no + 1) % 3,
                ),
            )
            conn.execute(
                """
                insert into source_documents values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    match_key,
                    match_no,
                    1,
                    f"sha-{match_no}",
                    12345 + match_no,
                    f"https://example.test/{source_id}.pdf",
                    1,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path
