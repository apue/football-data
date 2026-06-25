import json
import re
import sqlite3
from pathlib import Path

from football_data.editorial import (
    _load_scoring_config,
    _player_rows_for_date,
    _score_player,
    build_editorial_report,
    compile_editorial_markdown,
    write_editorial_artifacts,
)


def test_build_editorial_report_for_match_day():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-16")

    assert report["schema_version"] == 1
    assert report["match_date"] == "2026-06-16"
    assert report["scoring_version"] == "v0.4"
    assert report["matches"]
    assert report["match_flows"]
    assert report["choices"]

    first_choice = report["choices"][0]
    assert first_choice["award_type"] == "player_of_the_day"
    assert "player_of_the_day" in first_choice["award_types"]
    assert first_choice["badges"][0]["label"]["en"] == "Player of the Day"
    assert first_choice["player_name"]
    assert first_choice["score"] > 0
    assert 1 <= len(first_choice["evidence_chips"]["en"]) <= 4
    assert 1 <= len(first_choice["evidence_chips"]["zh"]) <= 4
    assert "narrative" not in first_choice
    assert first_choice["draft"]["en"]["title"]
    assert first_choice["draft"]["en"]["body"]
    assert "zh" not in first_choice["draft"]

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

    luis = next(choice for choice in players_of_day if choice["player_name"] == "Luis DIAZ")
    assert luis["metrics"]["assists"] == 1
    assert any(component["metric"] == "assists" for component in luis["score_components"])


def test_editorial_headline_impact_surfaces_goal_stories_for_latest_day():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-18")
    choices_by_name = {choice["player_name"]: choice for choice in report["choices"]}

    assert "Jonathan DAVID" in choices_by_name
    assert "Luis ROMO" in choices_by_name
    assert "Johan MANZAMBI" in choices_by_name

    david = choices_by_name["Jonathan DAVID"]
    assert david["award_type"] == "player_of_the_day"
    assert david["role_scores"]["impact"] >= 20
    assert any(component["metric"] == "hat_trick" for component in david["score_components"])

    romo = choices_by_name["Luis ROMO"]
    assert any(component["metric"] == "only_goal_winner" for component in romo["score_components"])

    manzambi = choices_by_name["Johan MANZAMBI"]
    assert any(component["metric"] == "substitute_brace" for component in manzambi["score_components"])


def test_editorial_scoring_ignores_goal_prevented_rows_in_existing_database():
    conn = sqlite3.connect("data/latest.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        scoring = _load_scoring_config("config/scoring/v0.3.json")
        players = [
            _score_player(row, scoring)
            for row in _player_rows_for_date(conn, "2026-06-18")
        ]
    finally:
        conn.close()

    tajon = next(
        player
        for player in players
        if player["match_no"] == 27 and player["player_name"] == "Tajon BUCHANAN"
    )

    assert tajon["goals"] == 0
    assert tajon["role_scores"]["impact"] == 0


def test_editorial_candidate_goals_prefer_official_timeline_totals():
    conn = sqlite3.connect("data/latest.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        haaland = next(
            row
            for row in _player_rows_for_date(conn, "2026-06-16")
            if row["match_no"] == 18 and row["player_name"] == "Erling HAALAND"
        )
    finally:
        conn.close()

    assert haaland["goals"] == 2
    assert haaland["goal_involvements"] == 2
    assert haaland["brace"] == 1


def test_editorial_selection_gate_rebalances_contextual_risks():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-18")
    choices_by_award = {choice["award_type"]: choice for choice in report["choices"]}
    player_names = [choice["player_name"] for choice in report["choices"]]

    assert report["selection_review"]["status"] == "publishable"
    assert not [
        alert
        for alert in report["selection_review"]["alerts"]
        if alert["level"] == "high"
    ]
    assert [iteration["status"] for iteration in report["selection_review"]["iterations"]] == [
        "needs_adjustment",
        "publishable",
    ]

    assert "Jonathan DAVID" in player_names
    assert "Johan MANZAMBI" in player_names
    assert "Luis ROMO" in player_names
    assert "Nikola KATIC" not in player_names
    assert "Oswin APPOLLIS" not in player_names
    assert "Ladislav KREJCI" not in player_names

    defensive_pick = choices_by_award["defensive_pick"]
    assert defensive_pick["team"] == "Korea Republic"
    assert defensive_pick["player_name"] == "LEE Gihyuk"
    assert "hidden_gem" not in choices_by_award


def test_latest_day_allows_keeper_watch_and_optional_hidden_gem():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-21")
    choices_by_award = {choice["award_type"]: choice for choice in report["choices"]}
    choices_by_name = {choice["player_name"]: choice for choice in report["choices"]}

    assert "MOSTAFA ZICO" not in choices_by_name
    assert [choice["team"] for choice in report["choices"]].count("Egypt") == 2
    assert choices_by_name["MOHAMED SALAH"]["award_types"] == [
        "player_of_the_day",
        "impact_pick",
    ]

    progression = choices_by_award["progression_pick"]
    assert progression["award_label"]["en"] == "Progression Engine"
    assert progression["award_label"]["zh"] == "进攻发动机"

    defensive = choices_by_award["defensive_pick"]
    assert defensive["player_name"] == "PICO LOPES"
    assert defensive["team"] == "Cabo Verde"
    assert defensive["award_types"] == ["defensive_pick", "hidden_gem"]

    keeper = choices_by_award["goalkeeper_watch"]
    assert keeper["player_name"] == "Alireza BEIRANVAND"
    assert keeper["team"] == "IR Iran"
    assert keeper["metrics"]["clean_sheet"] == 1
    assert keeper["metrics"]["opponent_xg"] == 1.48
    assert keeper["metrics"]["opponent_attempts_on_target"] == 7
    assert keeper["metrics"]["keeper_saved_shots"] == 8


def test_chinese_fact_bank_does_not_label_ordinary_go_ahead_goal_as_comeback():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-18")

    fact_bank_text = json.dumps(report, ensure_ascii=False)

    assert "反超进球" not in fact_bank_text


def test_editorial_evidence_exposes_match_flow_for_comeback_winner(tmp_path):
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-20")
    write_editorial_artifacts(
        report,
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
    )

    flow = report["match_flows"]["FIFA-2026-M33-GER-CIV"]
    assert flow["home_came_from_behind_to_win"] is True
    assert flow["decisive_goal"]["player_name"] == "Deniz UNDAV"
    assert "comeback_winner" in flow["decisive_goal"]["tags"]

    choices_by_name = {choice["player_name"]: choice for choice in report["choices"]}
    undav = choices_by_name["Deniz UNDAV"]
    assert undav["flow_context"]["team_came_from_behind_to_win"] is True
    assert "comeback win" in undav["flow_context"]["allowed_claims"]["en"]
    assert "逆转取胜" in undav["flow_context"]["allowed_claims"]["zh"]
    assert any(
        component["metric"] == "comeback_winner"
        for component in undav["score_components"]
    )

    evidence = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-20" / "evidence.json").read_text(
            encoding="utf-8"
        )
    )
    fact_bank = json.loads(
        (
            tmp_path
            / "site"
            / "editorial"
            / "2026-06-20"
            / "fact_bank.zh.json"
        ).read_text(encoding="utf-8")
    )
    brief = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-20" / "brief.en.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["match_flows"]["FIFA-2026-M33-GER-CIV"]["home_came_from_behind_to_win"] is True
    fact_bank_text = json.dumps(fact_bank, ensure_ascii=False)
    brief_text = json.dumps(brief, ensure_ascii=False)
    assert "德国 0-1 落后后 2-1 逆转取胜" in fact_bank_text
    assert "68' 扳平" in fact_bank_text
    assert "94' 补时制胜" in fact_bank_text
    assert "Germany came from behind to win 2-1" in brief_text
    assert "94' stoppage-time winner" in brief_text


def test_editorial_evidence_keeps_blowout_goals_out_of_winner_claims():
    report = build_editorial_report("data/latest.sqlite", match_date="2026-06-21")
    spain_choices = [choice for choice in report["choices"] if choice["team"] == "Spain"]

    assert spain_choices
    for choice in spain_choices:
        assert not any(
            "winner" in claim or "match-winning" in claim
            for claim in choice["flow_context"]["allowed_claims"]["en"]
        )
        assert "match-winning goal" not in choice["evidence_chips"]["en"]
        assert "打入制胜球" not in choice["evidence_chips"]["zh"]
        assert not any(
            component["metric"] == "match_winning_goal"
            for component in choice["score_components"]
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
    en_brief_json = tmp_path / "site" / "editorial" / "2026-06-16" / "brief.en.json"
    dated_html = tmp_path / "site" / "editorial" / "2026-06-16" / "index.html"
    archive_html = tmp_path / "site" / "editorial" / "index.html"
    report_md = tmp_path / "reports" / "editorial" / "2026-06-16.md"

    assert latest.exists()
    assert dated_json.exists()
    assert evidence_json.exists()
    assert zh_fact_bank_json.exists()
    assert not (tmp_path / "site" / "editorial" / "2026-06-16" / "brief.zh.json").exists()
    assert en_brief_json.exists()
    assert dated_html.exists()
    assert archive_html.exists()
    assert report_md.exists()

    saved = json.loads(latest.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_json.read_text(encoding="utf-8"))
    zh_fact_bank = json.loads(zh_fact_bank_json.read_text(encoding="utf-8"))
    en_brief = json.loads(en_brief_json.read_text(encoding="utf-8"))
    html = dated_html.read_text(encoding="utf-8")
    archive = archive_html.read_text(encoding="utf-8")
    markdown = report_md.read_text(encoding="utf-8")
    first_choice = saved["choices"][0]

    assert saved["schema_version"] == 2
    assert saved["match_date"] == "2026-06-16"
    assert saved["editorial_generation"]["uses_official_assists"] is True
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
    assert any("3 个进球" in fact for fact in zh_fact_bank["choices"][0]["facts"])
    assert not any("制胜进球" in fact for fact in zh_fact_bank["choices"][0]["facts"])
    assert any("首开纪录" in fact for fact in zh_fact_bank["choices"][0]["facts"])
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
    assert en_brief["language"] == "en"
    assert en_brief["choices"][0]["player_name"] == "Lionel MESSI"
    assert "帽子戏法" not in json.dumps(en_brief, ensure_ascii=False)
    assert "Editor's Choices" in html
    assert "Editor&apos;s Choices" not in html
    assert 'href="2026-06-16/"' in archive
    assert "official assists" in archive
    assert "Lionel MESSI turned the day" not in archive
    assert "🇦🇷 Lionel MESSI" in html
    assert "🇦🇷 Argentina vs 🇩🇿 Algeria" in html
    assert "<span>score</span>" not in html
    assert "## Choices" in markdown
    assert "#### English" in markdown
    assert "#### 中文" in markdown
    assert "Draft brief" in markdown
    assert "中文编辑草稿" not in markdown
    assert "fact_bank.zh.json" in markdown


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
    assert "中文编辑草稿" not in markdown
    assert "fact_bank.zh.json" in markdown
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
