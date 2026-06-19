import json
import subprocess
import sys
from pathlib import Path


def test_run_editorial_queue_cli_skips_publish_when_credentials_are_missing(tmp_path):
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-17")
    run_path = tmp_path / "editorial-run.json"
    queue_path = tmp_path / "editorial-queue.json"

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
            str(queue_path),
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
    site_dir = _site_with_latest_editorial(tmp_path, "2026-06-17")
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
            "--no-research",
            "--fake",
        ],
        check=True,
    )

    run = json.loads(run_path.read_text(encoding="utf-8"))
    choices = json.loads(
        (site_dir / "editorial" / "2026-06-18" / "choices.json").read_text(
            encoding="utf-8"
        )
    )

    assert run["status"] == "success"
    assert run["published_dates"] == ["2026-06-18"]
    assert choices["match_date"] == "2026-06-18"


def _site_with_latest_editorial(tmp_path: Path, match_date: str) -> Path:
    site_dir = tmp_path / f"site-{match_date}"
    editorial_dir = site_dir / "editorial"
    editorial_dir.mkdir(parents=True)
    (editorial_dir / "latest.json").write_text(
        json.dumps({"match_date": match_date}),
        encoding="utf-8",
    )
    return site_dir
