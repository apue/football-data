from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


DEFAULT_OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_AGENT_TIMEOUT_SECONDS = "180"
DEFAULT_AGENT_MAX_CONCURRENCY = "6"
DEFAULT_AGENT_MAX_ATTEMPTS = "1"

DEFAULT_MODELS = {
    "selection_editor": "deepseek-ai/DeepSeek-V4-Flash",
    "zh_editor": "zai-org/GLM-5.2",
    "en_editor": "deepseek-ai/DeepSeek-V4-Flash",
}

MODEL_ENV_KEYS = {
    "selection_editor": "EDITORIAL_SELECTION_EDITOR_MODEL",
    "zh_editor": "EDITORIAL_ZH_EDITOR_MODEL",
    "en_editor": "EDITORIAL_EN_EDITOR_MODEL",
}

CONTROL_ENV_KEYS = [
    "EDITORIAL_AGENT_TIMEOUT_SECONDS",
    "EDITORIAL_AGENT_MAX_CONCURRENCY",
    "EDITORIAL_AGENT_MAX_ATTEMPTS",
]


@dataclass(frozen=True)
class EditorialAiConfig:
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


class AgentCallTimeout(TimeoutError):
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


class AgentsSdkTextClient(AgentTextClient):
    def __init__(self, config: EditorialAiConfig) -> None:
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
        semaphore = asyncio.Semaphore(max(1, max_concurrency))
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
        del role, model, instructions, output_type
        payload = json.loads(user_input)
        choices = payload.get("choices", [])
        return json.dumps(
            {
                "items": [
                    {
                        "award_type": choice.get("award_type"),
                        "player_id": choice.get("player_id"),
                        "title": f"{choice.get('player_name', 'Player')} made the edit",
                        "body": str(choice.get("selection", {}).get("editorial_reason") or ""),
                    }
                    for choice in choices
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )


def load_editorial_ai_config(
    env_path: str | Path = ".env.local",
    *,
    require_credentials: bool = True,
) -> EditorialAiConfig:
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
    return EditorialAiConfig(
        api_key=api_key,
        base_url=base_url,
        models=models,
        loaded_keys=loaded_keys,
        timeout_seconds=float(env.get("EDITORIAL_AGENT_TIMEOUT_SECONDS", DEFAULT_AGENT_TIMEOUT_SECONDS)),
        max_concurrency=max(1, max_concurrency),
        max_attempts=max(1, max_attempts),
    )


def _load_env(env_path: str | Path) -> dict[str, str]:
    env: dict[str, str] = {}
    path = Path(env_path)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    env.update(os.environ)
    return env
