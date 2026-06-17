from football_data.demo import build_demo_site


def test_demo_uses_collapsed_long_sections_and_insight_tables(tmp_path):
    build_demo_site("data/latest.sqlite", tmp_path, "manifests")

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert '<details class="panel collapsible">' in html
    assert "<summary><h2>New Matches</h2>" in html
    assert "<summary><h2>Loaded Matches</h2>" in html
    assert '<div class="grid equal-height">' in html
    assert "Top 5 Completed Line Breaks" in html
    assert "Top 5 Final Third Receptions" in html
    assert "Goals and On-Target Shots" not in html
