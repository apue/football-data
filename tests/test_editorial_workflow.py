from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editorial_workflow_is_manual_only_smoke_path_and_exposes_optional_env():
    workflow = ROOT / ".github" / "workflows" / "editorial.yml"

    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")

    assert "workflow_dispatch" in text
    assert "workflow_run" not in text
    assert 'workflows: ["Update Dataset"]' not in text
    assert 'default: "true"' in text
    assert "python scripts/run_editorial_queue.py" in text
    assert "manifests/editorial-v2-run.json" in text
    assert "--experiment" in text
    assert "--ignore=tests/test_extract.py" in text
    assert "--ignore=tests/test_database.py" in text
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in text
    assert "OPENAI_BASE_URL: ${{ vars.OPENAI_BASE_URL || 'https://api.siliconflow.cn/v1' }}" in text
    assert "EDITORIAL_SELECTION_EDITOR_MODEL: ${{ vars.EDITORIAL_SELECTION_EDITOR_MODEL || 'deepseek-ai/DeepSeek-V4-Flash' }}" in text
    assert "EDITORIAL_ZH_EDITOR_MODEL: ${{ vars.EDITORIAL_ZH_EDITOR_MODEL || 'zai-org/GLM-5.2' }}" in text
    assert "EDITORIAL_EN_EDITOR_MODEL: ${{ vars.EDITORIAL_EN_EDITOR_MODEL || 'deepseek-ai/DeepSeek-V4-Flash' }}" in text
    assert "EDITORIAL_REVIEW_EDITOR_MODEL: ${{ vars.EDITORIAL_REVIEW_EDITOR_MODEL || 'deepseek-ai/DeepSeek-V4-Flash' }}" in text
    assert "EDITORIAL_REVISION_EDITOR_MODEL" not in text
    assert "EDITORIAL_AGENT_TIMEOUT_SECONDS: ${{ vars.EDITORIAL_AGENT_TIMEOUT_SECONDS || '180' }}" in text
    assert "EDITORIAL_ZH_WRITER_MODEL" not in text
    assert "EDITORIAL_EN_WRITER_MODEL" not in text
    assert "EDITORIAL_FACT_CHECK_MODEL" not in text
    assert "EDITORIAL_AGENT_MAX_CONCURRENCY: ${{ vars.EDITORIAL_AGENT_MAX_CONCURRENCY || '6' }}" in text
    assert "EDITORIAL_AGENT_MAX_ATTEMPTS: ${{ vars.EDITORIAL_AGENT_MAX_ATTEMPTS || '1' }}" in text
    assert "KEYPOOL_KEY: ${{ secrets.KEYPOOL_KEY }}" in text
    assert "KEYPOOL_URL: ${{ vars.KEYPOOL_URL || secrets.KEYPOOL_URL }}" in text
    assert "agent-runs" in text
    assert "editorial-run" in text
    assert "github.event.inputs.fake != 'true'" in text
    assert "[skip ci]" in text


def test_env_example_lists_editorial_ai_and_firecrawl_placeholders():
    env_example = ROOT / ".env.example"

    assert env_example.exists()
    text = env_example.read_text(encoding="utf-8")

    for key in [
        "OPENAI_API_KEY=",
        "OPENAI_BASE_URL=https://api.siliconflow.cn/v1",
        "EDITORIAL_SELECTION_EDITOR_MODEL=deepseek-ai/DeepSeek-V4-Flash",
        "EDITORIAL_ZH_EDITOR_MODEL=zai-org/GLM-5.2",
        "EDITORIAL_EN_EDITOR_MODEL=deepseek-ai/DeepSeek-V4-Flash",
        "EDITORIAL_REVIEW_EDITOR_MODEL=deepseek-ai/DeepSeek-V4-Flash",
        "EDITORIAL_AGENT_TIMEOUT_SECONDS=180",
        "EDITORIAL_AGENT_MAX_CONCURRENCY=6",
        "EDITORIAL_AGENT_MAX_ATTEMPTS=1",
        "KEYPOOL_KEY=",
        "KEYPOOL_URL=",
    ]:
        assert key in text
    for old_key in [
        "EDITORIAL_ZH_WRITER_MODEL",
        "EDITORIAL_EN_WRITER_MODEL",
        "EDITORIAL_FACT_CHECK_MODEL",
        "EDITORIAL_REVISION_EDITOR_MODEL",
    ]:
        assert old_key not in text
