from __future__ import annotations

import html
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from football_data.llm_client import AgentTextClient


class CopyItem(BaseModel):
    award_type: str
    player_id: str
    title: str
    body: str
    warnings: list[str] = Field(default_factory=list)


class CopyOutput(BaseModel):
    items: list[CopyItem]
    warnings: list[str] = Field(default_factory=list)


def build_copy_payloads(
    selection_decision: dict[str, Any],
    candidate_pool: dict[str, Any],
) -> dict[str, Any]:
    candidates = {
        str(candidate["player_id"]): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
    }
    choices = []
    for item in selection_decision.get("selected", []):
        candidate = candidates.get(str(item.get("player_id")))
        if candidate:
            award_type = str(item.get("award_type") or "")
            active_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
            choices.append(
                {
                    **candidate,
                    "metrics": active_context.get("metrics", candidate.get("metrics", {})),
                    "evidence_chips": active_context.get(
                        "evidence_chips",
                        candidate.get("evidence_chips", {"en": [], "zh": []}),
                    ),
                    "active_award_context": active_context,
                    "selection": item,
                }
            )
    return {"match_date": candidate_pool["match_date"], "choices": choices}


def generate_copy(
    payload: dict[str, Any],
    *,
    fake: bool,
    text_client: AgentTextClient | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
    models: dict[str, str] | None = None,
) -> dict[str, Any]:
    if fake or text_client is None:
        return {
            "en": _fake_language_copy(payload, "en"),
            "zh": _fake_language_copy(payload, "zh"),
        }
    profiles = profiles or {}
    models = models or {}
    return {
        "en": _agent_language_copy(payload, "en", text_client, profiles["en"], models),
        "zh": _agent_language_copy(payload, "zh", text_client, profiles["zh"], models),
    }


def _fake_language_copy(payload: dict[str, Any], language: str) -> dict[str, Any]:
    items = []
    for choice in payload.get("choices", []):
        player_name = str(choice["player_name"])
        reason = str(choice.get("selection", {}).get("editorial_reason") or "")
        if language == "zh":
            title = f"{player_name} 留在编辑精选里"
            body = f"{player_name} 的入选来自候选池复核：{reason}"
        else:
            title = f"{player_name} stays in the edit"
            body = f"{player_name} makes the final cut after reranking the candidate pool: {reason}"
        items.append(
            {
                "award_type": choice["selection"]["award_type"],
                "player_id": choice["player_id"],
                "title": title,
                "body": body,
                "warnings": [],
            }
        )
    return {"items": items, "warnings": []}


def _agent_language_copy(
    payload: dict[str, Any],
    language: str,
    text_client: AgentTextClient,
    profile: dict[str, Any],
    models: dict[str, str],
) -> dict[str, Any]:
    model_key = str(profile.get("model_key") or "en_editor")
    model = models.get(model_key, next(iter(models.values())))
    base_instructions = [
        "Write final editorial card copy from the provided JSON only.",
        "Use active_award_context, metrics, evidence_chips, and selection as the primary source for each card.",
        "Do not use a candidate's other award_contexts unless they support the selected award_type.",
        "Return strict JSON with items containing award_type, player_id, title, body.",
        "Do not add unsupported facts.",
    ]
    instructions = "\n".join([*base_instructions, *[str(item) for item in profile.get("instructions", [])]])
    response = text_client.complete(
        role=f"{language}_copy_editor",
        model=model,
        instructions=instructions,
        user_input=json.dumps({"language": language, **payload}, ensure_ascii=False),
        output_type=CopyOutput,
    )
    return json.loads(response)


def content_html(body: str) -> str:
    return f"<p>{html.escape(sanitize_copy_body(body), quote=False)}</p>"


def sanitize_copy_body(body: str) -> str:
    text = body
    text = re.sub(
        r"\boffered (\d+) times behind the defen[cs]e\b",
        r"received \1 offers",
        text,
        flags=re.IGNORECASE,
    )
    return text
