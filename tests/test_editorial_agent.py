import json
import subprocess
import sys
import time
from pathlib import Path

from football_data.editorial_agent import (
    AgentCompletionRequest,
    AgentTextClient,
    _deterministic_fact_check,
    _editor_instructions,
    _filter_llm_warnings,
    _writer_instructions,
    load_editorial_agent_config,
    run_editorial_agent,
)


class FakeEditorialClient(AgentTextClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.payloads: dict[str, list[dict[str, object]]] = {}

    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[object] | None = None,
    ) -> str:
        self.calls.append((role, model))
        payload = json.loads(user_input)
        self.payloads.setdefault(role, []).append(payload)
        if role.endswith("fact_check"):
            return json.dumps({"status": "pass", "warnings": []})
        language = payload["language"]
        items = []
        for index, choice in enumerate(payload["choices"], start=1):
            player_name = choice["player_name"]
            if language == "zh":
                title = f"{player_name} 的中文标题"
                body = f"{player_name} 入选是因为这些证据足够清楚。第 {index} 张卡片保持简短。"
            else:
                title = f"{player_name} in focus"
                body = f"{player_name} belongs here because the evidence is clear. Card {index} stays brief."
            items.append(
                {
                    "award_type": choice["award_type"],
                    "player_name": player_name,
                    "title": title,
                    "body": body,
                }
            )
        return json.dumps({"items": items, "warnings": []}, ensure_ascii=False)


class BatchEditorialClient(FakeEditorialClient):
    def __init__(self) -> None:
        super().__init__()
        self.batch_roles: list[list[str]] = []
        self.batch_concurrency: list[int] = []

    def complete_many(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[str]:
        self.batch_roles.append([request.role for request in requests])
        self.batch_concurrency.append(max_concurrency)
        return [
            self.complete(
                role=request.role,
                model=request.model,
                instructions=request.instructions,
                user_input=request.user_input,
                output_type=request.output_type,
            )
            for request in requests
        ]


class WarningFactCheckClient(FakeEditorialClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[object] | None = None,
    ) -> str:
        if role == "final_fact_check":
            return json.dumps({"status": "fail", "warnings": ["advisory warning"]})
        return super().complete(
            role=role,
            model=model,
            instructions=instructions,
            user_input=user_input,
            output_type=output_type,
        )


class FilteredFactCheckClient(FakeEditorialClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[object] | None = None,
    ) -> str:
        if role == "final_fact_check":
            return json.dumps({"status": "fail", "warnings": ["The markdown claims assists, but no assist data exists."]})
        return super().complete(
            role=role,
            model=model,
            instructions=instructions,
            user_input=user_input,
            output_type=output_type,
        )


class TimeoutFactCheckClient(FakeEditorialClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[object] | None = None,
    ) -> str:
        if role == "final_fact_check":
            time.sleep(1)
        return super().complete(
            role=role,
            model=model,
            instructions=instructions,
            user_input=user_input,
            output_type=output_type,
        )


class RenamingEditorialClient(FakeEditorialClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[object] | None = None,
    ) -> str:
        payload = json.loads(user_input)
        if role.endswith("fact_check"):
            return json.dumps({"status": "pass", "warnings": []})
        language = payload["language"]
        if language == "zh":
            item = {"award_type": "changed", "player_name": "改名", "title": "中文标题", "body": "中文正文。"}
        else:
            item = {"award_type": "changed", "player_name": "Renamed", "title": "English title", "body": "English body."}
        return json.dumps({"items": [item], "warnings": []}, ensure_ascii=False)


def test_load_editorial_agent_config_uses_openai_base_url_only(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY='secret'",
                "OPENAI_BASE_URL=https://api.example.test/v1",
                "OPEN_BASE_URL=https://wrong.example.test/v1",
                "EDITORIAL_ZH_WRITER_MODEL=zh-writer",
                "EDITORIAL_AGENT_MAX_CONCURRENCY=5",
            ]
        ),
        encoding="utf-8",
    )

    config = load_editorial_agent_config(env_path)

    assert config.api_key == "secret"
    assert config.base_url == "https://api.example.test/v1"
    assert config.models["zh_writer"] == "zh-writer"
    assert config.max_concurrency == 5
    assert "OPEN_BASE_URL" not in config.loaded_keys


def test_load_editorial_agent_config_reads_process_environment(tmp_path, monkeypatch):
    env_path = tmp_path / "missing.env"
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("EDITORIAL_EN_WRITER_MODEL", "env-en-writer")
    monkeypatch.setenv("EDITORIAL_AGENT_MAX_CONCURRENCY", "4")

    config = load_editorial_agent_config(env_path)

    assert config.api_key == "env-secret"
    assert config.base_url == "https://api.example.test/v1"
    assert config.models["en_writer"] == "env-en-writer"
    assert config.max_concurrency == 4


def test_load_editorial_agent_config_uses_default_base_url_and_models(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text("OPENAI_API_KEY='secret'\n", encoding="utf-8")

    config = load_editorial_agent_config(env_path)

    assert config.base_url == "https://api.siliconflow.cn/v1"
    assert config.models["zh_writer"] == "zai-org/GLM-5.2"
    assert config.models["fact_check"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert config.max_concurrency == 3


def test_filter_llm_fact_check_warnings_drops_absent_assist_claims():
    warnings = _filter_llm_warnings(
        "This copy mentions line breaks but not the forbidden term.",
        ["The markdown claims assists, but no assist data exists.", "Keep this warning."],
    )

    assert warnings == ["Keep this warning."]


def test_deterministic_fact_check_catches_all_team_goals_overclaim():
    evidence = {
        "matches": [
            {
                "match_key": "FIFA-2026-M27-CAN-QAT",
                "home_team": "Canada",
                "away_team": "Qatar",
                "home_score": 6,
                "away_score": 0,
            }
        ],
        "choices": [
            {
                "match_key": "FIFA-2026-M27-CAN-QAT",
                "player_name": "Jonathan DAVID",
                "team": "Canada",
                "score_components": [{"metric": "goals", "value": 3}],
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "Jonathan DAVID scored all three goals for Canada in a 6-0 win.",
    )

    assert any("all team goals" in warning for warning in warnings)


def test_deterministic_fact_check_blocks_unsupported_comeback_claim():
    evidence = {
        "matches": [
            {
                "match_key": "FIFA-2026-M28-SUI-BIH",
                "home_team": "Switzerland",
                "away_team": "Bosnia and Herzegovina",
                "home_score": 4,
                "away_score": 1,
            }
        ],
        "choices": [
            {
                "match_key": "FIFA-2026-M28-SUI-BIH",
                "player_name": "Johan MANZAMBI",
                "team": "Switzerland",
                "score_components": [
                    {"metric": "goals", "value": 2},
                    {"metric": "opening_goal", "value": 1},
                    {"metric": "go_ahead_goal", "value": 1},
                ],
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "Johan MANZAMBI 替补出场之后打进反超进球。",
    )

    assert any("comeback" in warning for warning in warnings)


def test_deterministic_fact_check_catches_overbroad_editorial_claims():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": []},
        "南非的每一次向前几乎都经过他的脚下，整场节奏全由他掌控。",
    )

    assert any("overbroad" in warning for warning in warnings)


def test_editorial_agent_prompts_explicitly_reject_overbroad_claims():
    zh_prompt = _writer_instructions("zh", {})
    en_prompt = _editor_instructions("en", {})

    assert "几乎" in zh_prompt
    assert "no answer" in en_prompt


def test_run_editorial_agent_with_fake_client_writes_artifacts(tmp_path):
    client = FakeEditorialClient()

    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        env_path=tmp_path / "missing.env",
        client=client,
        research=False,
        rebuild_homepage=False,
    )

    markdown_path = tmp_path / "reports" / "editorial" / "2026-06-18.md"
    choices_path = tmp_path / "site" / "editorial" / "2026-06-18" / "choices.json"
    run_path = tmp_path / "agent-runs" / "2026-06-18.json"
    external_path = tmp_path / "site" / "editorial" / "2026-06-18" / "external_evidence.json"

    assert result["status"] == "success"
    assert markdown_path.exists()
    assert choices_path.exists()
    assert run_path.exists()
    assert external_path.exists()
    assert [call[0] for call in client.calls].count("zh_writer") == 6
    assert [call[0] for call in client.calls].count("zh_final_editor") == 6
    assert [call[0] for call in client.calls].count("en_writer") == 6
    assert [call[0] for call in client.calls].count("en_final_editor") == 6
    assert [call[0] for call in client.calls].count("zh_draft_fact_check") == 1
    assert [call[0] for call in client.calls].count("en_draft_fact_check") == 1
    assert [call[0] for call in client.calls].count("final_fact_check") == 1
    assert client.payloads["zh_final_editor"][0]["draft_fact_check"] == {
        "status": "pass",
        "warnings": [],
    }
    assert client.payloads["en_final_editor"][0]["draft_fact_check"] == {
        "status": "pass",
        "warnings": [],
    }

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "### Player of the Day:" in markdown
    assert "#### English" in markdown
    assert "#### 中文" in markdown
    assert "的中文标题" in markdown

    choices = json.loads(choices_path.read_text(encoding="utf-8"))
    assert choices["match_date"] == "2026-06-18"
    assert choices["choices"]
    assert "score" not in choices["choices"][0]

    run_payload = json.loads(run_path.read_text(encoding="utf-8"))
    assert run_payload["match_date"] == "2026-06-18"
    assert run_payload["workflow"]["name"] == "editorial_state_graph"
    assert [node["id"] for node in run_payload["workflow"]["nodes"]] == [
        "build_evidence",
        "external_research",
        "zh_writer",
        "zh_draft_fact_check",
        "zh_final_editor",
        "en_writer",
        "en_draft_fact_check",
        "en_final_editor",
        "render_markdown",
        "final_deterministic_validation",
        "final_fact_check",
        "compile_publish",
    ]
    assert all(node["status"] == "success" for node in run_payload["workflow"]["nodes"])
    assert run_payload["fact_check"]["status"] == "pass"
    assert "OPENAI_API_KEY" not in json.dumps(run_payload)


def test_editorial_agent_batches_per_card_writer_and_editor_calls(tmp_path):
    client = BatchEditorialClient()
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test",
                "EDITORIAL_AGENT_MAX_CONCURRENCY=4",
            ]
        ),
        encoding="utf-8",
    )

    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        env_path=env_path,
        client=client,
        research=False,
        rebuild_homepage=False,
    )

    assert result["status"] == "success"
    assert client.batch_roles == [
        ["zh_writer"] * 6,
        ["zh_final_editor"] * 6,
        ["en_writer"] * 6,
        ["en_final_editor"] * 6,
    ]
    assert client.batch_concurrency == [4, 4, 4, 4]
    node_summaries = {
        node["id"]: node["summary"]
        for node in result["workflow"]["nodes"]
    }
    assert node_summaries["zh_writer"]["agent_calls"] == 6
    assert node_summaries["zh_writer"]["max_concurrency"] == 4


def test_llm_fact_check_warnings_are_advisory_without_deterministic_failures(tmp_path):
    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=WarningFactCheckClient(),
        research=False,
        rebuild_homepage=False,
    )

    assert result["status"] == "success"
    assert result["fact_check"]["status"] == "warning"
    assert result["fact_check"]["llm_status"] == "fail"
    assert result["fact_check"]["warnings"] == ["advisory warning"]


def test_filtered_llm_fact_check_warnings_do_not_leave_failed_status(tmp_path):
    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=FilteredFactCheckClient(),
        research=False,
        rebuild_homepage=False,
    )

    assert result["fact_check"]["status"] == "pass"
    assert result["fact_check"]["llm_status"] == "pass"
    assert result["fact_check"]["warnings"] == []


def test_llm_fact_check_timeout_is_advisory_when_deterministic_checks_pass(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test",
                "OPENAI_BASE_URL=https://api.example.test/v1",
                "EDITORIAL_AGENT_TIMEOUT_SECONDS=0.05",
            ]
        ),
        encoding="utf-8",
    )

    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        env_path=env_path,
        client=TimeoutFactCheckClient(),
        research=False,
        rebuild_homepage=False,
    )

    assert result["status"] == "success"
    assert result["fact_check"]["status"] == "warning"
    assert result["fact_check"]["llm_status"] == "timeout"
    assert any("timed out" in warning for warning in result["fact_check"]["warnings"])


def test_per_card_agent_copy_is_bound_to_original_choice_identity(tmp_path):
    run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=RenamingEditorialClient(),
        research=False,
        rebuild_homepage=False,
    )

    markdown = (tmp_path / "reports" / "editorial" / "2026-06-18.md").read_text(
        encoding="utf-8"
    )
    assert "中文标题" in markdown
    assert "English title" in markdown
    assert "Draft brief" not in markdown
    assert "中文编辑草稿" not in markdown


def test_run_editorial_agent_cli_dry_run_with_fake_backend(tmp_path):
    out_dir = tmp_path / "out"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_editorial_agent.py",
            "--date",
            "2026-06-18",
            "--site-dir",
            str(out_dir / "site"),
            "--reports-dir",
            str(out_dir / "reports"),
                "--agent-runs-dir",
                str(out_dir / "agent-runs"),
                "--env",
                str(out_dir / "missing.env"),
                "--fake",
                "--no-research",
                "--no-homepage",
        ],
        check=True,
    )

    assert (out_dir / "reports" / "editorial" / "2026-06-18.md").exists()
    assert (out_dir / "agent-runs" / "2026-06-18.json").exists()


def test_run_editorial_agent_cli_no_longer_exposes_sdk_transition_flag():
    result = subprocess.run(
        [sys.executable, "scripts/run_editorial_agent.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--sdk-backend" not in result.stdout
