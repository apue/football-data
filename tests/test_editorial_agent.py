import json
import subprocess
import sys
from pathlib import Path

from football_data.editorial_agent import (
    AgentCompletionOutcome,
    AgentCompletionRequest,
    AgentTextClient,
    _compact_editor_instructions,
    _deterministic_fact_check,
    _fallback_copy,
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
        if role == "revision_editor":
            choice = payload["choices"][0]
            current = payload.get("current_copy", {}).get("items", [{}])[0]
            return json.dumps(
                {
                    "items": [
                        {
                            "award_type": choice["award_type"],
                            "player_name": choice["player_name"],
                            "title": current.get("title") or f"{choice['player_name']} repaired",
                            "body": current.get("body") or f"{choice['player_name']} repaired body.",
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )
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

    def complete_many_settled(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[AgentCompletionOutcome]:
        self.batch_roles.append([request.role for request in requests])
        self.batch_concurrency.append(max_concurrency)
        return [
            AgentCompletionOutcome(
                response=self.complete(
                    role=request.role,
                    model=request.model,
                    instructions=request.instructions,
                    user_input=request.user_input,
                    output_type=request.output_type,
                )
            )
            for request in requests
        ]


class FailingCompactEditorBatchClient(BatchEditorialClient):
    def complete_many_settled(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[AgentCompletionOutcome]:
        self.batch_roles.append([request.role for request in requests])
        self.batch_concurrency.append(max_concurrency)
        outcomes: list[AgentCompletionOutcome] = []
        for index, request in enumerate(requests):
            if request.role == "zh_editor_agent" and index == 0:
                self.calls.append((request.role, request.model))
                self.payloads.setdefault(request.role, []).append(json.loads(request.user_input))
                outcomes.append(AgentCompletionOutcome(error="zh_editor_agent timed out after 90 seconds"))
                continue
            outcomes.append(
                AgentCompletionOutcome(
                    response=self.complete(
                        role=request.role,
                        model=request.model,
                        instructions=request.instructions,
                        user_input=request.user_input,
                        output_type=request.output_type,
                    )
                )
            )
        return outcomes


class DeterministicRepairClient(FakeEditorialClient):
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
        if role == "en_editor_agent":
            choice = payload["choices"][0]
            body = (
                "MOHAMED SALAH completed 7 line-breaking runs."
                if choice["player_name"] == "MOHAMED SALAH"
                else f"{choice['player_name']} belongs here."
            )
            return json.dumps(
                {
                    "items": [
                        {
                            "award_type": choice["award_type"],
                            "player_name": choice["player_name"],
                            "title": f"{choice['player_name']} initial",
                            "body": body,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )
        if role == "revision_editor":
            choice = payload["choices"][0]
            language = payload["language"]
            body = (
                "MOHAMED SALAH completed 7 line breaks."
                if language == "en"
                else "萨拉赫完成7次打穿防线。"
            )
            return json.dumps(
                {
                    "items": [
                        {
                            "award_type": choice["award_type"],
                            "player_name": choice["player_name"],
                            "title": f"{choice['player_name']} repaired",
                            "body": body,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )
        return super().complete(
            role=role,
            model=model,
            instructions=instructions,
            user_input=user_input,
            output_type=output_type,
        )


class BadFlowCopyClient(FakeEditorialClient):
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
        language = payload["language"]
        items = []
        for choice in payload["choices"]:
            player_name = choice["player_name"]
            title = "The midfield connector" if language == "en" else "中场连接点"
            body = (
                f"{player_name} scored twice and added a stoppage-time winner."
                if language == "en"
                else f"{player_name} 两球一助，并在补时打入制胜球。"
            )
            items.append(
                {
                    "award_type": choice["award_type"],
                    "player_name": player_name,
                    "title": title,
                    "body": body,
                }
            )
        return json.dumps({"items": items, "warnings": []}, ensure_ascii=False)


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
        language = payload["language"]
        player_name = payload["choices"][0]["player_name"]
        if language == "zh":
            item = {
                "award_type": "changed",
                "player_name": "改名",
                "title": f"{player_name} 中文标题",
                "body": "中文正文。",
            }
        else:
            item = {
                "award_type": "changed",
                "player_name": "Renamed",
                "title": f"{player_name} English title",
                "body": "English body.",
            }
        return json.dumps({"items": [item], "warnings": []}, ensure_ascii=False)


class ReviewRevisionClient(FakeEditorialClient):
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
        if role == "revision_editor":
            choice = payload["choices"][0]
            language = payload["language"]
            player_name = choice["player_name"]
            title = (
                "15次夺回球权，防守贡献更清楚"
                if language == "zh"
                else "The ball-winning case"
            )
            body = (
                "佛得角2-2乌拉圭，PICO LOPES用15次夺回球权撑起这张防守卡。"
                if language == "zh"
                else "PICO LOPES made 15 possession regains in Cabo Verde 2-2 Uruguay."
            )
            return json.dumps(
                {
                    "items": [
                        {
                            "award_type": choice["award_type"],
                            "player_name": player_name,
                            "title": title,
                            "body": body,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )
        return super().complete(
            role=role,
            model=model,
            instructions=instructions,
            user_input=user_input,
            output_type=output_type,
        )


def test_load_editorial_agent_config_uses_openai_base_url_only(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY='secret'",
                "OPENAI_BASE_URL=https://api.example.test/v1",
                "OPEN_BASE_URL=https://wrong.example.test/v1",
                "EDITORIAL_ZH_EDITOR_MODEL=zh-editor",
                "EDITORIAL_REVISION_EDITOR_MODEL=revision-editor",
                "EDITORIAL_AGENT_MAX_CONCURRENCY=5",
                "EDITORIAL_AGENT_MAX_ATTEMPTS=4",
            ]
        ),
        encoding="utf-8",
    )

    config = load_editorial_agent_config(env_path)

    assert config.api_key == "secret"
    assert config.base_url == "https://api.example.test/v1"
    assert config.models == {
        "zh_editor": "zh-editor",
        "en_editor": "deepseek-ai/DeepSeek-V4-Flash",
        "revision_editor": "revision-editor",
    }
    assert config.max_concurrency == 5
    assert config.max_attempts == 4
    assert "OPEN_BASE_URL" not in config.loaded_keys
    assert "EDITORIAL_ZH_WRITER_MODEL" not in config.loaded_keys


def test_load_editorial_agent_config_reads_process_environment(tmp_path, monkeypatch):
    env_path = tmp_path / "missing.env"
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("EDITORIAL_EN_EDITOR_MODEL", "env-en-editor")
    monkeypatch.setenv("EDITORIAL_AGENT_MAX_CONCURRENCY", "4")
    monkeypatch.setenv("EDITORIAL_AGENT_MAX_ATTEMPTS", "3")

    config = load_editorial_agent_config(env_path)

    assert config.api_key == "env-secret"
    assert config.base_url == "https://api.example.test/v1"
    assert config.models["en_editor"] == "env-en-editor"
    assert config.max_concurrency == 4
    assert config.max_attempts == 3


def test_load_editorial_agent_config_uses_default_base_url_and_models(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text("OPENAI_API_KEY='secret'\n", encoding="utf-8")

    config = load_editorial_agent_config(env_path)

    assert config.base_url == "https://api.siliconflow.cn/v1"
    assert config.models == {
        "zh_editor": "zai-org/GLM-5.2",
        "en_editor": "deepseek-ai/DeepSeek-V4-Flash",
        "revision_editor": "deepseek-ai/DeepSeek-V4-Flash",
    }
    assert config.max_concurrency == 6
    assert config.max_attempts == 1


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

    assert any("go-ahead" in warning or "反超" in warning for warning in warnings)


def test_deterministic_fact_check_blocks_unsupported_opening_goal_claim():
    evidence = {
        "choices": [
            {
                "player_name": "Agustin CANOBBIO",
                "team": "Uruguay",
                "flow_context": {
                    "allowed_claims": {
                        "en": ["go-ahead goal"],
                        "zh": ["取得领先"],
                    }
                },
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "### Player of the Day: Agustin CANOBBIO\n\n卡诺比奥为乌拉圭首开纪录。",
    )

    assert any("opening goal" in warning or "首开纪录" in warning for warning in warnings)


def test_deterministic_fact_check_blocks_unsupported_winner_claim():
    evidence = {
        "choices": [
            {
                "player_name": "Lamine YAMAL",
                "team": "Spain",
                "flow_context": {
                    "allowed_claims": {
                        "en": ["opening goal", "go-ahead goal"],
                        "zh": ["首开纪录", "取得领先"],
                    }
                },
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "### Player of the Day: Lamine YAMAL\n\n第10分钟，亚马尔打入制胜球。",
    )

    assert any("winner" in warning or "制胜" in warning for warning in warnings)


def test_deterministic_fact_check_allows_supported_comeback_claim():
    evidence = {
        "matches": [
            {
                "match_key": "FIFA-2026-M33-GER-CIV",
                "home_team": "Germany",
                "away_team": "Côte d'Ivoire",
                "home_score": 2,
                "away_score": 1,
            }
        ],
        "match_flows": {
            "FIFA-2026-M33-GER-CIV": {
                "home_came_from_behind_to_win": True,
                "away_came_from_behind_to_win": False,
            }
        },
        "choices": [
            {
                "match_key": "FIFA-2026-M33-GER-CIV",
                "player_name": "Deniz UNDAV",
                "team": "Germany",
                "flow_context": {
                    "allowed_claims": {
                        "en": ["comeback win", "comeback winner", "93' stoppage-time winner"],
                        "zh": ["逆转取胜", "逆转制胜", "93' 补时制胜"],
                    }
                },
                "score_components": [
                    {"metric": "comeback_winner", "value": 1},
                    {"metric": "late_match_winning_goal", "value": 1},
                ],
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "\n".join(
            [
                "### Player of the Day: Deniz UNDAV",
                "Undav scored both goals in a 2-1 comeback win.",
                "#### 中文",
                "恩达夫补时制胜，德国完成逆转取胜。",
            ]
        ),
    )

    assert not any("comeback" in warning for warning in warnings)


def test_deterministic_fact_check_catches_overbroad_editorial_claims():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": []},
        "南非的每一次向前几乎都经过他的脚下，整场节奏全由他掌控。",
    )

    assert any("overbroad" in warning for warning in warnings)


def test_deterministic_fact_check_catches_all_chances_converted_overclaim():
    evidence = {
        "matches": [],
        "choices": [
            {
                "player_name": "Ayase UEDA",
                "metrics": {"shots": 5, "goals": 2},
                "score_components": [{"metric": "goals", "value": 2}],
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "\n".join(
            [
                "### Player of the Day: Ayase UEDA",
                "#### 中文",
                "两次机会全部打进，射门质量够硬。",
            ]
        ),
    )

    assert any("all chances" in warning for warning in warnings)


def test_deterministic_fact_check_catches_unsupported_tactical_overreads():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": [{"player_name": "Joshua KIMMICH"}]},
        "\n".join(
            [
                "### Progression Engine: Joshua KIMMICH",
                "#### 中文",
                "他反复把球从压力里带出来，是球队最稳定的推进出口。",
            ]
        ),
    )

    assert any("unsupported tactical detail" in warning for warning in warnings)


def test_deterministic_fact_check_catches_generic_midfield_connector_overread():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": [{"player_name": "Maxi ARAUJO"}]},
        "\n".join(
            [
                "### Player of the Day: Maxi ARAUJO",
                "#### English",
                "The midfield connector was found 8 times in dangerous areas.",
            ]
        ),
    )

    assert any("unsupported tactical detail" in warning for warning in warnings)


def test_deterministic_fact_check_catches_position_overclaim():
    evidence = {
        "matches": [],
        "choices": [
            {
                "player_name": "Felix NMECHA",
                "position": "MF",
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "\n".join(
            [
                "### Defensive Pick: Felix NMECHA",
                "#### English",
                "The defender who kept resetting attacks.",
            ]
        ),
    )

    assert any("position" in warning for warning in warnings)


def test_deterministic_fact_check_catches_goalkeeper_saved_outcome_overclaim():
    evidence = {
        "matches": [],
        "choices": [
            {
                "award_type": "goalkeeper_watch",
                "player_name": "Alireza BEIRANVAND",
                "position": "GK",
            }
        ],
    }

    warnings = _deterministic_fact_check(
        evidence,
        "\n".join(
            [
                "### Goalkeeper Watch: Alireza BEIRANVAND",
                "#### English",
                "He required eight saves and turned aside all seven shots on target.",
                "#### 中文",
                "8次射门被他挡出。",
            ]
        ),
    )

    assert any("goalkeeper saves" in warning for warning in warnings)


def test_deterministic_fact_check_catches_in_behind_offer_conflation():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": [{"player_name": "Mikel OYARZABAL"}]},
        "\n".join(
            [
                "### Player of the Day: Mikel OYARZABAL",
                "#### 中文",
                "25次身后接应中有9次被队友找到。",
            ]
        ),
    )

    assert any("unsupported tactical detail" in warning for warning in warnings)


def test_deterministic_fact_check_catches_line_breaks_as_runs():
    warnings = _deterministic_fact_check(
        {
            "matches": [],
            "choices": [
                {
                    "player_name": "MOHAMED SALAH",
                    "metrics": {"line_breaks_completed": 7},
                }
            ],
        },
        "MOHAMED SALAH completed 7 line-breaking runs to keep the attack moving.",
    )

    assert any("unsupported tactical detail" in warning for warning in warnings)

    warnings = _deterministic_fact_check(
        {
            "matches": [],
            "choices": [
                {
                    "player_name": "MOHAMED SALAH",
                    "metrics": {"line_breaks_completed": 7},
                }
            ],
        },
        "MOHAMED SALAH completed 7 line-breaking passes to keep the attack moving.",
    )

    assert any("unsupported tactical detail" in warning for warning in warnings)


def test_deterministic_fact_check_catches_duplicate_choice_titles():
    warnings = _deterministic_fact_check(
        {"matches": [], "choices": [{"player_name": "A"}, {"player_name": "B"}]},
        "\n".join(
            [
                "### Player of the Day: A",
                "#### English",
                "**The constant threat behind**",
                "A body.",
                "#### 中文",
                "**甲**",
                "正文。",
                "### Player of the Day: B",
                "#### English",
                "**The constant threat behind**",
                "B body.",
                "#### 中文",
                "**乙**",
                "正文。",
            ]
        ),
    )

    assert any("Duplicate English title" in warning for warning in warnings)


def test_editorial_agent_prompts_explicitly_reject_overbroad_claims():
    zh_prompt = _compact_editor_instructions("zh", {})
    en_prompt = _compact_editor_instructions("en", {})

    assert "几乎" in zh_prompt
    assert "no answer" in en_prompt


def test_equaliser_assist_fallback_adds_editorial_value_without_repetition():
    choice = {
        "award_type": "player_of_the_day",
        "award_label": {"en": "Player of the Day", "zh": "每日最佳"},
        "player_name": "Maxi ARAUJO",
        "team": "Uruguay",
        "opponent": "Cabo Verde",
        "team_final_goals": 2,
        "opponent_final_goals": 2,
        "evidence_chips": {
            "en": ["equaliser", "assist"],
            "zh": ["扳平进球", "助攻"],
        },
        "metrics": {"goals": 1, "assists": 1},
    }

    en = _fallback_copy(choice, "en")
    zh = _fallback_copy(choice, "zh")

    assert "equaliser" in en["body"]
    assert "assist" in en["body"]
    assert "way back" in en["body"]
    assert "扳平球" in zh["body"]
    assert "助攻" in zh["body"]
    assert "两次直接参与进球" in zh["body"]


def test_goal_assist_fallback_uses_zh_name_and_keeps_goal_involvement():
    choice = {
        "award_type": "player_of_the_day",
        "award_label": {"en": "Player of the Day", "zh": "每日最佳"},
        "player_name": "MOHAMED SALAH",
        "team": "Egypt",
        "opponent": "New Zealand",
        "team_final_goals": 3,
        "opponent_final_goals": 1,
        "evidence_chips": {
            "en": ["match-winning goal", "assist"],
            "zh": ["逆转制胜", "助攻"],
        },
        "metrics": {"goals": 1, "assists": 1, "line_breaks_completed": 7},
    }

    en = _fallback_copy(choice, "en")
    zh = _fallback_copy(choice, "zh")

    assert "MOHAMED SALAH" not in zh["title"]
    assert "萨拉赫" in zh["title"]
    assert "助攻" in zh["body"]
    assert "逆转制胜球" in zh["body"]
    assert "打穿防线" in zh["body"]
    assert "scored" in en["body"]
    assert "assist" in en["body"]


def test_metric_fallback_copy_avoids_stale_ai_phrases():
    defensive_choice = {
        "award_type": "defensive_pick",
        "award_label": {"en": "Defensive Pick", "zh": "防守精选"},
        "player_name": "PICO LOPES",
        "team": "Cabo Verde",
        "opponent": "Uruguay",
        "team_final_goals": 2,
        "opponent_final_goals": 2,
        "evidence_chips": {"en": [], "zh": []},
        "metrics": {"possession_regains": 15, "possession_interrupted": 5, "blocks": 3},
    }
    progression_choice = {
        "award_type": "progression_pick",
        "award_label": {"en": "Progression Engine", "zh": "推进发动机"},
        "player_name": "MARAWAN ATTIA",
        "team": "Egypt",
        "opponent": "New Zealand",
        "team_final_goals": 3,
        "opponent_final_goals": 1,
        "evidence_chips": {"en": [], "zh": []},
        "metrics": {"line_breaks_completed": 31},
    }
    goalkeeper_choice = {
        "award_type": "goalkeeper_watch",
        "award_label": {"en": "Goalkeeper Watch", "zh": "门将关注"},
        "player_name": "Alireza BEIRANVAND",
        "team": "IR Iran",
        "opponent": "Belgium",
        "team_final_goals": 0,
        "opponent_final_goals": 0,
        "evidence_chips": {"en": [], "zh": []},
        "metrics": {"opponent_xg": 1.48, "opponent_attempts_on_target": 7},
    }

    zh_defensive = _fallback_copy(defensive_choice, "zh")
    zh_progression = _fallback_copy(progression_choice, "zh")
    zh_goalkeeper = _fallback_copy(goalkeeper_choice, "zh")

    combined = "\n".join(
        [
            zh_defensive["title"],
            zh_defensive["body"],
            zh_progression["title"],
            zh_progression["body"],
            zh_goalkeeper["title"],
            zh_goalkeeper["body"],
        ]
    )
    assert "反复把球权抢回来" not in combined
    assert "压力背景足够清楚" not in combined
    assert "全场31次打穿防线。" not in combined
    assert "15次夺回球权" in combined
    assert "31次打穿防线" in combined
    assert "7次射正" in combined


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
    pre_review_path = tmp_path / "reports" / "editorial" / "2026-06-18.pre-review.md"

    assert result["status"] == "success"
    assert markdown_path.exists()
    assert choices_path.exists()
    assert run_path.exists()
    assert external_path.exists()
    assert pre_review_path.exists()
    assert [call[0] for call in client.calls].count("zh_editor_agent") == 6
    assert [call[0] for call in client.calls].count("en_editor_agent") == 6
    assert "revision_editor" not in client.payloads

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "### Player of the Day:" in markdown
    assert "#### English" in markdown
    assert "#### 中文" in markdown
    assert "的中文标题" in markdown
    assert "Evidence:" not in markdown
    assert "依据：" not in markdown

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
        "zh_editor_agent",
        "en_editor_agent",
        "render_markdown_and_repair",
        "final_deterministic_validation",
        "compile_publish",
    ]
    assert all(node["status"] == "success" for node in run_payload["workflow"]["nodes"])
    assert run_payload["fact_check"]["status"] == "pass"
    assert run_payload["review_feedback"]["iterations"] == []
    assert run_payload["deterministic_repair"]["fallback_repairs"] == 0
    assert "publication_review" not in run_payload
    assert "fact_check_revisions" not in run_payload
    assert "OPENAI_API_KEY" not in json.dumps(run_payload)


def test_editorial_agent_batches_per_card_editor_calls(tmp_path):
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
        ["zh_editor_agent"] * 6,
        ["en_editor_agent"] * 6,
    ]
    assert client.batch_concurrency == [4, 4]
    node_summaries = {
        node["id"]: node["summary"]
        for node in result["workflow"]["nodes"]
    }
    assert node_summaries["zh_editor_agent"]["agent_calls"] == 6
    assert node_summaries["zh_editor_agent"]["max_concurrency"] == 4


def test_per_card_compact_editor_failure_falls_back_to_static_copy(tmp_path):
    client = FailingCompactEditorBatchClient()

    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=client,
        research=False,
        rebuild_homepage=False,
    )

    assert result["status"] == "success"
    zh_editor_node = next(
        node for node in result["workflow"]["nodes"] if node["id"] == "zh_editor_agent"
    )
    assert zh_editor_node["status"] == "success"
    assert any("zh_editor_agent failed" in warning for warning in zh_editor_node["warnings"])

    choices = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-18" / "choices.json").read_text(
            encoding="utf-8"
        )
    )
    assert choices["choices"]
    assert len(choices["choices"]) == len(result["choices"])


def test_deterministic_failure_triggers_targeted_repair_only_when_needed(tmp_path):
    client = DeterministicRepairClient()

    result = run_editorial_agent(
        match_date="2026-06-21",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=client,
        research=False,
        rebuild_homepage=False,
        max_review_loops=1,
    )

    markdown = (tmp_path / "reports" / "editorial" / "2026-06-21.md").read_text(encoding="utf-8")
    repair_node = next(
        node for node in result["workflow"]["nodes"] if node["id"] == "render_markdown_and_repair"
    )

    assert result["fact_check"]["status"] == "pass"
    assert "line-breaking runs" not in markdown
    assert "line breaks" in markdown
    assert [call[0] for call in client.calls].count("revision_editor") >= 1
    assert repair_node["summary"]["deterministic_repairs"] >= 1


def test_render_repair_replaces_factually_invalid_copy(tmp_path):
    result = run_editorial_agent(
        match_date="2026-06-21",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=BadFlowCopyClient(),
        research=False,
        rebuild_homepage=False,
    )

    markdown = (tmp_path / "reports" / "editorial" / "2026-06-21.md").read_text(
        encoding="utf-8"
    )
    evidence = json.loads(
        (tmp_path / "site" / "editorial" / "2026-06-21" / "evidence.json").read_text(
            encoding="utf-8"
        )
    )
    render_node = next(
        node for node in result["workflow"]["nodes"] if node["id"] == "render_markdown_and_repair"
    )

    assert result["status"] == "success"
    assert "scored twice and added a stoppage-time winner" not in markdown
    assert "两球一助，并在补时打入制胜球" not in markdown
    assert _deterministic_fact_check(evidence, markdown) == []
    assert render_node["summary"]["deterministic_repairs"] > 0


def test_external_review_feedback_revises_copy_and_keeps_pre_review(tmp_path):
    feedback_path = tmp_path / "codex-review.json"
    feedback_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "match_date": "2026-06-21",
                "reviewer": "codex",
                "status": "needs_revision",
                "comments": [
                    {
                        "id": "codex-1",
                        "player_name": "PICO LOPES",
                        "award_type": "defensive_pick",
                        "language": "zh",
                        "severity": "blocking",
                        "issue_type": "repetition",
                        "quote": "15次夺回球权，在防守端反复把球权抢回来",
                        "comment": "同一个事实重复说了两遍，改成一次事实加一句比赛价值。",
                        "constraint": "不要新增视频观察或站位判断。",
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    client = ReviewRevisionClient()

    result = run_editorial_agent(
        match_date="2026-06-21",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=client,
        research=False,
        rebuild_homepage=False,
        review_feedback_path=feedback_path,
        max_review_loops=2,
    )

    markdown_path = tmp_path / "reports" / "editorial" / "2026-06-21.md"
    pre_review_path = tmp_path / "reports" / "editorial" / "2026-06-21.pre-review.md"
    markdown = markdown_path.read_text(encoding="utf-8")
    pre_review = pre_review_path.read_text(encoding="utf-8")

    assert result["status"] == "success"
    assert pre_review_path.exists()
    assert "PICO LOPES" in pre_review
    assert "PICO LOPES用15次夺回球权撑起这张防守卡" not in pre_review
    assert "PICO LOPES用15次夺回球权撑起这张防守卡" in markdown
    assert "在防守端反复把球权抢回来" not in markdown
    assert [call[0] for call in client.calls].count("revision_editor") >= 1
    review_node = next(
        node for node in result["workflow"]["nodes"] if node["id"] == "render_markdown_and_repair"
    )
    assert review_node["summary"]["external_revisions"] == 1
    assert review_node["summary"]["external_comments"] == 1
    assert result["artifacts"]["pre_review_markdown"] == str(pre_review_path)


def test_compact_workflow_records_deterministic_fact_check_only(tmp_path):
    result = run_editorial_agent(
        match_date="2026-06-18",
        db_path="data/latest.sqlite",
        site_dir=tmp_path / "site",
        reports_dir=tmp_path / "reports",
        manifests_dir="manifests",
        agent_runs_dir=tmp_path / "agent-runs",
        client=FakeEditorialClient(),
        research=False,
        rebuild_homepage=False,
    )

    assert result["status"] == "success"
    assert result["fact_check"] == {
        "status": "pass",
        "deterministic_status": "pass",
        "llm_status": "skipped",
        "warnings": [],
    }


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


def test_editorial_agent_source_has_no_legacy_long_chain_roles():
    source = Path("football_data/editorial_agent.py").read_text(encoding="utf-8")

    for legacy_name in [
        "zh_writer",
        "en_writer",
        "zh_draft_fact_check",
        "en_draft_fact_check",
        "zh_final_editor",
        "en_final_editor",
        "publication_reviewer",
        "final_fact_check",
    ]:
        assert legacy_name not in source
