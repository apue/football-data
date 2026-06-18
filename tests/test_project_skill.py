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
    assert "Write Chinese from evidence, not from the English draft" in references
    assert "Treat generated Markdown as a draft brief, not publishable copy" in references
    assert "Rewrite Chinese and English in separate passes from the same evidence" in references
    assert "Do not use either finished language version as input for the other" in references
    assert "brief.zh.json" in references
    assert "brief.en.json" in references
    assert "Generate 3-5 Chinese title candidates" in references
    assert "editorial review pass" in references
    assert "football actions before data labels" in references
