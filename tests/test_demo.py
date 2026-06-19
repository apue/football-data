from football_data.demo import build_demo_site


def test_demo_uses_player_first_bilingual_dashboard(tmp_path):
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
              "score": 37.5,
              "evidence_chips": {
                "en": ["hat-trick profile", "high shot quality"],
                "zh": ["帽子戏法级别的进攻画像", "射门质量突出"]
              },
              "content": {
                "en": {"title": "The clearest attacking case", "html": "<p>Messi gave the data a simple story to tell.</p>"},
                "zh": {"title": "最清楚的进攻答案", "html": "<p>梅西让这一天的数据故事变得很直接。</p>"}
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    build_demo_site("data/latest.sqlite", tmp_path, "manifests")

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert "Editor's Choices" in html
    assert "🇦🇷 Lionel MESSI" in html
    assert "🇦🇷 Argentina vs 🇩🇿 Algeria" in html
    assert "The clearest attacking case" in html
    assert "最清楚的进攻答案" in html
    assert "<span>score</span>" not in html
    assert "<strong>37.5</strong>" not in html
    assert "<th>Score</th>" not in html
    assert '<details class="panel collapsible">' in html
    assert "<summary><h2>New Matches</h2>" in html
    assert "<summary><h2>Loaded Matches</h2>" in html
    assert 'class="language-toggle"' in html
    assert 'data-lang-button="zh"' in html
    assert 'data-i18n="hero.title"' in html
    assert 'data-scope="round1"' in html
    assert 'data-scope="round2"' in html
    assert 'data-scope="overall"' in html
    assert 'data-mode="single"' in html
    assert 'data-mode="accumulated"' in html
    assert 'id="leaderboard-grid"' in html
    assert "Player Leaderboards" in html
    assert "球员榜单" in html
    assert "Most Shots on Target" in html
    assert "射正最多" in html
    assert "Completed Line Breaks" in html
    assert "打穿防线" in html
    assert "In-Behind Offers" in html
    assert "身后接应" in html
    assert "Ball Progressions" in html
    assert "推进球" in html
    assert "Possession Regains" in html
    assert "夺回球权" in html
    assert "Single-match peak" in html
    assert "单场峰值" in html
    assert "Accumulated" in html
    assert "累计" in html
    assert "Group Round 1" in html
    assert "小组赛第一轮" in html
    assert "🇵🇦 Andres ANDRADE" in html
    assert "Top 5 Fastest Players" not in html
    assert "Top 5 Total Distance" not in html
    assert "Top 5 Completed Line Breaks" not in html
    assert "Top 5 Final Third Receptions" not in html
    assert "Goals and On-Target Shots" not in html
