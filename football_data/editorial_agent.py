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
from typing import Any, Callable

from pydantic import BaseModel, Field

from football_data.calibration import discover_potm_evidence_candidates
from football_data.demo import build_demo_site
from football_data.editorial import (
    build_editorial_report,
    render_editorial_markdown_file,
    write_editorial_artifacts,
)
from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG
from football_data.firecrawl import search_firecrawl


DEFAULT_OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_AGENT_TIMEOUT_SECONDS = "90"
DEFAULT_AGENT_MAX_CONCURRENCY = "3"
DEFAULT_AGENT_MAX_ATTEMPTS = "2"

DEFAULT_MODELS = {
    "zh_writer": "zai-org/GLM-5.2",
    "zh_editor": "Qwen/Qwen3.5-397B-A17B",
    "en_writer": "deepseek-ai/DeepSeek-V4-Flash",
    "en_editor": "deepseek-ai/DeepSeek-V4-Pro",
    "fact_check": "deepseek-ai/DeepSeek-V4-Pro",
}


MODEL_ENV_KEYS = {
    "zh_writer": "EDITORIAL_ZH_WRITER_MODEL",
    "zh_editor": "EDITORIAL_ZH_EDITOR_MODEL",
    "en_writer": "EDITORIAL_EN_WRITER_MODEL",
    "en_editor": "EDITORIAL_EN_EDITOR_MODEL",
    "fact_check": "EDITORIAL_FACT_CHECK_MODEL",
}

CONTROL_ENV_KEYS = [
    "EDITORIAL_AGENT_TIMEOUT_SECONDS",
    "EDITORIAL_AGENT_MAX_CONCURRENCY",
    "EDITORIAL_AGENT_MAX_ATTEMPTS",
]


@dataclass(frozen=True)
class EditorialAgentConfig:
    api_key: str
    base_url: str
    models: dict[str, str]
    loaded_keys: list[str]
    tracing_disabled: bool = True
    timeout_seconds: float = 90.0
    max_concurrency: int = 3
    max_attempts: int = 2


@dataclass(frozen=True)
class AgentCompletionRequest:
    role: str
    model: str
    instructions: str
    user_input: str
    output_type: type[Any] | None = None


@dataclass(frozen=True)
class AgentCompletionOutcome:
    response: str | None = None
    error: str | None = None


class AgentCallError(RuntimeError):
    pass


class AgentTextClient:
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[Any] | None = None,
    ) -> str:
        raise NotImplementedError

    def complete_many(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[str]:
        outcomes = self.complete_many_settled(requests, max_concurrency=max_concurrency)
        responses: list[str] = []
        for outcome in outcomes:
            if outcome.error:
                raise AgentCallError(outcome.error)
            if outcome.response is None:
                raise AgentCallError("Agent returned no response")
            responses.append(outcome.response)
        return responses

    def complete_many_settled(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[AgentCompletionOutcome]:
        outcomes: list[AgentCompletionOutcome] = []
        for request in requests:
            try:
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
            except Exception as exc:
                outcomes.append(AgentCompletionOutcome(error=str(exc)[:1000]))
        return outcomes


class AgentCallTimeout(TimeoutError):
    pass


class EditorialCopyItem(BaseModel):
    award_type: str = Field(description="Award type from the input choice.")
    player_name: str = Field(description="Player name from the input choice.")
    title: str = Field(description="Short publishable title.")
    body: str = Field(description="One publishable body paragraph.")


class EditorialCopyOutput(BaseModel):
    items: list[EditorialCopyItem]
    warnings: list[str] = Field(default_factory=list)


class EditorialFactCheckOutput(BaseModel):
    status: str
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class EditorialWorkflowNode:
    id: str
    kind: str
    handler: Callable[[dict[str, Any]], dict[str, Any] | None]
    next_id: str | None = None
    model_key: str | None = None
    skills: tuple[str, ...] = ()
    max_attempts: int = 1


class AgentsSdkTextClient(AgentTextClient):
    def __init__(self, config: EditorialAgentConfig) -> None:
        self.config = config

    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[Any] | None = None,
    ) -> str:
        requests = [
            AgentCompletionRequest(
                role=role,
                model=model,
                instructions=instructions,
                user_input=user_input,
                output_type=output_type,
            )
        ]
        return self.complete_many(requests, max_concurrency=1)[0]

    def complete_many(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[str]:
        outcomes = self.complete_many_settled(requests, max_concurrency=max_concurrency)
        responses: list[str] = []
        for outcome in outcomes:
            if outcome.error:
                raise AgentCallError(outcome.error)
            if outcome.response is None:
                raise AgentCallError("Agent returned no response")
            responses.append(outcome.response)
        return responses

    def complete_many_settled(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int = 1,
    ) -> list[AgentCompletionOutcome]:
        return asyncio.run(
            self._complete_many_settled_async(
                requests,
                max_concurrency=max_concurrency,
            )
        )

    async def _complete_many_settled_async(
        self,
        requests: list[AgentCompletionRequest],
        *,
        max_concurrency: int,
    ) -> list[AgentCompletionOutcome]:
        from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
        from openai import AsyncOpenAI

        set_tracing_disabled(self.config.tracing_disabled)
        concurrency = max(1, max_concurrency)
        semaphore = asyncio.Semaphore(concurrency)
        async with AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        ) as client:
            tasks = [
                self._run_request_with_retry(
                    request,
                    client=client,
                    semaphore=semaphore,
                    Agent=Agent,
                    OpenAIChatCompletionsModel=OpenAIChatCompletionsModel,
                    Runner=Runner,
                )
                for request in requests
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        outcomes: list[AgentCompletionOutcome] = []
        for result in results:
            if isinstance(result, Exception):
                outcomes.append(AgentCompletionOutcome(error=str(result)[:1000]))
            else:
                outcomes.append(AgentCompletionOutcome(response=str(result)))
        return outcomes

    async def _run_request_with_retry(
        self,
        request: AgentCompletionRequest,
        *,
        client: Any,
        semaphore: asyncio.Semaphore,
        Agent: Any,
        OpenAIChatCompletionsModel: Any,
        Runner: Any,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(1, max(1, self.config.max_attempts) + 1):
            try:
                return await self._run_request(
                    request,
                    client=client,
                    semaphore=semaphore,
                    Agent=Agent,
                    OpenAIChatCompletionsModel=OpenAIChatCompletionsModel,
                    Runner=Runner,
                )
            except Exception as exc:
                last_exc = exc
                if attempt >= max(1, self.config.max_attempts):
                    break
                await asyncio.sleep(min(2.0, 0.5 * attempt))
        raise last_exc or AgentCallError(f"{request.role} failed")

    async def _run_request(
        self,
        request: AgentCompletionRequest,
        *,
        client: Any,
        semaphore: asyncio.Semaphore,
        Agent: Any,
        OpenAIChatCompletionsModel: Any,
        Runner: Any,
    ) -> str:
        async with semaphore:
            sdk_model = OpenAIChatCompletionsModel(model=request.model, openai_client=client)
            agent = Agent(
                name=request.role,
                instructions=request.instructions,
                model=sdk_model,
                output_type=request.output_type,
            )
            try:
                result = await asyncio.wait_for(
                    Runner.run(agent, request.user_input, max_turns=3),
                    timeout=self.config.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise AgentCallTimeout(
                    f"{request.role} timed out after {self.config.timeout_seconds:g} seconds"
                ) from exc
        final_output = result.final_output
        if isinstance(final_output, BaseModel):
            return final_output.model_dump_json()
        if isinstance(final_output, dict):
            return json.dumps(final_output, ensure_ascii=False)
        return str(final_output)


class FakeEditorialAgentClient(AgentTextClient):
    def complete(
        self,
        *,
        role: str,
        model: str,
        instructions: str,
        user_input: str,
        output_type: type[Any] | None = None,
    ) -> str:
        payload = json.loads(user_input)
        if role.endswith("fact_check"):
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
            *CONTROL_ENV_KEYS,
            *MODEL_ENV_KEYS.values(),
        ]
        if key in env
    ]
    max_concurrency = int(env.get("EDITORIAL_AGENT_MAX_CONCURRENCY", DEFAULT_AGENT_MAX_CONCURRENCY))
    max_attempts = int(env.get("EDITORIAL_AGENT_MAX_ATTEMPTS", DEFAULT_AGENT_MAX_ATTEMPTS))
    return EditorialAgentConfig(
        api_key=api_key,
        base_url=base_url,
        models=models,
        loaded_keys=loaded_keys,
        timeout_seconds=float(env.get("EDITORIAL_AGENT_TIMEOUT_SECONDS", DEFAULT_AGENT_TIMEOUT_SECONDS)),
        max_concurrency=max(1, max_concurrency),
        max_attempts=max(1, max_attempts),
    )


class EditorialWorkflowRunner:
    name = "editorial_state_graph"
    version = 1

    def __init__(
        self,
        *,
        match_date: str,
        db_path: str | Path,
        site_dir: str | Path,
        reports_dir: str | Path,
        manifests_dir: str | Path,
        scoring_config_path: str | Path,
        style_dir: str | Path,
        env_path: str | Path,
        text_client: AgentTextClient,
        config: EditorialAgentConfig,
        research: bool,
        rebuild_homepage: bool,
    ) -> None:
        self.match_date = match_date
        self.db_path = db_path
        self.site_dir = site_dir
        self.reports_dir = reports_dir
        self.manifests_dir = manifests_dir
        self.scoring_config_path = scoring_config_path
        self.style_dir = style_dir
        self.env_path = env_path
        self.text_client = text_client
        self.config = config
        self.research = research
        self.rebuild_homepage = rebuild_homepage
        self.nodes = self._build_nodes()

    def run(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "match_date": self.match_date,
            "node_runs": [],
        }
        node_by_id = {node.id: node for node in self.nodes}
        node = self.nodes[0]
        while node is not None:
            trace = self._run_node(node, state)
            state["node_runs"].append(trace)
            if trace["status"] == "failed":
                raise state["_workflow_exception"]
            node = node_by_id.get(node.next_id) if node.next_id else None
        return state

    def workflow_audit(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "nodes": state.get("node_runs", []),
        }

    def _build_nodes(self) -> list[EditorialWorkflowNode]:
        return [
            EditorialWorkflowNode("build_evidence", "python", self._build_evidence, "external_research"),
            EditorialWorkflowNode("external_research", "python", self._external_research, "zh_writer"),
            EditorialWorkflowNode(
                "zh_writer",
                "agent",
                self._zh_writer,
                "zh_draft_fact_check",
                model_key="zh_writer",
                skills=("human-writing-zh", "anti-translationese", "football-editor-style"),
            ),
            EditorialWorkflowNode(
                "zh_draft_fact_check",
                "agent",
                self._zh_draft_fact_check,
                "zh_final_editor",
                model_key="fact_check",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode(
                "zh_final_editor",
                "agent",
                self._zh_final_editor,
                "en_writer",
                model_key="zh_editor",
                skills=("human-writing-zh", "anti-translationese", "football-editor-style"),
            ),
            EditorialWorkflowNode(
                "en_writer",
                "agent",
                self._en_writer,
                "en_draft_fact_check",
                model_key="en_writer",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode(
                "en_draft_fact_check",
                "agent",
                self._en_draft_fact_check,
                "en_final_editor",
                model_key="fact_check",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode(
                "en_final_editor",
                "agent",
                self._en_final_editor,
                "render_markdown",
                model_key="en_editor",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode("render_markdown", "python", self._render_markdown, "final_deterministic_validation"),
            EditorialWorkflowNode(
                "final_deterministic_validation",
                "validator",
                self._final_deterministic_validation,
                "final_fact_check",
            ),
            EditorialWorkflowNode(
                "final_fact_check",
                "agent",
                self._final_fact_check,
                "compile_publish",
                model_key="fact_check",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode("compile_publish", "python", self._compile_publish),
        ]

    def _run_node(
        self,
        node: EditorialWorkflowNode,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        trace: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind,
            "status": "running",
            "max_attempts": self.config.max_attempts if node.kind == "agent" else node.max_attempts,
        }
        if node.model_key:
            trace["model"] = self.config.models[node.model_key]
        if node.skills:
            trace["skills"] = list(node.skills)
        try:
            output = node.handler(state) or {}
            trace.update(
                {
                    "status": "success",
                    "warnings": output.get("warnings", []),
                    "summary": output.get("summary", {}),
                }
            )
        except Exception as exc:
            state["_workflow_exception"] = exc
            trace.update(
                {
                    "status": "failed",
                    "warnings": [str(exc)[:1000]],
                }
            )
        return trace

    def _build_evidence(self, state: dict[str, Any]) -> dict[str, Any]:
        report = build_editorial_report(
            self.db_path,
            match_date=self.match_date,
            scoring_config_path=self.scoring_config_path,
        )
        write_editorial_artifacts(report, site_dir=self.site_dir, reports_dir=self.reports_dir)

        paths = _artifact_paths(self.site_dir, self.reports_dir, self.match_date)
        state.update(
            {
                "report": report,
                "paths": paths,
                "evidence": _load_json(paths["evidence"]),
                "fact_bank": _load_json(paths["fact_bank"]),
                "brief_en": _load_json(paths["brief_en"]),
                "style_packs": _load_style_packs(self.style_dir),
            }
        )
        return {
            "summary": {
                "choices": len(report["choices"]),
                "scoring_version": report["scoring_version"],
            }
        }

    def _external_research(self, state: dict[str, Any]) -> dict[str, Any]:
        external_evidence = _external_evidence(
            db_path=self.db_path,
            match_date=self.match_date,
            env_path=self.env_path,
            research=self.research,
        )
        state["external_evidence"] = external_evidence
        state["paths"]["external_evidence"].write_text(
            json.dumps(external_evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "summary": {
                "enabled": self.research,
                "status": external_evidence.get("status"),
                "result_count": _external_result_count(external_evidence),
            }
        }

    def _zh_writer(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._write_draft(state, "zh", state["fact_bank"]["choices"], "zh_writer", "zh_writer")

    def _en_writer(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._write_draft(state, "en", state["brief_en"]["choices"], "en_writer", "en_writer")

    def _zh_draft_fact_check(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._draft_fact_check(state, "zh", "zh_draft_fact_check", "zh_draft", "zh_draft_fact_check")

    def _en_draft_fact_check(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._draft_fact_check(state, "en", "en_draft_fact_check", "en_draft", "en_draft_fact_check")

    def _zh_final_editor(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._final_editor(
            state,
            "zh",
            state["fact_bank"]["choices"],
            "zh_final_editor",
            "zh_draft",
            "zh_draft_fact_check",
            "zh_final",
        )

    def _en_final_editor(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._final_editor(
            state,
            "en",
            state["brief_en"]["choices"],
            "en_final_editor",
            "en_draft",
            "en_draft_fact_check",
            "en_final",
        )

    def _write_draft(
        self,
        state: dict[str, Any],
        language: str,
        choices: list[dict[str, Any]],
        role: str,
        model_key: str,
    ) -> dict[str, Any]:
        items: list[dict[str, str]] = []
        warnings: list[str] = []
        requests = [
            {
                "role": role,
                "model": self.config.models[model_key],
                "instructions": _writer_instructions(language, state["style_packs"]),
                "payload": _language_payload(
                    language=language,
                    choices=[choice],
                    evidence=_evidence_for_choice(state["evidence"], identity_choice),
                    external_evidence=state["external_evidence"],
                    style_packs=state["style_packs"],
                ),
                "output_type": EditorialCopyOutput,
            }
            for choice, identity_choice in zip(choices, state["report"]["choices"], strict=True)
        ]
        drafts = _call_json_many(
            self.text_client,
            requests,
            max_concurrency=self.config.max_concurrency,
        )
        for draft, identity_choice in zip(drafts, state["report"]["choices"], strict=True):
            bound = _copy_output_bound_to_choices(draft, [identity_choice], language)
            items.extend(bound["items"])
            warnings.extend(str(warning) for warning in draft.get("warnings", []))
        state[f"{language}_draft"] = {"items": items, "warnings": warnings}
        return {
            "warnings": warnings,
            "summary": {
                "items": len(state[f"{language}_draft"]["items"]),
                "agent_calls": len(requests),
                "max_concurrency": self.config.max_concurrency,
            },
        }

    def _draft_fact_check(
        self,
        state: dict[str, Any],
        language: str,
        role: str,
        draft_key: str,
        output_key: str,
    ) -> dict[str, Any]:
        result = _call_json(
            self.text_client,
            role=role,
            model=self.config.models["fact_check"],
            instructions=_draft_fact_check_instructions(language, state["style_packs"]),
            payload={
                "language": language,
                "match_date": self.match_date,
                "evidence": state["evidence"],
                "external_evidence": state["external_evidence"],
                "draft": state[draft_key],
            },
            output_type=EditorialFactCheckOutput,
            timeout_seconds=self.config.timeout_seconds,
        )
        state[output_key] = {
            "status": result.get("status", "pass"),
            "warnings": result.get("warnings", []),
        }
        return {
            "warnings": state[output_key]["warnings"],
            "summary": {"status": state[output_key]["status"]},
        }

    def _final_editor(
        self,
        state: dict[str, Any],
        language: str,
        choices: list[dict[str, Any]],
        role: str,
        draft_key: str,
        fact_check_key: str,
        output_key: str,
    ) -> dict[str, Any]:
        items: list[dict[str, str]] = []
        warnings: list[str] = []
        draft_items = state[draft_key]["items"]
        requests: list[dict[str, Any]] = []
        for index, (choice, identity_choice) in enumerate(
            zip(choices, state["report"]["choices"], strict=True)
        ):
            draft_item = draft_items[index] if index < len(draft_items) else _fallback_copy(identity_choice, language)
            requests.append(
                {
                    "role": role,
                    "model": self.config.models["zh_editor" if language == "zh" else "en_editor"],
                    "instructions": _editor_instructions(language, state["style_packs"]),
                    "payload": {
                        "language": language,
                        "choices": [choice],
                        "draft": {"items": [draft_item]},
                        "draft_fact_check": state[fact_check_key],
                        "style_packs": _style_subset(
                            state["style_packs"],
                            ["anti-translationese", "human-writing-zh"]
                            if language == "zh"
                            else ["football-editor-style"],
                        ),
                    },
                    "output_type": EditorialCopyOutput,
                }
            )
        edits = _call_json_many(
            self.text_client,
            requests,
            max_concurrency=self.config.max_concurrency,
        )
        for index, (edited, identity_choice) in enumerate(zip(edits, state["report"]["choices"], strict=True)):
            if not edited.get("items") and index < len(draft_items):
                draft_item = draft_items[index]
                edited = {
                    "items": [
                        {
                            "award_type": identity_choice["award_type"],
                            "player_name": identity_choice["player_name"],
                            "title": str(draft_item.get("title") or ""),
                            "body": str(draft_item.get("body") or ""),
                        }
                    ],
                    "warnings": edited.get("warnings", []),
                }
            bound = _copy_output_bound_to_choices(edited, [identity_choice], language)
            items.extend(bound["items"])
            warnings.extend(str(warning) for warning in edited.get("warnings", []))
        state[output_key] = {"items": items, "warnings": warnings}
        return {
            "warnings": warnings,
            "summary": {
                "items": len(state[output_key]["items"]),
                "agent_calls": len(requests),
                "max_concurrency": self.config.max_concurrency,
            },
        }

    def _render_markdown(self, state: dict[str, Any]) -> dict[str, Any]:
        markdown_text = _render_agent_markdown(
            report=state["report"],
            en_copy=state["en_final"],
            zh_copy=state["zh_final"],
        )
        state["markdown_text"] = markdown_text
        state["paths"]["markdown"].write_text(markdown_text, encoding="utf-8")
        return {"summary": {"markdown_chars": len(markdown_text)}}

    def _final_deterministic_validation(self, state: dict[str, Any]) -> dict[str, Any]:
        warnings = _deterministic_fact_check(state["evidence"], state["markdown_text"])
        state["deterministic_warnings"] = warnings
        if warnings:
            raise RuntimeError(f"Editorial deterministic validation failed: {warnings}")
        return {"warnings": warnings, "summary": {"status": "pass"}}

    def _final_fact_check(self, state: dict[str, Any]) -> dict[str, Any]:
        try:
            llm_fact_check = _call_json(
                self.text_client,
                role="final_fact_check",
                model=self.config.models["fact_check"],
                instructions=_fact_check_instructions(state["style_packs"]),
                payload={
                    "match_date": self.match_date,
                    "evidence": state["evidence"],
                    "external_evidence": state["external_evidence"],
                    "markdown": state["markdown_text"],
                    "deterministic_warnings": state["deterministic_warnings"],
                },
                output_type=EditorialFactCheckOutput,
                timeout_seconds=self.config.timeout_seconds,
            )
        except AgentCallTimeout as exc:
            llm_fact_check = {"status": "timeout", "warnings": [str(exc)]}
        llm_warnings = _filter_llm_warnings(state["markdown_text"], llm_fact_check.get("warnings", []))
        llm_status = llm_fact_check.get("status", "pass") if llm_warnings else "pass"
        fact_check = {
            "status": "warning" if llm_warnings else "pass",
            "deterministic_status": "pass",
            "llm_status": llm_status,
            "warnings": llm_warnings,
        }
        state["fact_check"] = fact_check
        return {"warnings": llm_warnings, "summary": {"status": fact_check["status"]}}

    def _compile_publish(self, state: dict[str, Any]) -> dict[str, Any]:
        compiled = render_editorial_markdown_file(
            match_date=self.match_date,
            site_dir=self.site_dir,
            reports_dir=self.reports_dir,
        )
        state["compiled"] = compiled
        if self.rebuild_homepage:
            build_demo_site(self.db_path, self.site_dir, self.manifests_dir)
        return {"summary": {"choices": len(compiled.get("choices", []))}}


def run_editorial_agent(
    *,
    match_date: str,
    db_path: str | Path = "data/latest.sqlite",
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
    manifests_dir: str | Path = "manifests",
    agent_runs_dir: str | Path = "agent-runs",
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
    style_dir: str | Path = ".agents/editorial-skills",
    env_path: str | Path = ".env.local",
    client: AgentTextClient | None = None,
    research: bool = True,
    rebuild_homepage: bool = True,
) -> dict[str, Any]:
    config = load_editorial_agent_config(env_path, require_credentials=client is None)
    text_client = client or AgentsSdkTextClient(config)
    runner = EditorialWorkflowRunner(
        match_date=match_date,
        db_path=db_path,
        site_dir=site_dir,
        reports_dir=reports_dir,
        manifests_dir=manifests_dir,
        scoring_config_path=scoring_config_path,
        style_dir=style_dir,
        env_path=env_path,
        text_client=text_client,
        config=config,
        research=research,
        rebuild_homepage=rebuild_homepage,
    )
    state = runner.run()
    report = state["report"]
    compiled = state["compiled"]
    external_evidence = state["external_evidence"]
    fact_check = state["fact_check"]
    paths = state["paths"]

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
        "workflow": runner.workflow_audit(state),
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


def _evidence_for_choice(
    evidence: dict[str, Any],
    identity_choice: dict[str, Any],
) -> dict[str, Any]:
    return {
        **evidence,
        "choices": [
            choice
            for choice in evidence.get("choices", [])
            if choice.get("award_type") == identity_choice.get("award_type")
            and choice.get("player_name") == identity_choice.get("player_name")
        ],
    }


def _copy_output_bound_to_choices(
    payload: dict[str, Any],
    identity_choices: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    raw_items = payload.get("items")
    candidate_items = raw_items if isinstance(raw_items, list) else []
    items: list[dict[str, str]] = []
    for index, identity_choice in enumerate(identity_choices):
        candidate = candidate_items[index] if index < len(candidate_items) else {}
        if not isinstance(candidate, dict):
            candidate = {}
        title = str(candidate.get("title") or "").strip()
        body = str(candidate.get("body") or "").strip()
        if not title or not body:
            fallback = _fallback_copy(identity_choice, language)
            title = title or fallback["title"]
            body = body or fallback["body"]
        items.append(
            {
                "award_type": identity_choice["award_type"],
                "player_name": identity_choice["player_name"],
                "title": title,
                "body": body,
            }
        )
    return {"items": items, "warnings": payload.get("warnings", [])}


def _call_json(
    client: AgentTextClient,
    *,
    role: str,
    model: str,
    instructions: str,
    payload: dict[str, Any],
    output_type: type[Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    print(f"[editorial-agent] {role} -> {model}", file=sys.stderr, flush=True)
    user_input = json.dumps(payload, ensure_ascii=False)
    try:
        effective_timeout = None if isinstance(client, AgentsSdkTextClient) else timeout_seconds
        response = _complete_with_timeout(
            lambda: client.complete(
                role=role,
                model=model,
                instructions=instructions,
                user_input=user_input,
                output_type=output_type,
            ),
            timeout_seconds=effective_timeout,
            role=role,
        )
    except AgentCallTimeout as exc:
        raise
    parsed = _extract_json_object(response)
    return parsed


def _call_json_many(
    client: AgentTextClient,
    requests: list[dict[str, Any]],
    *,
    max_concurrency: int,
) -> list[dict[str, Any]]:
    completion_requests: list[AgentCompletionRequest] = []
    for request in requests:
        role = str(request["role"])
        model = str(request["model"])
        print(f"[editorial-agent] {role} -> {model}", file=sys.stderr, flush=True)
        completion_requests.append(
            AgentCompletionRequest(
                role=role,
                model=model,
                instructions=str(request["instructions"]),
                user_input=json.dumps(request["payload"], ensure_ascii=False),
                output_type=request.get("output_type"),
            )
        )
    outcomes = client.complete_many_settled(
        completion_requests,
        max_concurrency=max_concurrency,
    )
    payloads: list[dict[str, Any]] = []
    for request, outcome in zip(completion_requests, outcomes, strict=True):
        if outcome.error:
            payloads.append({"items": [], "warnings": [f"{request.role} failed: {outcome.error}"]})
            continue
        if outcome.response is None:
            payloads.append({"items": [], "warnings": [f"{request.role} failed: empty response"]})
            continue
        try:
            payloads.append(_extract_json_object(outcome.response))
        except Exception as exc:
            payloads.append({"items": [], "warnings": [f"{request.role} returned invalid JSON: {exc}"]})
    return payloads


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
                "你是终审中文体育编辑。根据输入 draft、draft_fact_check 和 evidence 定稿，不新增事实。",
                "返回同样 JSON schema。必须修复 draft_fact_check 指出的事实问题，再删掉翻译腔、空话和过度数据罗列。",
                "删掉“几乎都”“完全掌控”“没有办法限制他”等没有结构化证据支撑的总括句。",
                _style_subset(style_packs, ["human-writing-zh", "anti-translationese"]).get("joined", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are the final English editor. Finalize the copy from the draft, draft_fact_check, and evidence without adding facts.",
            "Return the same JSON schema. Fix any fact-check issues first, then keep the copy compact and editorial.",
            "Remove unsupported totalizing phrases such as \"no answer\", \"all afternoon\", \"controlled everything\", or \"every attack\".",
            style_packs.get("football-editor-style", ""),
        ]
    )


def _draft_fact_check_instructions(language: str, style_packs: dict[str, str]) -> str:
    if language == "zh":
        return "\n\n".join(
            [
                "你是中文初稿事实核查编辑。只检查 draft 是否被 evidence 支撑，不润色。",
                "返回严格 JSON：{\"status\":\"pass\"|\"fail\",\"warnings\":[\"...\"]}。",
                "指出错比分、错进球、助攻臆造、视频观察、外部评价、过度总括或证据不足的句子。",
                style_packs.get("fact-check-rules", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are a draft fact-checking editor. Check whether the draft is supported by evidence; do not rewrite it.",
            "Return strict JSON: {\"status\":\"pass\"|\"fail\",\"warnings\":[\"...\"]}.",
            "Flag wrong scorelines, unsupported assists, video observations, outside ratings, overbroad claims, or unsupported metrics.",
            style_packs.get("fact-check-rules", ""),
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
    unsupported_flow_claims = _unsupported_flow_claims(evidence, markdown_text)
    if unsupported_flow_claims:
        warnings.append(
            "Copy makes a match-flow claim that current evidence does not support: "
            + "; ".join(unsupported_flow_claims)
        )
    conversion_warnings = _unsupported_conversion_claims(evidence, markdown_text)
    warnings.extend(conversion_warnings)
    warnings.extend(_unsupported_tactical_detail_claims(markdown_text))
    warnings.extend(_unsupported_position_claims(evidence, markdown_text))
    warnings.extend(_duplicate_title_warnings(markdown_text))
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


def _duplicate_title_warnings(markdown_text: str) -> list[str]:
    warnings: list[str] = []
    for language, titles in _choice_titles_by_language(markdown_text).items():
        seen: set[str] = set()
        duplicates: set[str] = set()
        for title in titles:
            normalized = title.strip().lower()
            if not normalized:
                continue
            if normalized in seen:
                duplicates.add(title.strip())
            seen.add(normalized)
        for title in sorted(duplicates):
            warnings.append(f"Duplicate {language} title in editorial choices: {title}")
    return warnings


def _choice_titles_by_language(markdown_text: str) -> dict[str, list[str]]:
    titles = {"English": [], "Chinese": []}
    sections = _markdown_choice_sections(markdown_text)
    for section in sections:
        en_match = re.search(r"#### English\s+\*\*(.*?)\*\*", section, flags=re.DOTALL)
        zh_match = re.search(r"#### 中文\s+\*\*(.*?)\*\*", section, flags=re.DOTALL)
        if en_match:
            titles["English"].append(en_match.group(1).strip())
        if zh_match:
            titles["Chinese"].append(zh_match.group(1).strip())
    return titles


def _unsupported_tactical_detail_claims(markdown_text: str) -> list[str]:
    patterns = [
        r"禁区.{0,8}(抢到|落点)",
        r"防线身前接应",
        r"不敢.{0,6}前压",
        r"压力里带出来",
        r"最稳定的推进出口",
        r"组织反扑",
        r"\bdefen[cs]e unbalanced\b",
        r"\bsliced through\b.{0,40}\bshape\b",
    ]
    warnings: list[str] = []
    for pattern in patterns:
        if re.search(pattern, markdown_text, flags=re.IGNORECASE):
            warnings.append(
                "Copy uses unsupported tactical detail that would need event/location/tracking evidence."
            )
            break
    return warnings


def _unsupported_position_claims(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    sections = _markdown_choice_sections(markdown_text)
    choices = evidence.get("choices", [])
    if not sections or len(sections) != len(choices):
        return warnings
    for choice, section in zip(choices, sections, strict=True):
        position = str(choice.get("position") or "")
        if re.search(r"\bdefender\b", section, flags=re.IGNORECASE) and not position.startswith("DF"):
            warnings.append(
                f"Copy calls {choice.get('player_name')} a defender, but evidence position is {position or 'unknown'}."
            )
    return warnings


def _unsupported_conversion_claims(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    sections = _markdown_choice_sections(markdown_text)
    choices = evidence.get("choices", [])
    if not sections or len(sections) != len(choices):
        sections = [markdown_text for _ in choices]
    for choice, section in zip(choices, sections, strict=False):
        if not _mentions_all_chances_converted(section):
            continue
        metrics = choice.get("metrics") or {}
        shots = float(metrics.get("shots") or _choice_component_value(choice, "shots") or 0)
        goals = float(metrics.get("goals") or _choice_component_value(choice, "goals") or 0)
        if shots > goals:
            warnings.append(
                f"Copy claims all chances/shots were converted for {choice.get('player_name')}, "
                f"but evidence has {goals:g} goals from {shots:g} shots."
            )
    return warnings


def _mentions_all_chances_converted(text: str) -> bool:
    return bool(
        re.search(r"(机会|射门).{0,8}(全部|全都|都).{0,8}(打进|转化|把握)", text)
        or re.search(
            r"\ball\s+(?:chances|shots).{0,40}(?:converted|scored|finished)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _unsupported_flow_claims(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    unsupported: list[str] = []
    sections = _markdown_choice_sections(markdown_text)
    choices = evidence.get("choices", [])
    if sections and len(sections) == len(choices):
        for choice, section in zip(choices, sections, strict=True):
            unsupported.extend(_unsupported_flow_claims_for_choice(choice, section))
        return unsupported
    allowed_claims = _all_allowed_flow_claims(evidence)
    if _mentions_comeback_claim(markdown_text) and not _allows_any(
        allowed_claims,
        ["comeback win", "comeback winner", "comeback equaliser", "逆转取胜", "逆转制胜", "逆转扳平"],
    ):
        unsupported.append("comeback/逆转")
    if _mentions_go_ahead_claim(markdown_text) and not _allows_any(
        allowed_claims,
        ["go-ahead goal", "comeback winner", "取得领先", "逆转制胜"],
    ):
        unsupported.append("go-ahead/反超")
    return unsupported


def _markdown_choice_sections(markdown_text: str) -> list[str]:
    matches = list(re.finditer(r"(?m)^###\s+", markdown_text))
    sections: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        sections.append(markdown_text[start:end])
    return sections


def _unsupported_flow_claims_for_choice(choice: dict[str, Any], section: str) -> list[str]:
    allowed_claims = _choice_allowed_flow_claims(choice)
    unsupported: list[str] = []
    if _mentions_comeback_claim(section) and not _allows_any(
        allowed_claims,
        ["comeback win", "comeback winner", "comeback equaliser", "逆转取胜", "逆转制胜", "逆转扳平"],
    ):
        unsupported.append(f"{choice.get('player_name', 'unknown player')}: comeback/逆转")
    if _mentions_go_ahead_claim(section) and not _allows_any(
        allowed_claims,
        ["go-ahead goal", "comeback winner", "取得领先", "逆转制胜"],
    ):
        unsupported.append(f"{choice.get('player_name', 'unknown player')}: go-ahead/反超")
    return unsupported


def _mentions_comeback_claim(text: str) -> bool:
    return bool(re.search(r"\bcome(?:s)?[- ]from[- ]behind\b|\bcomeback\b|逆转", text, flags=re.IGNORECASE))


def _mentions_go_ahead_claim(text: str) -> bool:
    return bool(re.search(r"\bgo[- ]ahead\b|反超", text, flags=re.IGNORECASE))


def _all_allowed_flow_claims(evidence: dict[str, Any]) -> list[str]:
    claims: list[str] = []
    for choice in evidence.get("choices", []):
        claims.extend(_choice_allowed_flow_claims(choice))
    return claims


def _choice_allowed_flow_claims(choice: dict[str, Any]) -> list[str]:
    flow_context = choice.get("flow_context") or {}
    allowed = flow_context.get("allowed_claims") or {}
    claims: list[str] = []
    for language_claims in allowed.values():
        if isinstance(language_claims, list):
            claims.extend(str(claim) for claim in language_claims)
    return claims


def _allows_any(allowed_claims: list[str], needles: list[str]) -> bool:
    lowered = [claim.lower() for claim in allowed_claims]
    for needle in needles:
        needle_lower = needle.lower()
        if any(needle_lower in claim or claim in needle_lower for claim in lowered):
            return True
    return False


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
    for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", *MODEL_ENV_KEYS.values(), *CONTROL_ENV_KEYS]:
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
