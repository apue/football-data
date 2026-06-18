from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_publish_editors_choices_skill_is_repo_scoped():
    skill = ROOT / ".agents" / "skills" / "publish-editors-choices" / "SKILL.md"

    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    references = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".agents" / "skills" / "publish-editors-choices" / "references").glob(
            "*.md"
        )
    )
    assert text.startswith("---\n")
    assert "name: publish-editors-choices" in text
    assert "description: Use when" in text
    assert "Editor" in text
    assert "scripts/generate_editorial.py" in text
    assert "reports/editorial/YYYY-MM-DD.md" in references
    assert "scripts/render_editorial.py" in references
    assert "Markdown is the human-readable source" in references
    assert "Write Chinese from `fact_bank.zh.json`, not from the English draft" in references
    assert "Treat generated Markdown as a draft brief, not publishable copy" in references
    assert "Rewrite Chinese and English in separate passes from the same evidence" in references
    assert "Do not use either finished language version as input for the other" in references
    assert "fact_bank.zh.json" in references
    assert "from-scratch Chinese sports editor" in references
    assert "qu-ai-wei" in references
    assert "humanizer-zh" in references
    assert "brief.zh.json" in references
    assert "brief.en.json" in references
    assert "Generate 3-5 Chinese title candidates" in references
    assert "editorial review pass" in references
    assert "football actions before data labels" in references


def test_calibrate_potm_labels_skill_is_repo_scoped():
    skill = ROOT / ".agents" / "skills" / "calibrate-potm-labels" / "SKILL.md"

    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    references = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".agents" / "skills" / "calibrate-potm-labels" / "references").glob(
            "*.md"
        )
    )

    assert text.startswith("---\n")
    assert "name: calibrate-potm-labels" in text
    assert "description: Use when" in text
    assert "Firecrawl" in text
    assert "Keypool" in text
    assert "scripts/calibrate_potm.py" in references
    assert "calibration/potm-labels.json" in references
    assert "POTM is a weak label" in references
    assert "Do not use POTM as a scoring input" in references
    assert "rank_diff" in references
    assert "top3_hit_rate" in references


def test_publish_skill_mentions_potm_calibration_gate():
    skill_dir = ROOT / ".agents" / "skills" / "publish-editors-choices"
    text = "\n".join(path.read_text(encoding="utf-8") for path in skill_dir.rglob("*.md"))

    assert "calibrate-potm-labels" in text
    assert "POTM calibration" in text
