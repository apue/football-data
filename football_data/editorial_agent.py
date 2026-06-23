from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from football_data.calibration import discover_potm_evidence_candidates
from football_data.demo import build_demo_site
from football_data.editorial import (
    _zh_player_name,
    _zh_team_name,
    build_editorial_report,
    render_editorial_markdown_file,
    write_editorial_artifacts,
)
from football_data.editorial_fingerprint import DEFAULT_SCORING_CONFIG
from football_data.firecrawl import search_firecrawl


DEFAULT_OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_AGENT_TIMEOUT_SECONDS = "90"
DEFAULT_AGENT_MAX_CONCURRENCY = "6"
DEFAULT_AGENT_MAX_ATTEMPTS = "1"

DEFAULT_MODELS = {
    "zh_editor": "zai-org/GLM-5.2",
    "en_editor": "deepseek-ai/DeepSeek-V4-Flash",
    "revision_editor": "deepseek-ai/DeepSeek-V4-Flash",
}


MODEL_ENV_KEYS = {
    "zh_editor": "EDITORIAL_ZH_EDITOR_MODEL",
    "en_editor": "EDITORIAL_EN_EDITOR_MODEL",
    "revision_editor": "EDITORIAL_REVISION_EDITOR_MODEL",
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
    used_evidence: list[str] = Field(default_factory=list)
    risk_check: list[str] = Field(default_factory=list)


class EditorialCopyOutput(BaseModel):
    items: list[EditorialCopyItem]
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
        review_feedback_path: str | Path | None,
        max_review_loops: int,
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
        self.review_feedback_path = Path(review_feedback_path) if review_feedback_path else None
        self.max_review_loops = max(0, max_review_loops)
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
            EditorialWorkflowNode("external_research", "python", self._external_research, "zh_editor_agent"),
            EditorialWorkflowNode(
                "zh_editor_agent",
                "agent",
                self._zh_editor_agent,
                "en_editor_agent",
                model_key="zh_editor",
                skills=("human-writing-zh", "anti-translationese", "football-editor-style"),
            ),
            EditorialWorkflowNode(
                "en_editor_agent",
                "agent",
                self._en_editor_agent,
                "render_markdown_and_repair",
                model_key="en_editor",
                skills=("football-editor-style",),
            ),
            EditorialWorkflowNode(
                "render_markdown_and_repair",
                "python",
                self._render_markdown_and_repair,
                "final_deterministic_validation",
            ),
            EditorialWorkflowNode(
                "final_deterministic_validation",
                "validator",
                self._final_deterministic_validation,
                "compile_publish",
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

    def _zh_editor_agent(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._edit_language_compact(
            state,
            "zh",
            state["fact_bank"]["choices"],
            "zh_editor_agent",
            "zh_editor",
            "zh_final",
        )

    def _en_editor_agent(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._edit_language_compact(
            state,
            "en",
            state["brief_en"]["choices"],
            "en_editor_agent",
            "en_editor",
            "en_final",
        )

    def _edit_language_compact(
        self,
        state: dict[str, Any],
        language: str,
        choices: list[dict[str, Any]],
        role: str,
        model_key: str,
        output_key: str,
    ) -> dict[str, Any]:
        items: list[dict[str, str]] = []
        warnings: list[str] = []
        self_checks: list[dict[str, Any]] = []
        requests = [
            {
                "role": role,
                "model": self.config.models[model_key],
                "instructions": _compact_editor_instructions(language, state["style_packs"]),
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
        outputs = _call_json_many(
            self.text_client,
            requests,
            max_concurrency=self.config.max_concurrency,
        )
        for output, identity_choice in zip(outputs, state["report"]["choices"], strict=True):
            bound = _copy_output_bound_to_choices(output, [identity_choice], language)
            items.extend(bound["items"])
            warnings.extend(str(warning) for warning in output.get("warnings", []))
            for raw_item in output.get("items", []):
                if isinstance(raw_item, dict):
                    self_checks.append(
                        {
                            "award_type": identity_choice["award_type"],
                            "player_name": identity_choice["player_name"],
                            "language": language,
                            "used_evidence": list(raw_item.get("used_evidence", []))
                            if isinstance(raw_item.get("used_evidence"), list)
                            else [],
                            "risk_check": list(raw_item.get("risk_check", []))
                            if isinstance(raw_item.get("risk_check"), list)
                            else [],
                        }
                    )
        state[output_key] = {"items": items, "warnings": warnings}
        state.setdefault("editor_self_checks", []).extend(self_checks)
        return {
            "warnings": warnings,
            "summary": {
                "items": len(state[output_key]["items"]),
                "agent_calls": len(requests),
                "max_concurrency": self.config.max_concurrency,
            },
        }

    def _render_markdown_and_repair(self, state: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        iterations: list[dict[str, Any]] = []
        revision_count = 0
        fallback_repairs = 0

        markdown_text = _render_agent_markdown(
            report=state["report"],
            en_copy=state["en_final"],
            zh_copy=state["zh_final"],
        )
        state["pre_review_markdown_text"] = markdown_text
        state["paths"]["pre_review_markdown"].write_text(markdown_text, encoding="utf-8")

        external_comments = _load_review_feedback_comments(self.review_feedback_path, self.match_date)
        if external_comments and self.max_review_loops > 0:
            revision_warnings = self._revise_from_review_comments(state, external_comments)
            warnings.extend(revision_warnings)
            revision_count += len(external_comments)
            markdown_text = _render_agent_markdown(
                report=state["report"],
                en_copy=state["en_final"],
                zh_copy=state["zh_final"],
            )
            iterations.append(
                {
                    "loop": 1,
                    "source": "external",
                    "status": "needs_revision",
                    "comments": external_comments,
                    "actionable_comments": len(external_comments),
                    "warnings": revision_warnings,
                }
            )

        repair_loop_cap = max(1, self.max_review_loops)
        deterministic_iterations: list[dict[str, Any]] = []
        for loop_index in range(1, repair_loop_cap + 1):
            comments = _deterministic_review_comments(
                report=state["report"],
                evidence=state["evidence"],
                markdown_text=markdown_text,
            )
            if not comments:
                break
            revision_warnings = self._revise_from_review_comments(state, comments)
            warnings.extend(revision_warnings)
            revision_count += len(comments)
            markdown_text = _render_agent_markdown(
                report=state["report"],
                en_copy=state["en_final"],
                zh_copy=state["zh_final"],
            )
            deterministic_iterations.append(
                {
                    "loop": loop_index,
                    "comments": comments,
                    "warnings": revision_warnings,
                }
            )

        final_warnings = _deterministic_fact_check(state["evidence"], markdown_text)
        if final_warnings:
            en_copy, zh_copy, markdown_text, repair_warnings = _render_repaired_markdown(
                report=state["report"],
                evidence=state["evidence"],
                en_copy=state["en_final"],
                zh_copy=state["zh_final"],
            )
            state["en_final"] = en_copy
            state["zh_final"] = zh_copy
            warnings.extend(repair_warnings)
            fallback_repairs = len(repair_warnings)

        state["markdown_text"] = markdown_text
        state["paths"]["markdown"].write_text(markdown_text, encoding="utf-8")
        state["review_feedback"] = {
            "iterations": iterations,
            "external_comments": external_comments,
        }
        state["deterministic_repair"] = {
            "iterations": deterministic_iterations,
            "fallback_repairs": fallback_repairs,
        }
        return {
            "warnings": warnings,
            "summary": {
                "markdown_chars": len(markdown_text),
                "external_revisions": len(external_comments),
                "external_comments": len(external_comments),
                "deterministic_repairs": sum(len(item["comments"]) for item in deterministic_iterations)
                + fallback_repairs,
                "revisions": revision_count,
                "fallback_repairs": fallback_repairs,
            },
        }

    def _revise_from_review_comments(
        self,
        state: dict[str, Any],
        comments: list[dict[str, Any]],
    ) -> list[str]:
        warnings: list[str] = []
        requests: list[dict[str, Any]] = []
        request_meta: list[tuple[dict[str, Any], str]] = []
        for choice in state["report"]["choices"]:
            for language in ("en", "zh"):
                language_comments = _review_comments_for_choice_language(
                    comments,
                    choice,
                    language,
                )
                if not language_comments:
                    continue
                copy_payload = state[f"{language}_final"]
                current_copy = _copy_by_choice(copy_payload).get(_choice_key(choice)) or _fallback_copy(
                    choice,
                    language,
                )
                requests.append(
                    {
                        "role": "revision_editor",
                        "model": self.config.models["revision_editor"],
                        "instructions": _revision_editor_instructions(language, state["style_packs"]),
                        "payload": {
                            "language": language,
                            "choices": [choice],
                            "current_copy": {"items": [{**current_copy, "award_type": choice["award_type"], "player_name": choice["player_name"]}]},
                            "comments": language_comments,
                            "evidence": _evidence_for_choice(state["evidence"], choice),
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
                request_meta.append((choice, language))
        if not requests:
            return warnings
        revisions = _call_json_many(
            self.text_client,
            requests,
            max_concurrency=self.config.max_concurrency,
        )
        for revision, (choice, language) in zip(revisions, request_meta, strict=True):
            bound = _copy_output_bound_to_choices(revision, [choice], language)
            if not bound["items"]:
                warnings.append(f"revision_editor returned no copy for {choice['player_name']} {language}")
                continue
            _set_copy_item(state[f"{language}_final"], choice, bound["items"][0])
            warnings.extend(str(warning) for warning in revision.get("warnings", []))
        return warnings

    def _final_deterministic_validation(self, state: dict[str, Any]) -> dict[str, Any]:
        warnings = _deterministic_fact_check(state["evidence"], state["markdown_text"])
        state["deterministic_warnings"] = warnings
        if warnings:
            raise RuntimeError(f"Editorial deterministic validation failed: {warnings}")
        state["fact_check"] = {
            "status": "pass",
            "deterministic_status": "pass",
            "llm_status": "skipped",
            "warnings": [],
        }
        return {"warnings": warnings, "summary": {"status": "pass"}}

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
    review_feedback_path: str | Path | None = None,
    max_review_loops: int = 1,
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
        review_feedback_path=review_feedback_path,
        max_review_loops=max_review_loops,
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
        "review_feedback": state.get("review_feedback"),
        "deterministic_repair": state.get("deterministic_repair"),
        "editor_self_checks": state.get("editor_self_checks", []),
        "artifacts": {
            "markdown": str(paths["markdown"]),
            "pre_review_markdown": str(paths["pre_review_markdown"]),
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
        "pre_review_markdown": Path(reports_dir) / "editorial" / f"{match_date}.pre-review.md",
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


def _compact_editor_instructions(language: str, style_packs: dict[str, str]) -> str:
    if language == "zh":
        return "\n\n".join(
            [
                "你是一个中文足球编辑节点，一次完成选角、写作和自检。只根据输入 JSON 写作，不要编造助攻、视频观察或外部评价。",
                "返回严格 JSON：{\"items\":[{\"award_type\":\"...\",\"player_name\":\"...\",\"title\":\"...\",\"body\":\"...\",\"used_evidence\":[\"...\"],\"risk_check\":[\"...\"]}],\"warnings\":[]}",
                "每张卡只写一个 title 和一个 body。body 最多一段，最多带 2-3 个关键数字。",
                "写作前在心里完成 risk_check：事实是否都在 evidence；时间顺序是否正确；指标是否误写；中文是否像翻译腔或模板句。",
                "risk_check 只写简短检查点，不要写进 body。used_evidence 只列你实际使用的关键事实。",
                "严格区分“取得领先”“首开纪录”“制胜”：只有 allowed_claims 明确支持时才写。",
                "不要把“一球一助”写成“两球”“梅开二度”或“双响”。",
                "`offers_received` 写作“接应成功/被队友找到”，不要写成传球次数。",
                "`in_behind` 是独立的 in-behind offer 计数；不要和 `offers_received` 写成包含关系。",
                "`line_breaks_completed` 写作“打穿防线”或“完成打穿防线”，不要写成跑动或传球次数。",
                "不要写需要看录像才能证明的总括句，例如“几乎都从他脚下经过”“完全掌控”“没有办法限制他”。",
                "避免“压力背景足够清楚”“入选理由很直接”“给出答案”这类审稿腔/模板腔。",
                _style_subset(style_packs, ["human-writing-zh", "anti-translationese", "football-editor-style"]).get("joined", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are a football editor node. In one pass, choose the angle, write the card, and self-check it from the input JSON only.",
            "Return strict JSON: {\"items\":[{\"award_type\":\"...\",\"player_name\":\"...\",\"title\":\"...\",\"body\":\"...\",\"used_evidence\":[\"...\"],\"risk_check\":[\"...\"]}],\"warnings\":[]}",
            "Each card needs one title and one body paragraph. Use at most 2-3 key numbers.",
            "Before finalizing, run a risk_check: supported facts only, correct sequence, no metric mistranslation, no generic filler.",
            "risk_check stays in JSON only; do not put it in body. used_evidence should list only facts actually used.",
            "Distinguish go-ahead, opening, and match-winning goals. Use them only when allowed_claims supports them.",
            "Do not turn one goal plus one assist into two goals, a brace, or scored twice.",
            "Treat offers_received as successful receptions/being found, not as passes.",
            "Treat in_behind as a separate in-behind offer count. Do not combine it with offers_received.",
            "Treat line_breaks_completed as completed line breaks or line-breaking actions, not runs or passes.",
            "Avoid generic or unsupported phrases like 'made the case', 'clear evidence', 'no answer', or audit-style wording.",
            style_packs.get("football-editor-style", ""),
        ]
    )


def _revision_editor_instructions(language: str, style_packs: dict[str, str]) -> str:
    if language == "zh":
        return "\n\n".join(
            [
                "你是发布前修订编辑。只根据 comments 修改 current_copy，不重新选人，不新增事实。",
                "返回同样 JSON schema: {\"items\":[{\"award_type\":\"...\",\"player_name\":\"...\",\"title\":\"...\",\"body\":\"...\"}],\"warnings\":[]}",
                "目标是让文案像中文足球短评：去重复、去模板腔、去审计口吻。",
                "必须保留 evidence 支持的事实边界；不能写站位、压迫、视频观察或外部评价。",
                style_packs.get("human-writing-zh", ""),
                style_packs.get("anti-translationese", ""),
            ]
        )
    return "\n\n".join(
        [
            "You are the publication revision editor. Revise only the current_copy according to comments.",
            "Return the same JSON schema with one title/body item. Do not change the selected player.",
            "Make the copy concise and publishable. Remove repetition, template phrasing, and audit/process language.",
            "Do not add facts, video observations, outside ratings, or unsupported tactical claims.",
            style_packs.get("football-editor-style", ""),
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
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_repaired_markdown(
    *,
    report: dict[str, Any],
    evidence: dict[str, Any],
    en_copy: dict[str, Any],
    zh_copy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, list[str]]:
    en_repaired = _clone_copy_payload(en_copy)
    zh_repaired = _clone_copy_payload(zh_copy)
    repair_warnings: list[str] = []

    for _iteration in range(3):
        markdown_text = _render_agent_markdown(
            report=report,
            en_copy=en_repaired,
            zh_copy=zh_repaired,
        )
        warnings = _deterministic_fact_check(evidence, markdown_text)
        if not warnings:
            return en_repaired, zh_repaired, markdown_text, repair_warnings

        changed = False
        sections = _markdown_choice_sections(markdown_text)
        for choice, section in zip(report["choices"], sections, strict=False):
            section_warnings = _choice_section_hard_warnings(choice, section)
            if not section_warnings:
                continue
            _set_copy_item(en_repaired, choice, _fallback_copy(choice, "en"))
            _set_copy_item(zh_repaired, choice, _fallback_copy(choice, "zh"))
            changed = True
            repair_warnings.append(
                f"Replaced {choice['player_name']} copy with deterministic fallback: "
                + "; ".join(section_warnings)
            )

        if _dedupe_titles(en_repaired, report, "en"):
            changed = True
            repair_warnings.append("Repaired duplicate English titles.")
        if _dedupe_titles(zh_repaired, report, "zh"):
            changed = True
            repair_warnings.append("Repaired duplicate Chinese titles.")

        if not changed:
            break

    markdown_text = _render_agent_markdown(
        report=report,
        en_copy=en_repaired,
        zh_copy=zh_repaired,
    )
    return en_repaired, zh_repaired, markdown_text, repair_warnings


def _choice_section_hard_warnings(choice: dict[str, Any], section: str) -> list[str]:
    warnings: list[str] = []
    warnings.extend(_unsupported_flow_claims_for_choice(choice, section))
    warnings.extend(_unsupported_goal_count_claims_for_choice(choice, section))
    warnings.extend(_unsupported_goalkeeper_save_claims_for_choice(choice, section))
    warnings.extend(_unsupported_tactical_detail_claims(section))
    if _mentions_all_chances_converted(section):
        shots = _choice_metric_value(choice, "shots")
        goals = _choice_metric_value(choice, "goals")
        if shots > goals:
            warnings.append(
                f"{choice.get('player_name', 'unknown player')}: all chances converted"
            )
    return warnings


def _deterministic_review_comments(
    *,
    report: dict[str, Any],
    evidence: dict[str, Any],
    markdown_text: str,
) -> list[dict[str, Any]]:
    del evidence
    comments: list[dict[str, Any]] = []
    sections = _markdown_choice_sections(markdown_text)
    for choice_index, (choice, section) in enumerate(
        zip(report.get("choices", []), sections, strict=False),
        start=1,
    ):
        for language, language_section in _language_sections(section).items():
            section_warnings = _choice_section_hard_warnings(choice, language_section)
            for warning_index, warning in enumerate(section_warnings, start=1):
                comments.append(
                    {
                        "id": f"deterministic-{choice_index}-{language}-{warning_index}",
                        "award_type": str(choice.get("award_type") or ""),
                        "player_name": str(choice.get("player_name") or ""),
                        "language": language,
                        "severity": "blocking",
                        "issue_type": "deterministic_validation",
                        "quote": "",
                        "comment": warning,
                        "constraint": (
                            "Make the smallest local edit needed to remove this validation issue. "
                            "Preserve the title, structure, tone, and all unrelated supported context."
                        ),
                    }
                )
    return comments


def _language_sections(section: str) -> dict[str, str]:
    en_match = re.search(r"#### English\s+(.*?)(?=#### 中文|\Z)", section, flags=re.DOTALL)
    zh_match = re.search(r"#### 中文\s+(.*)", section, flags=re.DOTALL)
    return {
        "en": en_match.group(1) if en_match else section,
        "zh": zh_match.group(1) if zh_match else section,
    }


def _clone_copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": [
            dict(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ],
        "warnings": list(payload.get("warnings", [])),
    }


def _load_review_feedback_comments(
    path: Path | None,
    match_date: str,
) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("match_date") or match_date) != match_date:
        raise ValueError(
            f"Review feedback date {payload.get('match_date')} does not match {match_date}"
        )
    return _normalize_review_comments(payload.get("comments", []))


def _normalize_review_comments(raw_comments: object) -> list[dict[str, Any]]:
    if not isinstance(raw_comments, list):
        return []
    comments: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_comments, start=1):
        if isinstance(raw, BaseModel):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            continue
        player_name = str(raw.get("player_name") or "").strip()
        comment = str(raw.get("comment") or "").strip()
        if not player_name or not comment:
            continue
        comments.append(
            {
                "id": str(raw.get("id") or f"review-{index}"),
                "award_type": str(raw.get("award_type") or ""),
                "player_name": player_name,
                "language": str(raw.get("language") or "both").lower(),
                "severity": str(raw.get("severity") or "major").lower(),
                "issue_type": str(raw.get("issue_type") or "style"),
                "quote": str(raw.get("quote") or ""),
                "comment": comment,
                "constraint": str(raw.get("constraint") or ""),
            }
        )
    return comments


def _review_comments_for_choice_language(
    comments: list[dict[str, Any]],
    choice: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    player_name = str(choice["player_name"])
    award_type = str(choice["award_type"])
    matched: list[dict[str, Any]] = []
    for comment in comments:
        comment_language = str(comment.get("language") or "both").lower()
        if comment_language not in {language, "both", "all"}:
            continue
        if str(comment.get("player_name") or "") != player_name:
            continue
        comment_award = str(comment.get("award_type") or "")
        if comment_award and comment_award != award_type:
            continue
        matched.append(comment)
    return matched


def _set_copy_item(
    payload: dict[str, Any],
    choice: dict[str, Any],
    copy_item: dict[str, str],
) -> None:
    key = _choice_key(choice)
    items = payload.setdefault("items", [])
    replacement = {
        "award_type": choice["award_type"],
        "player_name": choice["player_name"],
        "title": str(copy_item.get("title") or ""),
        "body": str(copy_item.get("body") or ""),
    }
    for index, item in enumerate(items):
        if (
            str(item.get("award_type") or ""),
            str(item.get("player_name") or ""),
        ) == key:
            items[index] = replacement
            return
    items.append(replacement)


def _dedupe_titles(payload: dict[str, Any], report: dict[str, Any], language: str) -> bool:
    seen: set[str] = set()
    changed = False
    by_key = _copy_item_refs_by_choice(payload)
    for choice in report["choices"]:
        key = _choice_key(choice)
        item = by_key.get(key)
        if not item:
            continue
        normalized = _normalize_title(str(item.get("title") or ""))
        if normalized and normalized not in seen:
            seen.add(normalized)
            continue
        fallback = _fallback_copy(choice, language)
        title = str(fallback["title"])
        normalized = _normalize_title(title)
        if not normalized or normalized in seen:
            if language == "zh":
                title = f"{choice['player_name']}：{title}"
            else:
                title = f"{title}: {choice['player_name']}"
            normalized = _normalize_title(title)
        item["title"] = title
        seen.add(normalized)
        changed = True
    return changed


def _copy_item_refs_by_choice(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in payload.get("items", []):
        if isinstance(item, dict):
            by_key[(str(item.get("award_type") or ""), str(item.get("player_name") or ""))] = item
    return by_key


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _copy_by_choice(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    items = payload.get("items", [])
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("award_type") or ""), str(item.get("player_name") or ""))
        title = _normalize_copy_text(item.get("title") or "")
        body = _normalize_copy_text(item.get("body") or "")
        if key[0] and key[1] and title and body:
            by_key[key] = {"title": title, "body": body}
    return by_key


def _normalize_copy_text(value: object) -> str:
    text = str(value).strip()
    text = text.replace("\\n\\n", "\n\n").replace("\\n", "\n")
    text = re.sub(r"(?i)\bsuccess-\s+ful\b", "successful", text)
    return text


def _choice_key(choice: dict[str, Any]) -> tuple[str, str]:
    return (str(choice["award_type"]), str(choice["player_name"]))


def _fallback_copy(choice: dict[str, Any], language: str) -> dict[str, str]:
    if language == "zh":
        return _fallback_zh_copy(choice)
    return _fallback_en_copy(choice)


def _fallback_zh_copy(choice: dict[str, Any]) -> dict[str, str]:
    player = _zh_player_name(str(choice["player_name"]))
    award_type = str(choice.get("award_type") or "")
    metrics = choice.get("metrics") if isinstance(choice.get("metrics"), dict) else {}
    chips = [str(chip) for chip in choice.get("evidence_chips", {}).get("zh", [])]
    goals = int(float(metrics.get("goals") or 0))
    assists = int(float(metrics.get("assists") or 0))
    line_breaks = int(float(metrics.get("line_breaks_completed") or 0))
    regains = int(float(metrics.get("possession_regains") or 0))
    interruptions = int(float(metrics.get("possession_interrupted") or 0))
    blocks = int(float(metrics.get("blocks") or 0))
    offers = int(float(metrics.get("offers_received") or 0))
    in_behind = int(float(metrics.get("in_behind") or 0))
    in_between = int(float(metrics.get("in_between") or 0))
    opponent_xg = float(metrics.get("opponent_xg") or 0)
    opponent_on_target = int(float(metrics.get("opponent_attempts_on_target") or 0))
    team = _zh_team_name(str(choice["team"]))
    opponent = _zh_team_name(str(choice["opponent"]))
    scoreline = f"{team}{choice['team_final_goals']}-{choice['opponent_final_goals']}{opponent}"

    if "逆转制胜" in chips and assists:
        title = f"{player}一球一助，打进逆转制胜球"
        body = f"{scoreline}，{player}打进逆转制胜球，还送出一次助攻。"
        if line_breaks:
            body += f" 全场{line_breaks}次打穿防线，进攻贡献不只停在进球上。"
    elif "逆转制胜" in chips:
        title = f"{player}打进逆转制胜球"
        body = f"{scoreline}，{player}的进球直接改变了比赛结果。"
    elif "扳平进球" in chips and assists:
        title = f"{player}扳平又助攻"
        body = f"{scoreline}，{player}既有扳平球，也送出一次助攻。两次直接参与进球，让他的进攻贡献不只停在一个瞬间。"
    elif goals >= 2:
        title = f"{player}梅开二度"
        assist_note = "，还送出一次助攻" if assists else ""
        body = f"{scoreline}，{player}梅开二度{assist_note}。"
    elif goals:
        title = f"{player}打进关键进球"
        body = f"{scoreline}，{player}取得进球，这是他入选最直接的理由。"
    elif award_type == "progression_pick" and line_breaks:
        title = f"{line_breaks}次打穿防线，{player}负责向前"
        body = (
            f"{scoreline}，{player}全场{line_breaks}次打穿防线，"
            "这类贡献不一定抢镜，但会持续把进攻推到更靠前的位置。"
        )
    elif award_type == "defensive_pick" and regains:
        title = f"{regains}次夺回球权，{player}守住防线"
        details = []
        if interruptions:
            details.append(f"{interruptions}次破坏进攻")
        if blocks:
            details.append(f"{blocks}次封堵")
        detail_text = f"再加上{'、'.join(details[:2])}，" if details else ""
        body = (
            f"{scoreline}，{player}全场{regains}次夺回球权。"
            f"{detail_text}他的防守存在感很直接。"
        )
    elif award_type == "goalkeeper_watch":
        title = f"{player}守住零封"
        details = []
        if opponent_on_target:
            details.append(f"对手{opponent_on_target}次射正")
        if opponent_xg:
            details.append(f"xG达到{opponent_xg:g}")
        body = f"{scoreline}，{player}这个零封不算轻松。"
        if details:
            body += " " + "，".join(details[:2]) + "，这个零封有足够分量。"
    elif offers:
        title = f"{offers}次接应成功，{player}把进攻串起来"
        body = f"{scoreline}，{player}全场{offers}次接应成功。"
    else:
        title = f"{player}入选{choice['award_label']['zh']}"
        body = f"{scoreline}，{player}的关键贡献来自{('、'.join(chips[:2]) if chips else '这场比赛里的稳定表现')}。"

    extras = []
    if goals == 0 and award_type not in {"goalkeeper_watch", "defensive_pick", "progression_pick"}:
        if line_breaks and award_type != "progression_pick":
            extras.append(f"{line_breaks}次打穿防线")
        if offers and award_type != "defensive_pick":
            extras.append(f"{offers}次接应成功")
        if in_behind:
            extras.append(f"{in_behind}次身后接应")
        if in_between:
            extras.append(f"{in_between}次两线间接应")
        if regains and award_type != "defensive_pick":
            extras.append(f"{regains}次夺回球权")
    if extras:
        body += " " + "，".join(extras[:3]) + "，让他的贡献不只停在一个标签上。"
    return {"title": title, "body": body}


def _fallback_en_copy(choice: dict[str, Any]) -> dict[str, str]:
    player = str(choice["player_name"])
    award = str(choice["award_label"]["en"])
    metrics = choice.get("metrics") if isinstance(choice.get("metrics"), dict) else {}
    chips = [str(chip) for chip in choice.get("evidence_chips", {}).get("en", [])]
    goals = int(float(metrics.get("goals") or 0))
    assists = int(float(metrics.get("assists") or 0))
    line_breaks = int(float(metrics.get("line_breaks_completed") or 0))
    regains = int(float(metrics.get("possession_regains") or 0))
    offers = int(float(metrics.get("offers_received") or 0))
    opponent_xg = float(metrics.get("opponent_xg") or 0)
    opponent_on_target = int(float(metrics.get("opponent_attempts_on_target") or 0))
    scoreline = f"{choice['team']} {choice['team_final_goals']}-{choice['opponent_final_goals']} {choice['opponent']}"
    if "equaliser" in chips and assists:
        return {
            "title": f"{player} kept Uruguay alive",
            "body": f"{player} scored the equaliser and added an assist in {scoreline}, giving Uruguay both a way back and another direct contribution in attack.",
        }
    if goals >= 2 and assists:
        return {
            "title": f"{player}'s two goals and assist",
            "body": f"{player} scored twice and added an assist in {scoreline}.",
        }
    if goals and assists:
        goal_phrase = "the match-winning goal" if "match-winning goal" in chips else "a goal"
        return {
            "title": f"{player}'s goal and assist",
            "body": f"{player} scored {goal_phrase} and added an assist in {scoreline}.",
        }
    if goals:
        return {
            "title": f"{player}'s decisive touch",
            "body": f"{player} scored in {scoreline}.",
        }
    if str(choice.get("award_type") or "") == "goalkeeper_watch":
        pressure = []
        if opponent_on_target:
            pressure.append(f"{opponent_on_target} opponent shots on target")
        if opponent_xg:
            pressure.append(f"{opponent_xg:g} opponent xG")
        detail = f" against {' and '.join(pressure)}" if pressure else ""
        return {
            "title": "The clean sheet under pressure",
            "body": f"{player} kept the clean sheet in {scoreline}{detail}, making the shutout stand out on a quiet scoreboard.",
        }
    if str(choice.get("award_type") or "") == "defensive_pick" and regains:
        return {
            "title": "The ball-winner",
            "body": f"{player} made {regains} possession regains in {scoreline}, giving his defensive selection a clear base.",
        }
    if line_breaks:
        return {
            "title": f"The forward route",
            "body": f"{player} completed {line_breaks} line breaks in {scoreline}, giving his side a repeated way forward.",
        }
    if regains:
        return {
            "title": "The ball-winner",
            "body": f"{player} made {regains} possession regains in {scoreline}, a clear defensive footprint.",
        }
    if offers:
        return {
            "title": "The connector",
            "body": f"{player} received {offers} offers in {scoreline}, keeping himself available as a passing option.",
        }
    return {
        "title": f"{player}: {award}",
        "body": f"{player}'s evidence profile supports this selection.",
    }


def _match_label(choice: dict[str, Any], match: dict[str, Any] | None) -> str:
    if not match:
        return f"{choice['team']} vs {choice['opponent']} · Match {choice['match_no']}"
    return f"{match['home_team']} vs {match['away_team']} · Match {match['match_no']}"


def _deterministic_fact_check(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    if (
        re.search(r"\bassist(s|ed)?\b|助攻", markdown_text, flags=re.IGNORECASE)
        and not _evidence_has_official_assists(evidence)
    ):
        warnings.append("Copy mentions assists, which are not available in current PMSR evidence.")
    unsupported_flow_claims = _unsupported_flow_claims(evidence, markdown_text)
    if unsupported_flow_claims:
        warnings.append(
            "Copy makes a match-flow claim that current evidence does not support: "
            + "; ".join(unsupported_flow_claims)
        )
    conversion_warnings = _unsupported_conversion_claims(evidence, markdown_text)
    warnings.extend(conversion_warnings)
    warnings.extend(_unsupported_goal_count_claims(evidence, markdown_text))
    warnings.extend(_unsupported_goalkeeper_save_claims(evidence, markdown_text))
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


def _evidence_has_official_assists(evidence: dict[str, Any]) -> bool:
    editorial_input = evidence.get("editorial_input")
    return isinstance(editorial_input, dict) and "goal_involvements" in editorial_input


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
    checked_text = "\n".join(
        line
        for line in markdown_text.splitlines()
        if not line.startswith("Evidence:") and not line.startswith("依据：")
    )
    patterns = [
        r"禁区.{0,8}(抢到|落点)",
        r"防线身前接应",
        r"不敢.{0,6}前压",
        r"压力里带出来",
        r"最稳定的推进出口",
        r"组织反扑",
        r"中场接应和转移",
        r"中场连接点",
        r"接应和转移",
        r"帮助.{0,12}不断向前",
        r"帮球队持续向前处理",
        r"没有断掉进攻",
        r"落后阶段.{0,12}接应",
        r"被队友不断找到",
        r"把球往前推",
        r"把球往前送",
        r"一直.{0,8}往前送",
        r"没回收",
        r"出球点",
        r"连接让球队稳住",
        r"禁区前沿",
        r"防线中段",
        r"乌拉圭反复压上来攻",
        r"推进路线",
        r"前场中路",
        r"空当",
        r"防线之间",
        r"找到通道",
        r"长传或直塞",
        r"脏活硬活包揽",
        r"脏活.{0,4}硬活",
        r"包揽.{0,12}脏活.{0,6}硬活",
        r"推进一次次停下来",
        r"推进.{0,8}停下来",
        r"进攻.{0,8}停下来",
        r"不断施压",
        r"\d+\s*次身后接应中(?:有)?\d+\s*次被(?:队友)?找到",
        r"\bdefen[cs]e unbalanced\b",
        r"\bforcing resets\b",
        r"\brestart (?:their )?attacks\b",
        r"\broute back into (?:it|the match)\b",
        r"\bhelp(?:ed|ing)?\s+\w+\s+recover from\b",
        r"\brecover from a one-goal deficit\b",
        r"\bmidfield connector\b",
        r"\bconnected\b.{0,40}\bmidfield\b",
        r"\bconstant movement\b",
        r"\bdangerous areas\b",
        r"\bline[- ]breaking (?:runs?|passes?)\b",
        r"\b\d+\s+(?:runs?|passes?)\s+in\s+behind\b",
        r"\b(?:received|receiving)\s+\w+\s+(?:passes?|offers?)\s+.{0,20}\bin\s+behind\b",
        r"\bsliced through\b.{0,40}\bshape\b",
        r"\breceived\s+\d+\s+passes\b",
        r"接到\s*\d+\s*(?:脚|次)?传球",
    ]
    warnings: list[str] = []
    for pattern in patterns:
        if re.search(pattern, checked_text, flags=re.IGNORECASE):
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
        if re.search(r"\bwinger\b", section, flags=re.IGNORECASE) and "WINGER" not in position.upper():
            warnings.append(
                f"Copy calls {choice.get('player_name')} a winger, but evidence position is {position or 'unknown'}."
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
    if _mentions_opening_goal_claim(markdown_text) and not _allows_any(
        allowed_claims,
        ["opening goal", "首开纪录"],
    ):
        unsupported.append("opening goal/首开纪录")
    if _mentions_winner_claim(markdown_text) and not _allows_any(
        allowed_claims,
        [
            "match-winning goal",
            "winner",
            "late winner",
            "comeback winner",
            "stoppage-time winner",
            "制胜球",
            "补时制胜",
            "逆转制胜",
        ],
    ):
        unsupported.append("winner/制胜")
    if _mentions_stoppage_winner_claim(markdown_text) and not _allows_any(
        allowed_claims,
        ["stoppage-time winner", "补时制胜"],
    ):
        unsupported.append("stoppage-time winner/补时制胜")
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
    if _mentions_opening_goal_claim(section) and not _allows_any(
        allowed_claims,
        ["opening goal", "首开纪录"],
    ):
        unsupported.append(f"{choice.get('player_name', 'unknown player')}: opening goal/首开纪录")
    if _mentions_winner_claim(section) and not _allows_any(
        allowed_claims,
        [
            "match-winning goal",
            "winner",
            "late winner",
            "comeback winner",
            "stoppage-time winner",
            "制胜球",
            "补时制胜",
            "逆转制胜",
        ],
    ):
        unsupported.append(f"{choice.get('player_name', 'unknown player')}: winner/制胜")
    if _mentions_stoppage_winner_claim(section) and not _allows_any(
        allowed_claims,
        ["stoppage-time winner", "补时制胜"],
    ):
        unsupported.append(f"{choice.get('player_name', 'unknown player')}: stoppage-time winner/补时制胜")
    return unsupported


def _mentions_comeback_claim(text: str) -> bool:
    return bool(re.search(r"\bcome(?:s)?[- ]from[- ]behind\b|\bcomeback\b|逆转", text, flags=re.IGNORECASE))


def _mentions_go_ahead_claim(text: str) -> bool:
    return bool(re.search(r"\bgo[- ]ahead\b|反超", text, flags=re.IGNORECASE))


def _mentions_opening_goal_claim(text: str) -> bool:
    return bool(
        re.search(
            r"\bopen(?:ed|s|ing)? the scoring\b|\bopening goal\b|首开纪录|首球",
            text,
            flags=re.IGNORECASE,
        )
    )


def _mentions_winner_claim(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:match[- ]winning|match[- ]winner|(?<!-)winner)\b|制胜球|制胜一击|补时制胜|逆转制胜",
            text,
            flags=re.IGNORECASE,
        )
    )


def _mentions_stoppage_winner_claim(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:stoppage[- ]time|90\+).*\bwinner\b|补时制胜",
            text,
            flags=re.IGNORECASE,
        )
    )


def _unsupported_goal_count_claims(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    sections = _markdown_choice_sections(markdown_text)
    choices = evidence.get("choices", [])
    if not sections or len(sections) != len(choices):
        sections = [markdown_text for _ in choices]
    for choice, section in zip(choices, sections, strict=False):
        warnings.extend(_unsupported_goal_count_claims_for_choice(choice, section))
    return warnings


def _unsupported_goal_count_claims_for_choice(choice: dict[str, Any], section: str) -> list[str]:
    goals = _choice_metric_value(choice, "goals")
    player_name = str(choice.get("player_name") or "unknown player")
    warnings: list[str] = []
    if goals < 3 and _mentions_hat_trick_claim(section):
        warnings.append(f"Copy claims a hat-trick/帽子戏法 for {player_name}, but evidence has {goals:g} goals.")
    if goals < 2 and _mentions_two_goal_claim(section):
        warnings.append(f"Copy claims a brace/two goals for {player_name}, but evidence has {goals:g} goals.")
    return warnings


def _unsupported_goalkeeper_save_claims(evidence: dict[str, Any], markdown_text: str) -> list[str]:
    warnings: list[str] = []
    sections = _markdown_choice_sections(markdown_text)
    choices = evidence.get("choices", [])
    if not sections or len(sections) != len(choices):
        sections = [markdown_text for _ in choices]
    for choice, section in zip(choices, sections, strict=False):
        warnings.extend(_unsupported_goalkeeper_save_claims_for_choice(choice, section))
    return warnings


def _unsupported_goalkeeper_save_claims_for_choice(choice: dict[str, Any], section: str) -> list[str]:
    if str(choice.get("award_type") or "") != "goalkeeper_watch":
        return []
    number = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    if re.search(
        rf"\b(?:made|required)?\s*{number}\s+saves?\b|\bsaved\s+{number}\b|\bturned\s+aside\s+(?:all\s+)?{number}\b|\brepell(?:ed|ing)\s+(?:all\s+)?{number}\s+shots?\b",
        section,
        flags=re.IGNORECASE,
    ):
        return [
            f"Copy treats shot-log Saved outcomes as official goalkeeper saves for {choice.get('player_name')}."
        ]
    if re.search(r"\d+\s*次.{0,10}(?:扑救|扑出|挡出|化解)|被他挡出", section):
        return [
            f"Copy treats shot-log Saved outcomes as official goalkeeper saves for {choice.get('player_name')}."
        ]
    if re.search(
        r"\bresisted every attempt\b|\bevery attempt\b|力保城门不失|一次次化解|连续的射正考验",
        section,
        flags=re.IGNORECASE,
    ):
        return [
            f"Copy treats shot-log Saved outcomes as official goalkeeper saves for {choice.get('player_name')}."
        ]
    return []


def _mentions_hat_trick_claim(text: str) -> bool:
    return bool(re.search(r"\bhat[- ]trick\b|帽子戏法", text, flags=re.IGNORECASE))


def _mentions_two_goal_claim(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:two goals|scored twice|brace)\b|梅开二度|双响|两球|2球",
            text,
            flags=re.IGNORECASE,
        )
    )


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


def _choice_metric_value(choice: dict[str, Any], metric: str) -> float:
    metrics = choice.get("metrics")
    if isinstance(metrics, dict) and metric in metrics:
        return float(metrics.get(metric) or 0)
    return _choice_component_value(choice, metric)


def _team_goals_for_choice(choice: dict[str, Any], match: dict[str, Any] | None) -> float:
    if not match:
        return 0.0
    team = choice.get("team")
    if team == match.get("home_team"):
        return float(match.get("home_score") or 0)
    if team == match.get("away_team"):
        return float(match.get("away_score") or 0)
    return 0.0


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
