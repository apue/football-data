import sqlite3

from football_data.demo import build_demo_site


def test_demo_uses_player_first_bilingual_dashboard(tmp_path):
    latest_date = _latest_data_date()
    editorial_dir = tmp_path / "editorial"
    editorial_dir.mkdir()
    latest_json = """
        {
          "match_date": "__MATCH_DATE__",
          "choices": [
            {
              "award_type": "player_of_the_day",
              "award_label": {"en": "Player of the Day", "zh": "每日最佳球员"},
              "player_name": "Lionel MESSI",
              "team": "Argentina",
              "opponent": "Algeria",
              "match_no": 19,
              "score": 37.5,
              "evidence_chips": {
                "en": ["hat-trick profile", "high shot quality"],
                "zh": ["帽子戏法级别的进攻画像", "射门质量突出"]
              },
              "content": {
                "en": {"title": "The clearest attacking case", "html": "<p>Messi gave the data a simple story to tell.</p>"},
                "zh": {"title": "最清楚的进攻答案", "html": "<p>梅西让这一天的数据故事变得很直接。</p>"}
              }
            },
            {
              "award_type": "player_of_the_day",
              "award_label": {"en": "Player of the Day", "zh": "每日最佳球员"},
              "player_name": "Luis ROMO",
              "team": "Mexico",
              "opponent": "Korea Republic",
              "match_no": 22,
              "evidence_chips": {
                "en": ["late winner"],
                "zh": ["绝杀"]
              },
              "content": {
                "en": {"title": "The late answer", "html": "<p>Romo changed the result late.</p>"},
                "zh": {"title": "最后的答案", "html": "<p>Romo 在最后阶段改写了结果。</p>"}
              }
            },
            {
              "award_type": "impact_pick",
              "award_label": {"en": "Impact Pick", "zh": "影响力精选"},
              "player_name": "Granit XHAKA",
              "team": "Switzerland",
              "opponent": "Bosnia and Herzegovina",
              "match_no": 26,
              "evidence_chips": {
                "en": ["progressive passing"],
                "zh": ["向前传递"]
              },
              "content": {
                "en": {"title": "The best route forward", "html": "<p>Xhaka gave Switzerland a route forward.</p>"},
                "zh": {"title": "向前的线路", "html": "<p>Xhaka 给瑞士提供了向前线路。</p>"}
              }
            },
            {
              "award_type": "impact_pick",
              "award_label": {"en": "Impact Pick", "zh": "影响力精选"},
              "player_name": "LEE Gihyuk",
              "team": "Korea Republic",
              "opponent": "Mexico",
              "match_no": 22,
              "evidence_chips": {
                "en": ["defensive work"],
                "zh": ["防守贡献"]
              },
              "content": {
                "en": {"title": "The hidden defensive note", "html": "<p>Lee made the defensive side visible.</p>"},
                "zh": {"title": "被遮住的防守亮点", "html": "<p>李基赫的防守工作值得被看见。</p>"}
              }
            }
          ]
        }
        """
    (editorial_dir / "latest.json").write_text(
        latest_json.replace("__MATCH_DATE__", latest_date),
        encoding="utf-8",
    )

    build_demo_site("data/latest.sqlite", tmp_path, "manifests")

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert "Editor's Choices" in html
    assert "🇦🇷 Lionel MESSI" in html
    assert "🇦🇷 Argentina vs 🇩🇿 Algeria" in html
    assert "The clearest attacking case" in html
    assert "最清楚的进攻答案" in html
    assert "🇰🇷 LEE Gihyuk" in html
    assert "The hidden defensive note" in html
    assert "影响力精选" in html
    assert "<span>score</span>" not in html
    assert "<strong>37.5</strong>" not in html
    assert "<th>Score</th>" not in html
    assert '<details class="panel collapsible">' in html
    assert "<summary><h2>New Matches</h2>" in html
    assert "<summary><h2>Loaded Matches</h2>" in html
    assert 'class="language-toggle"' in html
    assert 'data-lang-button="zh"' in html
    assert 'data-i18n="hero.title"' in html
    assert 'data-scope="group_round_1"' in html
    assert 'data-scope="group_round_2"' in html
    assert 'data-scope="group_round_3"' in html
    assert 'data-scope="overall"' in html
    assert 'data-mode="single"' in html
    assert 'data-mode="accumulated"' in html
    assert 'id="leaderboard-grid"' in html
    assert "Player Leaderboards" in html
    assert "Goal Involvements" in html
    assert "进球参与" in html
    assert "Progressive Line Breaks" in html
    assert "推进型打穿防线" in html
    assert "Completed Crosses" in html
    assert "成功传中" in html
    assert "Top Speed" in html
    assert "最高速度" in html
    assert "Distance Covered" in html
    assert "跑动距离" in html
    assert "Sprints" in html
    assert "冲刺次数" in html
    assert "In-Behind Offers" not in html
    assert "身后接应" not in html


def test_demo_does_not_show_stale_editorial_cards_as_latest(tmp_path):
    editorial_dir = tmp_path / "editorial"
    editorial_dir.mkdir()
    (editorial_dir / "latest.json").write_text(
        """
        {
          "match_date": "2026-06-16",
          "choices": [
            {
              "award_type": "player_of_the_day",
              "award_label": {"en": "Player of the Day", "zh": "每日最佳球员"},
              "player_name": "Lionel MESSI",
              "team": "Argentina",
              "opponent": "Algeria",
              "match_no": 19,
              "evidence_chips": {"en": ["hat-trick"], "zh": ["帽子戏法"]},
              "content": {
                "en": {"title": "Old title", "html": "<p>Old copy.</p>"},
                "zh": {"title": "旧标题", "html": "<p>旧文案。</p>"}
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    build_demo_site("data/latest.sqlite", tmp_path, "manifests")

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert "Old title" not in html
    assert "Latest data is" in html
    assert "Open archive" in html


def _latest_data_date() -> str:
    conn = sqlite3.connect("data/latest.sqlite")
    try:
        row = conn.execute("select max(match_date) from matches").fetchone()
    finally:
        conn.close()
    assert row and row[0]
    return str(row[0])
