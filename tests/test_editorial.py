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
    assert report["scoring_version"] == "v0.2"
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


def test_editorial_impact_layer_surfaces_decisive_goal_players():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-17")

    players_of_day = [
        choice
        for choice in report["choices"]
        if choice["award_type"] == "player_of_the_day"
    ]
    player_names = [choice["player_name"] for choice in players_of_day]

    assert "Caleb YIRENKYI" in player_names
    assert "Luis DIAZ" in player_names

    caleb = next(choice for choice in players_of_day if choice["player_name"] == "Caleb YIRENKYI")
    assert caleb["role_scores"]["impact"] >= 40
    assert any(
        component["metric"] == "late_match_winning_goal"
        for component in caleb["score_components"]
    )


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
    zh_fact_bank_json = tmp_path / "site" / "editorial" / "2026-06-16" / "fact_bank.zh.json"
    zh_brief_json = tmp_path / "site" / "editorial" / "2026-06-16" / "brief.zh.json"
    en_brief_json = tmp_path / "site" / "editorial" / "2026-06-16" / "brief.en.json"
    dated_html = tmp_path / "site" / "editorial" / "2026-06-16" / "index.html"
    report_md = tmp_path / "reports" / "editorial" / "2026-06-16.md"

    assert latest.exists()
    assert dated_json.exists()
    assert evidence_json.exists()
    assert zh_fact_bank_json.exists()
    assert zh_brief_json.exists()
    assert en_brief_json.exists()
    assert dated_html.exists()
    assert report_md.exists()

    saved = json.loads(latest.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_json.read_text(encoding="utf-8"))
    zh_fact_bank = json.loads(zh_fact_bank_json.read_text(encoding="utf-8"))
    zh_brief = json.loads(zh_brief_json.read_text(encoding="utf-8"))
    en_brief = json.loads(en_brief_json.read_text(encoding="utf-8"))
    html = dated_html.read_text(encoding="utf-8")
    markdown = report_md.read_text(encoding="utf-8")
    first_choice = saved["choices"][0]

    assert saved["schema_version"] == 2
    assert saved["match_date"] == "2026-06-16"
    assert saved["source_markdown_path"] == "reports/editorial/2026-06-16.md"
    assert "narrative" not in first_choice
    assert "score" not in first_choice
    assert "primary_score" not in first_choice
    assert "role_scores" not in first_choice
    assert "score_components" not in first_choice
    assert "content" in first_choice
    assert first_choice["content"]["en"]["title"]
    assert first_choice["content"]["en"]["html"].startswith("<p>")
    assert "**" not in first_choice["content"]["en"]["html"]
    assert "markdown" not in first_choice["content"]["en"]
    assert "narrative" not in evidence["choices"][0]
    assert "draft" not in evidence["choices"][0]
    assert zh_fact_bank["language"] == "zh"
    assert zh_fact_bank["editorial_process"] == "from_scratch_chinese_sports_editor"
    assert zh_fact_bank["choices"][0]["player_name"] == "梅西"
    assert zh_fact_bank["choices"][0]["match_scoreline"] == "阿根廷 3-0 阿尔及利亚"
    assert any("帽子戏法" in fact for fact in zh_fact_bank["choices"][0]["facts"])
    assert any("4 次射正" in fact for fact in zh_fact_bank["choices"][0]["facts"])
    assert any("制胜进球" in fact for fact in zh_fact_bank["choices"][0]["facts"])
    progression_choice = next(
        choice
        for choice in zh_fact_bank["choices"]
        if choice["award_type"] == "progression_pick"
    )
    assert progression_choice["match_scoreline"] == "阿尔及利亚 0-3 阿根廷"
    assert "英文稿" in zh_fact_bank["forbidden_inputs"]
    fact_bank_text = json.dumps(zh_fact_bank, ensure_ascii=False)
    assert "why_selected" not in fact_bank_text
    assert "title_candidates" not in fact_bank_text
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
    assert "🇦🇷 Lionel MESSI" in html
    assert "🇦🇷 Argentina vs 🇩🇿 Algeria" in html
    assert "<span>score</span>" not in html
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


def test_zh_fact_bank_uses_chinese_team_names_for_latest_loaded_day(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-17")
    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )

    fact_bank = json.loads(
        (
            tmp_path
            / "site"
            / "editorial"
            / "2026-06-17"
            / "fact_bank.zh.json"
        ).read_text(encoding="utf-8")
    )
    text = json.dumps(fact_bank, ensure_ascii=False)

    assert "巴拿马" in text
    assert "加纳" in text
    assert "葡萄牙" in text
    assert "刚果（金）" in text
    assert "Panama" not in text
    assert "Ghana" not in text
    assert "Portugal" not in text
    assert "Congo DR" not in text


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
    assert "Player Leaderboards" in homepage
    assert "Most Shots on Target" in homepage
    assert "射正最多" in homepage


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
