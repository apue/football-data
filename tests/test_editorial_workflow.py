from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editorial_workflow_runs_after_dataset_update_and_exposes_secret_env():
    workflow = ROOT / ".github" / "workflows" / "editorial.yml"

    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")

    assert 'workflows: ["Update Dataset"]' in text
    assert "workflow_dispatch" in text
    assert "python scripts/run_editorial_queue.py" in text
    assert "--ignore=tests/test_extract.py" in text
    assert "--ignore=tests/test_database.py" in text
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in text
    assert "OPENAI_BASE_URL: ${{ vars.OPENAI_BASE_URL || 'https://api.siliconflow.cn/v1' }}" in text
    assert "EDITORIAL_ZH_WRITER_MODEL: ${{ vars.EDITORIAL_ZH_WRITER_MODEL || 'zai-org/GLM-5.2' }}" in text
    assert "EDITORIAL_AGENT_MAX_CONCURRENCY: ${{ vars.EDITORIAL_AGENT_MAX_CONCURRENCY || '3' }}" in text
    assert "EDITORIAL_AGENT_MAX_ATTEMPTS: ${{ vars.EDITORIAL_AGENT_MAX_ATTEMPTS || '2' }}" in text
    assert "KEYPOOL_KEY: ${{ secrets.KEYPOOL_KEY }}" in text
    assert "KEYPOOL_URL: ${{ vars.KEYPOOL_URL || secrets.KEYPOOL_URL }}" in text
    assert "agent-runs" in text
    assert "editorial-run" in text
    assert "[skip ci]" in text


def test_env_example_lists_editorial_agent_and_firecrawl_placeholders():
    env_example = ROOT / ".env.example"

    assert env_example.exists()
    text = env_example.read_text(encoding="utf-8")

    for key in [
        "OPENAI_API_KEY=",
        "OPENAI_BASE_URL=https://api.siliconflow.cn/v1",
        "EDITORIAL_ZH_WRITER_MODEL=zai-org/GLM-5.2",
        "EDITORIAL_ZH_EDITOR_MODEL=Qwen/Qwen3.5-397B-A17B",
        "EDITORIAL_EN_WRITER_MODEL=deepseek-ai/DeepSeek-V4-Flash",
        "EDITORIAL_EN_EDITOR_MODEL=deepseek-ai/DeepSeek-V4-Pro",
        "EDITORIAL_FACT_CHECK_MODEL=deepseek-ai/DeepSeek-V4-Pro",
        "EDITORIAL_AGENT_TIMEOUT_SECONDS=90",
        "EDITORIAL_AGENT_MAX_CONCURRENCY=3",
        "EDITORIAL_AGENT_MAX_ATTEMPTS=2",
        "KEYPOOL_KEY=",
        "KEYPOOL_URL=",
    ]:
        assert key in text
