import json
import re
import subprocess
import sys
from pathlib import Path

from football_data.editorial import build_editorial_report, write_editorial_artifacts


def test_build_editorial_report_for_match_day():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")

    assert report["schema_version"] == 1
    assert report["match_date"] == "2026-06-16"
    assert report["scoring_version"] == "v0.1"
    assert report["matches"]
    assert report["choices"]

    first_choice = report["choices"][0]
    assert first_choice["award_type"] == "player_of_the_day"
    assert first_choice["player_name"]
    assert first_choice["score"] > 0
    assert 1 <= len(first_choice["evidence_chips"]["en"]) <= 4
    assert 1 <= len(first_choice["evidence_chips"]["zh"]) <= 4
    assert first_choice["narrative"]["en"]["title"]
    assert first_choice["narrative"]["en"]["body"]
    assert first_choice["narrative"]["zh"]["title"]
    assert first_choice["narrative"]["zh"]["body"]

    digit_count = len(re.findall(r"\d", first_choice["narrative"]["en"]["body"]))
    assert digit_count <= 6


def test_write_editorial_artifacts(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")

    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )

    latest = tmp_path / "site" / "editorial" / "latest.json"
    dated_json = tmp_path / "site" / "editorial" / "2026-06-16" / "choices.json"
    dated_html = tmp_path / "site" / "editorial" / "2026-06-16" / "index.html"
    report_md = tmp_path / "reports" / "editorial" / "2026-06-16.md"

    assert latest.exists()
    assert dated_json.exists()
    assert dated_html.exists()
    assert report_md.exists()

    saved = json.loads(latest.read_text(encoding="utf-8"))
    html = dated_html.read_text(encoding="utf-8")
    markdown = report_md.read_text(encoding="utf-8")
    assert saved["match_date"] == "2026-06-16"
    assert "Editor's Choices" in html
    assert "Editor&apos;s Choices" not in html
    assert "## English" in markdown
    assert "## 中文" in markdown


def test_generate_editorial_cli_rebuilds_homepage(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "scripts/generate_editorial.py",
            "--date",
            "2026-06-16",
            "--site-dir",
            str(tmp_path / "site"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
        check=True,
    )

    homepage = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "Editor's Choices" in homepage
    assert "Top 5 Attacking Threats" in homepage
