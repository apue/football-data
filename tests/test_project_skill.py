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
    assert "scripts/run_editorial_queue.py" in text
    assert "scripts/run_editorial_v2.py" in references
    assert "reports/editorial/YYYY-MM-DD.md" in references
    assert "scripts/generate_editorial.py" not in text + references
    assert "scripts/render_editorial.py" not in text + references
    assert "scripts/run_editorial_loop.py" not in text + references
    assert "run_editorial_agent.py" not in text + references
    assert "ai_rerank_selection_v1" in text + references
    assert "OpenAI Agents SDK" in text + references
    assert "selection_validation.json" in text + references
    assert "candidate_pool.json" in references
    assert "selector_input.json" in references
    assert "selection_decision.json" in references
    assert "Do not use either finished language version as input for the other" in references
    assert "candidate evidence packet" in references
    assert "from-scratch Chinese sports editor" in references
    assert "fact_bank.zh.json" not in references
    assert "brief.zh.json" not in references
    assert "brief.en.json" not in references
    assert "generate 3-5 Chinese title candidates" in references
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


def test_evaluate_potm_workflow_skill_is_repo_scoped():
    skill = ROOT / ".agents" / "skills" / "evaluate-potm-workflow" / "SKILL.md"

    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    references = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".agents" / "skills" / "evaluate-potm-workflow" / "references").glob(
            "*.md"
        )
    )

    assert text.startswith("---\n")
    assert "name: evaluate-potm-workflow" in text
    assert "description: Use when" in text
    assert "Firecrawl" in text
    assert "Keypool" in text
    assert "scripts/evaluate_potm_workflow.py" in references
    assert "calibration/evaluation" in references
    assert "source_quality" in references
    assert "noise_ratio" in references
    assert "POTM is a weak label" in references
    assert "Do not change scoring weights from one evaluation" in references
