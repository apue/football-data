from football_data.demo import build_demo_site


def test_demo_uses_collapsed_long_sections_and_insight_tables(tmp_path):
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
    assert "The clearest attacking case" in html
    assert "最清楚的进攻答案" in html
    assert '<details class="panel collapsible">' in html
    assert "<summary><h2>New Matches</h2>" in html
    assert "<summary><h2>Loaded Matches</h2>" in html
    assert '<div class="grid equal-height">' in html
    assert "Top 5 Attacking Threats" in html
    assert "Top 5 Progressors" in html
    assert "Top 5 Off-Ball Receivers" in html
    assert "Top 5 Defensive Contributors" in html
    assert "Top 5 Completed Line Breaks" not in html
    assert "Top 5 Final Third Receptions" not in html
    assert "Goals and On-Target Shots" not in html
