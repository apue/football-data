import json
import subprocess
import sys
from pathlib import Path

from football_data.editorial_loop import run_editorial_loop


def test_editorial_loop_writes_review_repair_validate_iterations(tmp_path):
    result = run_editorial_loop(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        agent_runs_dir=tmp_path / "agent-runs",
        max_iterations=3,
    )

    final_path = tmp_path / "agent-runs" / "2026-06-18" / "final.json"
    iteration_path = tmp_path / "agent-runs" / "2026-06-18" / "iteration-001"

    assert result["status"] == "published"
    assert result["decision"] == "publish"
    assert final_path.exists()
    assert (iteration_path / "state.json").exists()
    assert (iteration_path / "selection_review.json").exists()
    assert (iteration_path / "copy_review.zh.json").exists()
    assert (iteration_path / "validation.json").exists()
    assert (iteration_path / "decision.json").exists()

    final = json.loads(final_path.read_text(encoding="utf-8"))
    choices = {choice["award_type"]: choice for choice in final["choices"]}

    assert final["orchestrator"]["pattern"] == "review_repair_validate"
    assert choices["hidden_gem"]["player_name"] == "LEE Gihyuk"
    assert "defensive_pick" not in choices


def test_run_editorial_loop_cli_writes_final_audit(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_loop.py",
            "--date",
            "2026-06-18",
            "--site-dir",
            str(tmp_path / "site"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--agent-runs-dir",
            str(tmp_path / "agent-runs"),
            "--skip-homepage",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    final = json.loads(
        (tmp_path / "agent-runs" / "2026-06-18" / "final.json").read_text(encoding="utf-8")
    )

    assert payload["status"] == "published"
    assert final["decision"] == "publish"
    assert final["choices"][-1]["player_name"] == "LEE Gihyuk"


def test_editorial_loop_can_validate_existing_markdown_without_overwriting(tmp_path):
    run_editorial_loop(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        agent_runs_dir=tmp_path / "agent-runs",
        max_iterations=3,
    )
    markdown_path = tmp_path / "reports" / "editorial" / "2026-06-18.md"
    markdown_path.write_text(
        markdown_path.read_text(encoding="utf-8").replace(
            "Draft brief - Player of the Day",
            "Human edited title",
            1,
        ),
        encoding="utf-8",
    )

    result = run_editorial_loop(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        agent_runs_dir=tmp_path / "agent-runs",
        max_iterations=3,
        use_existing_markdown=True,
    )

    assert result["status"] == "published"
    assert "Human edited title" in markdown_path.read_text(encoding="utf-8")
    choices = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-18" / "choices.json").read_text(
            encoding="utf-8"
        )
    )
    assert choices["choices"][0]["content"]["en"]["title"] == "Human edited title"
