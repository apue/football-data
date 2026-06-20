from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_data.calibration import discover_potm_evidence_candidates
from football_data.demo import build_demo_site
from football_data.editorial import (
    build_editorial_report,
    render_editorial_markdown_file,
    write_editorial_artifacts,
)
from football_data.firecrawl import search_firecrawl


DEFAULT_OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_AGENT_TIMEOUT_SECONDS = "90"

DEFAULT_MODELS = {
    "orchestrator": "deepseek-ai/DeepSeek-V4-Pro",
    "research": "deepseek-ai/DeepSeek-V4-Flash",
    "selection": "deepseek-ai/DeepSeek-V4-Pro",
    "zh_writer": "zai-org/GLM-5.2",
    "zh_editor": "Qwen/Qwen3.5-397B-A17B",
    "en_writer": "deepseek-ai/DeepSeek-V4-Flash",
    "en_editor": "deepseek-ai/DeepSeek-V4-Pro",
    "fact_check": "deepseek-ai/DeepSeek-V4-Pro",
}


MODEL_ENV_KEYS = {
    "orchestrator": "EDITORIAL_ORCHESTRATOR_MODEL",
    "research": "EDITORIAL_RESEARCH_MODEL",
    "selection": "EDITORIAL_SELECTION_MODEL",
    "zh_writer": "EDITORIAL_ZH_WRITER_MODEL",
    "zh_editor": "EDITORIAL_ZH_EDITOR_MODEL",
    "en_writer": "EDITORIAL_EN_WRITER_MODEL",
    "en_editor": "EDITORIAL_EN_EDITOR_MODEL",
    "fact_check": "EDITORIAL_FACT_CHECK_MODEL",
}


@dataclass(frozen=True)
class EditorialAgentConfig:
    api_key: str
    base_url: str
    models: dict[str, str]
    loaded_keys: list[str]
    tracing_disabled: bool = True
    timeout_seconds: float = 90.0


class AgentTextClient:
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
    ) -> str:
        raise NotImplementedError


class AgentCallTimeout(TimeoutError):
    pass


class SdkAgentTextClient(AgentTextClient):
    def __init__(self, config: EditorialAgentConfig) -> None:
        self.config = config

    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
    ) -> str:
        return asyncio.run(
            self._complete_async(
                role=role,
                model=model,
                instructions=instructions,
                user_input=user_input,
            )
        )

    async def _complete_async(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
    ) -> str:
        from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
        from openai import AsyncOpenAI

        set_tracing_disabled(self.config.tracing_disabled)
        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        )
        sdk_model = OpenAIChatCompletionsModel(model=model, openai_client=client)
        agent = Agent(name=role, instructions=instructions, model=sdk_model)
        result = await asyncio.wait_for(
            Runner.run(agent, user_input, max_turns=3),
            timeout=self.config.timeout_seconds,
        )
        return str(result.final_output)


class OpenAIChatCompletionsTextClient(AgentTextClient):
    def __init__(self, config: EditorialAgentConfig) -> None:
        self.config = config

    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            temperature=0.4 if "writer" in role or "editor" in role else 0,
            max_tokens=3000,
        )
        return response.choices[0].message.content or ""


class FakeEditorialAgentClient(AgentTextClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
    ) -> str:
        payload = json.loads(user_input)
        if role == "fact_check":
            return json.dumps({"status": "pass", "warnings": []})
        language = payload["language"]
        items = []
        for choice in payload["choices"]:
            player_name = choice["player_name"]
            if language == "zh":
                title = f"{player_name} 的数据理由"
                body = f"{player_name} 这场的入选理由很直接：关键动作和整体贡献都能对上。"
            else:
                title = f"{player_name} made the case"
                body = f"{player_name} earns the pick because the decisive actions and wider profile line up."
            items.append(
                {
                    "award_type": choice["award_type"],
                    "player_name": player_name,
                    "title": title,
                    "body": body,
                }
            )
        return json.dumps({"items": items, "warnings": []}, ensure_ascii=False)


def load_editorial_agent_config(
    env_path: str | Path = ".env.local",
    *,
    require_credentials: bool = True,
) -> EditorialAgentConfig:
    env = _load_env(env_path)
    api_key = env.get("OPENAI_API_KEY", "")
    base_url = env.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    if require_credentials and not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    models = {
        role: env.get(env_key, DEFAULT_MODELS[role])
        for role, env_key in MODEL_ENV_KEYS.items()
    }
    loaded_keys = [
        key
        for key in [
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            *MODEL_ENV_KEYS.values(),
        ]
        if key in env
    ]
    return EditorialAgentConfig(
        api_key=api_key,
        base_url=base_url,
        models=models,
        loaded_keys=loaded_keys,
        timeout_seconds=float(env.get("EDITORIAL_AGENT_TIMEOUT_SECONDS", DEFAULT_AGENT_TIMEOUT_SECONDS)),
    )


def run_editorial_agent(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    scoring_config_path: str | Path = "config/scoring/v0.3.json",
    style_dir: str | Path = ".agents/editorial-skills",
    env_path: str | Path = ".env.local",
    client: AgentTextClient | None = None,
    research: bool = True,
    rebuild_homepage: bool = True,
) -> dict[str, Any]:
    config = load_editorial_agent_config(env_path, require_credentials=client is None)
    text_client = client or OpenAIChatCompletionsTextClient(config)

    report = build_editorial_report(
        db_path,
        match_date=match_date,
        scoring_config_path=scoring_config_path,
    )
    write_editorial_artifacts(report, site_dir=site_dir, reports_dir=reports_dir)

    paths = _artifact_paths(site_dir, reports_dir, match_date)
    evidence = _load_json(paths["evidence"])
    fact_bank = _load_json(paths["fact_bank"])
    brief_en = _load_json(paths["brief_en"])
    external_evidence = _external_evidence(
        db_path=db_path,
        match_date=match_date,
        env_path=env_path,
        research=research,
    )
    paths["external_evidence"].write_text(
        json.dumps(external_evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    style_packs = _load_style_packs(style_dir)
    call_records: list[dict[str, Any]] = []

    zh_final = _generate_language_copy(
        client=text_client,
        language="zh",
        choices=fact_bank["choices"],
        identity_choices=report["choices"],
        evidence=evidence,
        external_evidence=external_evidence,
        style_packs=style_packs,
        writer_model=config.models["zh_writer"],
        editor_model=config.models["zh_editor"],
        call_records=call_records,
    )

    en_final = _generate_language_copy(
        client=text_client,
        language="en",
        choices=brief_en["choices"],
        identity_choices=report["choices"],
        evidence=evidence,
        external_evidence=external_evidence,
        style_packs=style_packs,
        writer_model=config.models["en_writer"],
        editor_model=config.models["en_editor"],
        call_records=call_records,
    )

    markdown_text = _render_agent_markdown(
        report=report,
        en_copy=en_final,
        zh_copy=zh_final,
    )
    paths["markdown"].write_text(markdown_text, encoding="utf-8")

    deterministic_warnings = _deterministic_fact_check(evidence, markdown_text)
    try:
        llm_fact_check = _call_json(
            text_client,
            role="fact_check",
            model=config.models["fact_check"],
            instructions=_fact_check_instructions(style_packs),
            payload={
                "match_date": match_date,
                "evidence": evidence,
                "external_evidence": external_evidence,
                "markdown": markdown_text,
                "deterministic_warnings": deterministic_warnings,
            },
            call_records=call_records,
            timeout_seconds=config.timeout_seconds,
        )
    except AgentCallTimeout as exc:
        llm_fact_check = {
            "status": "timeout",
            "warnings": [str(exc)],
        }
    llm_warnings = _filter_llm_warnings(markdown_text, llm_fact_check.get("warnings", []))
    llm_status = llm_fact_check.get("status", "pass") if llm_warnings else "pass"
    if call_records and call_records[-1].get("role") == "fact_check":
        call_records[-1]["warnings"] = llm_warnings
        call_records[-1]["status"] = llm_status
    fact_check = {
        "status": "fail" if deterministic_warnings else ("warning" if llm_warnings else "pass"),
        "deterministic_status": "fail" if deterministic_warnings else "pass",
        "llm_status": llm_status,
        "warnings": [*deterministic_warnings, *llm_warnings],
    }
    if fact_check["deterministic_status"] != "pass":
        raise RuntimeError(f"Editorial fact check failed: {fact_check['warnings']}")

    compiled = render_editorial_markdown_file(
        match_date=match_date,
        site_dir=site_dir,
        reports_dir=reports_dir,
    )
    if rebuild_homepage:
        build_demo_site(db_path, site_dir, manifests_dir)

    run_payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "success",
        "match_date": match_date,
        "scoring_version": report["scoring_version"],
        "research": {
            "enabled": research,
            "status": external_evidence.get("status"),
            "result_count": _external_result_count(external_evidence),
        },
        "selection_review": report.get("selection_review"),
        "models": {role: config.models[role] for role in sorted(config.models)},
        "tool_calls": call_records,
        "fact_check": fact_check,
        "artifacts": {
            "markdown": str(paths["markdown"]),
            "choices": str(paths["choices"]),
            "external_evidence": str(paths["external_evidence"]),
        },
        "choices": [
            {
                "award_type": choice["award_type"],
                "player_name": choice["player_name"],
                "team": choice["team"],
            }
            for choice in compiled["choices"]
        ],
    }
    run_path = Path(agent_runs_dir) / f"{match_date}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_payload


def _artifact_paths(
    site_dir: str | Path,
    reports_dir: str | Path,
    match_date: str,
) -> dict[str, Path]:
    site_path = Path(site_dir)
    dated_path = site_path / "editorial" / match_date
    return {
        "dated": dated_path,
        "markdown": Path(reports_dir) / "editorial" / f"{match_date}.md",
        "evidence": dated_path / "evidence.json",
        "fact_bank": dated_path / "fact_bank.zh.json",
        "brief_en": dated_path / "brief.en.json",
        "choices": dated_path / "choices.json",
        "external_evidence": dated_path / "external_evidence.json",
    }


def _external_evidence(
    *,
    db_path: str | Path,
    match_date: str,
    env_path: str | Path,
    research: bool,
) -> dict[str, Any]:
    if not research:
        return {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "match_date": match_date,
            "status": "skipped",
            "matches": [],
        }
    try:
        evidence = discover_potm_evidence_candidates(
            db_path=db_path,
            match_date=match_date,
            search_fn=lambda query, limit: search_firecrawl(
                query=query,
                limit=limit,
                env_path=env_path,
                timeout=30,
            ),
            limit=3,
        )
        evidence["status"] = "ok"
        return evidence
    except Exception as exc:
        return {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "match_date": match_date,
            "status": "failed",
            "error": str(exc)[:500],
            "matches": [],
        }


def _language_payload(
    *,
    language: str,
    choices: list[dict[str, Any]],
    evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    style_packs: dict[str, str],
) -> dict[str, Any]:
    return {
        "language": language,
        "match_date": evidence["match_date"],
        "scoring_version": evidence["scoring_version"],
        "choices": choices,
        "matches": evidence["matches"],
        "external_evidence": external_evidence,
        "style_packs": _style_subset(
            style_packs,
            ["football-editor-style", "source-policy", "scoring-policy"],
        ),
    }


def _generate_language_copy(
    *,
    client: AgentTextClient,
    language: str,
    choices: list[dict[str, Any]],
    identity_choices: list[dict[str, Any]],
    evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    style_packs: dict[str, str],
    writer_model: str,
    editor_model: str,
    call_records: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    writer_role = f"{language}_writer"
    editor_role = f"{language}_editor"
    for choice, identity_choice in zip(choices, identity_choices, strict=True):
        single_choice_payload = _language_payload(
            language=language,
            choices=[choice],
            evidence={
                **evidence,
                "choices": [
                    evidence_choice
                    for evidence_choice in evidence.get("choices", [])
                    if evidence_choice.get("award_type") == choice.get("award_type")
                    and evidence_choice.get("player_name") == choice.get("player_name")
                ],
            },
            external_evidence=external_evidence,
            style_packs=style_packs,
        )
        draft = _call_json(
            client,
            role=writer_role,
            model=writer_model,
            instructions=_writer_instructions(language, style_packs),
            payload=single_choice_payload,
            call_records=call_records,
        )
        edited = _call_json(
            client,
            role=editor_role,
            model=editor_model,
            instructions=_editor_instructions(language, style_packs),
            payload={
                "language": language,
                "choices": [choice],
                "draft": draft,
                "style_packs": _style_subset(
                    style_packs,
                    ["anti-translationese", "human-writing-zh"]
                    if language == "zh"
                    else ["football-editor-style"],
                ),
            },
            call_records=call_records,
        )
        item = _first_copy_item(edited, identity_choice)
        if item:
            items.append(item)
    return {"items": items, "warnings": []}


def _first_copy_item(payload: dict[str, Any], identity_choice: dict[str, Any]) -> dict[str, Any] | None:
    items = _candidate_copy_items(payload)
    if not items or not isinstance(items[0], dict):
        return None
    item = dict(items[0])
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if not title or not body:
        return None
    item["award_type"] = identity_choice["award_type"]
    item["player_name"] = identity_choice["player_name"]
    item["title"] = title
    item["body"] = body
    return item


def _candidate_copy_items(payload: dict[str, Any]) -> list[Any]:
    direct = payload.get("items")
    if isinstance(direct, list):
        return direct
    draft = payload.get("draft")
    if isinstance(draft, dict) and isinstance(draft.get("items"), list):
        return draft["items"]
    output = payload.get("output")
    if isinstance(output, dict) and isinstance(output.get("items"), list):
        return output["items"]
    return []


def _call_json(
    client: AgentTextClient,
    *,
    role: str,
    model: str,
    instructions: str,
    payload: dict[str, Any],
    call_records: list[dict[str, Any]],
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    print(f"[editorial-agent] {role} -> {model}", file=sys.stderr, flush=True)
    user_input = json.dumps(payload, ensure_ascii=False)
    try:
        response = _complete_with_timeout(
            lambda: client.complete(
                role=role,
                model=model,
                instructions=instructions,
                user_input=user_input,
            ),
            timeout_seconds=timeout_seconds,
            role=role,
        )
    except AgentCallTimeout as exc:
        call_records.append(
            {
                "role": role,
                "model": model,
                "input_chars": len(user_input),
                "output_chars": 0,
                "warnings": [str(exc)],
                "status": "timeout",
            }
        )
        raise
    parsed = _extract_json_object(response)
    call_records.append(
        {
            "role": role,
            "model": model,
            "input_chars": len(user_input),
            "output_chars": len(response),
            "warnings": parsed.get("warnings", []),
        }
    )
    return parsed


def _complete_with_timeout(
    call: Any,
    *,
    timeout_seconds: float | None,
    role: str,
) -> str:
    if timeout_seconds is None or timeout_seconds <= 0:
        return str(call())

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _handle_timeout(_signum: int, _frame: Any) -> None:
        raise AgentCallTimeout(f"{role} timed out after {timeout_seconds:g} seconds")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return str(call())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _writer_instructions(language: str, style_packs: dict[str, str]) -> str:
    if language == "zh":
        return "\n\n".join(
            [
                "你是中文足球数据编辑。只根据输入 JSON 写作，不要编造助攻、视频观察或外部评价。",
                "返回严格 JSON：{\"items\":[{\"award_type\":\"...\",\"player_name\":\"...\",\"title\":\"...\",\"body\":\"...\"}],\"warnings\":[]}",
                "每个 body 只写一段，最多带 2-3 个关键数字。不要翻译英文句式。",
                "不要写需要看录像才能证明的总括句，例如“几乎都从他脚下经过”“完全掌控”“没有办法限制他”。",
                _style_subset(style_packs, ["human-writing-zh", "anti-translationese", "football-editor-style"]).get("joined", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are a football data editor. Write compact English editorial copy from the input JSON only.",
            "Return strict JSON: {\"items\":[{\"award_type\":\"...\",\"player_name\":\"...\",\"title\":\"...\",\"body\":\"...\"}],\"warnings\":[]}",
            "One paragraph per body. Use at most 2-3 key numbers. Do not invent assists, video observations, or outside ratings.",
            "Avoid unsupported totalizing phrases such as \"no answer\", \"all afternoon\", \"controlled everything\", or \"every attack\".",
            style_packs.get("football-editor-style", ""),
        ]
    )


def _editor_instructions(language: str, style_packs: dict[str, str]) -> str:
    if language == "zh":
        return "\n\n".join(
            [
                "你是终审中文体育编辑。只润色输入 draft，不新增事实。",
                "返回同样 JSON schema。删掉翻译腔、空话和过度数据罗列。",
                "删掉“几乎都”“完全掌控”“没有办法限制他”等没有结构化证据支撑的总括句。",
                _style_subset(style_packs, ["human-writing-zh", "anti-translationese"]).get("joined", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are the final English editor. Polish the draft without adding facts.",
            "Return the same JSON schema. Keep the copy compact and editorial, not a metric table.",
            "Remove unsupported totalizing phrases such as \"no answer\", \"all afternoon\", \"controlled everything\", or \"every attack\".",
            style_packs.get("football-editor-style", ""),
        ]
    )


def _fact_check_instructions(style_packs: dict[str, str]) -> str:
    return "\n\n".join(
        [
            "You are a fact-checking editor. Check the Markdown against evidence JSON.",
            "Return strict JSON: {\"status\":\"pass\"|\"fail\",\"warnings\":[\"...\"]}.",
            "Fail unsupported assists, invented source claims, implied video review, wrong scorelines, or unsupported metrics.",
            style_packs.get("fact-check-rules", ""),
        ]
    )


def _render_agent_markdown(
    *,
    report: dict[str, Any],
    en_copy: dict[str, Any],
    zh_copy: dict[str, Any],
) -> str:
    en_items = _copy_by_choice(en_copy)
    zh_items = _copy_by_choice(zh_copy)
    matches_by_key = {str(match["match_key"]): match for match in report["matches"]}
    lines = [
        f"# Editor's Choices - {report['match_date']}",
        "",
        f"Scoring version: `{report['scoring_version']}`",
        "",
        "Data-informed selections from the structured PMSR dataset. These are not official FIFA awards.",
        "",
        "## Matches",
        "",
    ]
    for match in report["matches"]:
        lines.append(
            f"- Match {match['match_no']}: {match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}"
        )
    lines.extend(["", "## Choices", ""])
    for choice in report["choices"]:
        key = _choice_key(choice)
        en = en_items.get(key) or _fallback_copy(choice, "en")
        zh = zh_items.get(key) or _fallback_copy(choice, "zh")
        match = matches_by_key.get(str(choice["match_key"]))
        lines.extend(
            [
                f"### {choice['award_label']['en']}: {choice['player_name']}",
                "",
                f"_{_match_label(choice, match)}_",
                "",
                "#### English",
                "",
                f"**{en['title']}**",
                "",
                en["body"],
                "",
                "#### 中文",
                "",
                f"**{zh['title']}**",
                "",
                zh["body"],
                "",
                "Evidence: " + ", ".join(choice["evidence_chips"]["en"]),
                "",
                "依据：" + "，".join(choice["evidence_chips"]["zh"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _copy_by_choice(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    items = payload.get("items", [])
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("award_type") or ""), str(item.get("player_name") or ""))
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if key[0] and key[1] and title and body:
            by_key[key] = {"title": title, "body": body}
    return by_key


def _choice_key(choice: dict[str, Any]) -> tuple[str, str]:
    return (str(choice["award_type"]), str(choice["player_name"]))


def _fallback_copy(choice: dict[str, Any], language: str) -> dict[str, str]:
    draft = choice.get("draft", {}).get(language)
    if isinstance(draft, dict) and draft.get("title") and draft.get("body"):
        return {"title": str(draft["title"]), "body": str(draft["body"])}
    if language == "zh":
        chips = "，".join(str(chip) for chip in choice.get("evidence_chips", {}).get("zh", []))
        return {
            "title": f"{choice['player_name']}：{choice['award_label']['zh']}",
            "body": f"结构化证据显示他值得入选：{chips or '详见 fact_bank.zh.json'}。",
        }
    return {
        "title": f"{choice['player_name']}: {choice['award_label']['en']}",
        "body": "Structured evidence supports this selection.",
    }


def _match_label(choice: dict[str, Any], match: dict[str, Any] | None) -> str:
    if not match:
        return f"{choice['team']} vs {choice['opponent']} · Match {choice['match_no']}"
    return f"{match['home_team']} vs {match['away_team']} · Match {match['match_no']}"


def _deterministic_fact_check(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    if re.search(r"\bassist(s|ed)?\b|助攻", markdown_text, flags=re.IGNORECASE):
        warnings.append("Copy mentions assists, which are not available in current PMSR evidence.")
    if re.search(r"\bcome(?:s)? from behind\b|\bcomeback\b|反超|逆转", markdown_text, flags=re.IGNORECASE):
        warnings.append(
            "Copy makes a comeback or come-from-behind claim, but current evidence does not "
            "carry an explicit comeback-goal field."
        )
    if re.search(r"几乎每一次|每一次向前|几乎都|全由他|从头到尾|绝非运气|会更早被", markdown_text):
        warnings.append(
            "Copy uses overbroad attribution that would need video review or stronger evidence."
        )
    matches_by_key = {
        str(match.get("match_key")): match
        for match in evidence.get("matches", [])
        if match.get("match_key")
    }
    for choice in evidence.get("choices", []):
        if str(choice["player_name"]) not in markdown_text:
            warnings.append(f"Missing player name in Markdown: {choice['player_name']}")
        player_goals = _choice_component_value(choice, "goals")
        match = matches_by_key.get(str(choice.get("match_key")))
        team_goals = _team_goals_for_choice(choice, match)
        if player_goals and team_goals and player_goals < team_goals:
            team = re.escape(str(choice.get("team", "")))
            all_goals_patterns = [
                rf"\ball\s+(?:\w+|\d+)\s+goals\s+for\s+{team}\b",
                rf"\bevery\s+goal\s+for\s+(?:his\s+team|{team})\b",
                r"包办.*全部.*进球",
            ]
            if any(re.search(pattern, markdown_text, flags=re.IGNORECASE) for pattern in all_goals_patterns):
                warnings.append(
                    f"Copy claims all team goals for {choice['player_name']}, "
                    f"but evidence has {player_goals:g} of {team_goals:g} team goals."
                )
    return warnings


def _choice_component_value(choice: dict[str, Any], metric: str) -> float:
    for component in choice.get("score_components", []):
        if component.get("metric") == metric:
            return float(component.get("value") or 0)
    return 0.0


def _team_goals_for_choice(choice: dict[str, Any], match: dict[str, Any] | None) -> float:
    if not match:
        return 0.0
    team = choice.get("team")
    if team == match.get("home_team"):
        return float(match.get("home_score") or 0)
    if team == match.get("away_team"):
        return float(match.get("away_score") or 0)
    return 0.0


def _filter_llm_warnings(markdown_text: str, warnings: list[str]) -> list[str]:
    filtered: list[str] = []
    lower_markdown = markdown_text.lower()
    for warning in warnings:
        lower_warning = str(warning).lower()
        if "assist" in lower_warning and "assist" not in lower_markdown and "助攻" not in markdown_text:
            continue
        filtered.append(str(warning))
    return filtered


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Agent did not return JSON: {text[:500]}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Agent JSON response must be an object")
    return value


def _load_style_packs(style_dir: str | Path) -> dict[str, str]:
    directory = Path(style_dir)
    packs: dict[str, str] = {}
    if not directory.exists():
        return packs
    for path in sorted(directory.glob("*.md")):
        packs[path.stem] = path.read_text(encoding="utf-8")
    return packs


def _style_subset(style_packs: dict[str, str], names: list[str]) -> dict[str, str]:
    subset = {name: style_packs[name] for name in names if name in style_packs}
    subset["joined"] = "\n\n".join(subset.values())
    return subset


def _external_result_count(external_evidence: dict[str, Any]) -> int:
    total = 0
    for match in external_evidence.get("matches", []):
        if isinstance(match, dict):
            total += len(match.get("results", []))
    return total


def _load_env(path: str | Path) -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = Path(path)
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", *MODEL_ENV_KEYS.values()]:
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
