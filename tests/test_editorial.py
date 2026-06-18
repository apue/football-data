import json
import re
import subprocess
import sys
from pathlib import Path

from football_data.editorial import (
    build_editorial_report,
    compile_editorial_markdown,
    write_editorial_artifacts,
)


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
    assert "narrative" not in first_choice
    assert first_choice["draft"]["en"]["title"]
    assert first_choice["draft"]["en"]["body"]
    assert first_choice["draft"]["zh"]["title"]
    assert first_choice["draft"]["zh"]["body"]

    digit_count = len(re.findall(r"\d", first_choice["draft"]["en"]["body"]))
    assert digit_count <= 10


def test_write_editorial_artifacts(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")

    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )

    latest = tmp_path / "site" / "editorial" / "latest.json"
    dated_json = tmp_path / "site" / "editorial" / "2026-06-16" / "choices.json"
    evidence_json = tmp_path / "site" / "editorial" / "2026-06-16" / "evidence.json"
    zh_brief_json = tmp_path / "site" / "editorial" / "2026-06-16" / "brief.zh.json"
    en_brief_json = tmp_path / "site" / "editorial" / "2026-06-16" / "brief.en.json"
    dated_html = tmp_path / "site" / "editorial" / "2026-06-16" / "index.html"
    report_md = tmp_path / "reports" / "editorial" / "2026-06-16.md"

    assert latest.exists()
    assert dated_json.exists()
    assert evidence_json.exists()
    assert zh_brief_json.exists()
    assert en_brief_json.exists()
    assert dated_html.exists()
    assert report_md.exists()

    saved = json.loads(latest.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_json.read_text(encoding="utf-8"))
    zh_brief = json.loads(zh_brief_json.read_text(encoding="utf-8"))
    en_brief = json.loads(en_brief_json.read_text(encoding="utf-8"))
    html = dated_html.read_text(encoding="utf-8")
    markdown = report_md.read_text(encoding="utf-8")
    first_choice = saved["choices"][0]

    assert saved["schema_version"] == 2
    assert saved["match_date"] == "2026-06-16"
    assert saved["source_markdown_path"] == "reports/editorial/2026-06-16.md"
    assert "narrative" not in first_choice
    assert "content" in first_choice
    assert first_choice["content"]["en"]["title"]
    assert first_choice["content"]["en"]["html"].startswith("<p>")
    assert "**" not in first_choice["content"]["en"]["html"]
    assert "markdown" not in first_choice["content"]["en"]
    assert "narrative" not in evidence["choices"][0]
    assert "draft" not in evidence["choices"][0]
    assert zh_brief["language"] == "zh"
    assert en_brief["language"] == "en"
    assert zh_brief["choices"][0]["player_name"] == "梅西"
    assert zh_brief["choices"][0]["team"] == "阿根廷"
    assert zh_brief["choices"][0]["opponent"] == "阿尔及利亚"
    assert "title_candidates" in zh_brief["choices"][0]
    assert "帽子戏法就是答案" in zh_brief["choices"][0]["title_candidates"]
    assert "Lionel" not in json.dumps(zh_brief, ensure_ascii=False)
    assert "hat-trick" not in json.dumps(zh_brief, ensure_ascii=False)
    assert en_brief["choices"][0]["player_name"] == "Lionel MESSI"
    assert "帽子戏法" not in json.dumps(en_brief, ensure_ascii=False)
    assert "Editor's Choices" in html
    assert "Editor&apos;s Choices" not in html
    assert "## Choices" in markdown
    assert "#### English" in markdown
    assert "#### 中文" in markdown
    assert "Draft brief" in markdown
    assert "中文编辑草稿" in markdown


def test_generated_editorial_markdown_is_a_draft_not_final_copy(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")
    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )

    markdown = (tmp_path / "reports" / "editorial" / "2026-06-16.md").read_text(
        encoding="utf-8"
    )
    awkward_phrases = [
        "今天最清楚的答案",
        "不用复杂包装",
        "比赛叙事",
        "给了这一天一个很直接的进攻答案",
        "把防线往身后拉",
        "最有说服力的一场表现",
        "中场推进很多时候就是靠这些动作续上",
        "进攻节奏很多时候就是靠这些小动作续上的",
        "PMSR 里",
        "PMSR 的",
        "数据画像",
        "不是最容易被写进标题的人",
        "这反而是他入选的理由",
        "单一片段",
        "made the headline and the data agree",
        "PMSR profile",
        "this dataset is built to surface",
        "not just one highlight",
        "normal recap can flatten",
    ]
    for phrase in awkward_phrases:
        assert phrase not in markdown

    assert "Draft brief" in markdown
    assert "中文编辑草稿" in markdown
    assert "Use this as evidence, then rewrite the English and Chinese copy separately." in markdown


def test_compile_editorial_markdown_renders_edited_copy(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")
    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )
    evidence = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-16" / "evidence.json").read_text(
            encoding="utf-8"
        )
    )
    markdown = (
        tmp_path / "reports" / "editorial" / "2026-06-16.md"
    ).read_text(encoding="utf-8")
    markdown = markdown.replace("Draft brief - Player of the Day", "A human-edited title", 1)
    markdown = markdown.replace(
        "Use this as evidence, then rewrite the English and Chinese copy separately",
        "Lionel MESSI turned the day into a clean editorial call",
        1,
    )

    compiled = compile_editorial_markdown(
        evidence,
        markdown,
        source_markdown_path="reports/editorial/2026-06-16.md",
    )

    first_choice = compiled["choices"][0]
    assert compiled["schema_version"] == 2
    assert first_choice["content"]["en"]["title"] == "A human-edited title"
    assert "clean editorial call" in first_choice["content"]["en"]["html"]
    assert "**" not in first_choice["content"]["en"]["html"]
    assert "markdown" not in first_choice["content"]["en"]


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


def test_render_editorial_cli_compiles_existing_markdown(tmp_path):
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
    report_md = tmp_path / "reports" / "editorial" / "2026-06-16.md"
    report_md.write_text(
        report_md.read_text(encoding="utf-8").replace(
            "Draft brief - Player of the Day",
            "A rendered Markdown title",
            1,
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/render_editorial.py",
            "--date",
            "2026-06-16",
            "--site-dir",
            str(tmp_path / "site"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
        check=True,
    )

    compiled = json.loads(
        (tmp_path / "site" / "editorial" / "latest.json").read_text(encoding="utf-8")
    )
    homepage = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert compiled["choices"][0]["content"]["en"]["title"] == "A rendered Markdown title"
    assert "A rendered Markdown title" in homepage
