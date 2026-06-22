import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_run_editorial_queue_cli_skips_publish_when_credentials_are_missing(tmp_path):
    db_path = _queue_db(tmp_path)
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-17")
    run_path = tmp_path / "editorial-run.json"
    queue_path = tmp_path / "editorial-queue.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_queue.py",
            "--db",
            str(db_path),
            "--site-dir",
            str(site_dir),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--out",
            str(run_path),
            "--queue-out",
            str(queue_path),
            "--manifests-dir",
            str(tmp_path / "manifests"),
            "--env",
            str(tmp_path / "missing.env"),
            "--no-research",
        ],
        check=True,
    )

    run = json.loads(run_path.read_text(encoding="utf-8"))
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert run["status"] == "needs_credentials"
    assert run["pending_dates"] == ["2026-06-18"]
    assert queue["status"] == "pending"


def test_run_editorial_queue_cli_with_fake_backend_publishes_pending_date(tmp_path):
    latest_date, previous_date = _latest_and_previous_data_dates()
    site_dir = _site_with_latest_editorial(tmp_path, previous_date)
    run_path = tmp_path / "editorial-run.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_queue.py",
            "--site-dir",
            str(site_dir),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--out",
            str(run_path),
            "--queue-out",
            str(tmp_path / "editorial-queue.json"),
            "--max-dates",
            "1",
            "--no-research",
            "--fake",
        ],
        check=True,
    )

    run = json.loads(run_path.read_text(encoding="utf-8"))
    choices = json.loads(
        (site_dir / "editorial" / latest_date / "choices.json").read_text(
            encoding="utf-8"
        )
    )

    assert run["status"] == "success"
    assert run["published_dates"] == [latest_date]
    assert run["runs"][0]["agent_status"] == "success"
    assert "loop_status" not in run["runs"][0]
    assert choices["match_date"] == latest_date


def test_run_editorial_queue_cli_date_backfill_does_not_replace_latest(tmp_path):
    latest_date, previous_date = _latest_and_previous_data_dates()
    site_dir = _site_with_latest_editorial(tmp_path, latest_date)
    run_path = tmp_path / "editorial-run.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_queue.py",
            "--site-dir",
            str(site_dir),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--out",
            str(run_path),
            "--queue-out",
            str(tmp_path / "editorial-queue.json"),
            "--date",
            previous_date,
            "--no-research",
            "--fake",
        ],
        check=True,
    )

    run = json.loads(run_path.read_text(encoding="utf-8"))
    latest = json.loads((site_dir / "editorial" / "latest.json").read_text(encoding="utf-8"))
    choices = json.loads(
        (site_dir / "editorial" / previous_date / "choices.json").read_text(
            encoding="utf-8"
        )
    )

    assert run["status"] == "success"
    assert run["published_dates"] == [previous_date]
    assert latest["match_date"] == latest_date
    assert choices["match_date"] == previous_date


def _site_with_latest_editorial(tmp_path: Path, match_date: str) -> Path:
    site_dir = tmp_path / f"site-{match_date}"
    editorial_dir = site_dir / "editorial"
    editorial_dir.mkdir(parents=True)
    (editorial_dir / "latest.json").write_text(
        json.dumps({"match_date": match_date}),
        encoding="utf-8",
    )
    return site_dir


def _latest_and_previous_data_dates() -> tuple[str, str]:
    conn = sqlite3.connect("data/latest.sqlite")
    try:
        rows = conn.execute(
            "select distinct match_date from matches order by match_date desc limit 2"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) >= 2
    return str(rows[0][0]), str(rows[1][0])


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
                "insert into matches values (?, ?, ?, ?, ?, ?, ?, ?)",
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
                "insert into source_documents values (?, ?, ?, ?, ?, ?, ?, ?)",
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
