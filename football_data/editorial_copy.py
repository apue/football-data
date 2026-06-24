from __future__ import annotations

import html
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from football_data.editorial_display_names import player_display_name
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
        item = _static_copy_item(choice, language)
        items.append(item)
    return {"items": items, "warnings": []}


def _static_copy_item(choice: dict[str, Any], language: str) -> dict[str, Any]:
    player_name = str(choice["player_name"])
    display_name = _display_player_name(player_name, language)
    award_type = str(choice["selection"]["award_type"])
    metrics = choice.get("metrics") or {}
    chips = (choice.get("evidence_chips") or {}).get(language) or []
    if language == "zh":
        title, body = _static_zh_copy(display_name, award_type, metrics, chips)
    else:
        title, body = _static_en_copy(display_name, award_type, metrics, chips)
    return {
        "award_type": award_type,
        "player_id": choice["player_id"],
        "title": title,
        "body": body,
        "warnings": ["static fallback copy"],
    }


def _static_en_copy(
    player_name: str,
    award_type: str,
    metrics: dict[str, Any],
    chips: list[str],
) -> tuple[str, str]:
    goals = int(metrics.get("goals") or 0)
    assists = int(metrics.get("assists") or 0)
    on_target = int(metrics.get("on_target") or 0)
    if award_type == "player_of_the_day":
        if goals >= 3:
            title = "The hat-trick was enough"
            body = f"{player_name}'s hat-trick settles the main argument."
        elif goals == 2:
            title = "Two goals, clear case"
            body = f"{player_name}'s two goals put him in the top group."
        elif goals == 1:
            title = "The decisive scorer"
            body = f"{player_name}'s goal gives this pick its starting point."
        else:
            title = f"{player_name} led the day"
            body = f"{player_name} had the strongest evidence packet for this slot."
        if int(metrics.get("comeback_winner") or 0):
            body += " It was also the comeback winner."
        elif int(metrics.get("match_winning_goal") or 0):
            body += " One of them was the match-winner."
        if assists:
            body += f" He also added {assists} assist{'s' if assists != 1 else ''}."
        elif on_target >= 3:
            body += f" He also put {on_target} shots on target."
        return title, body
    if award_type == "impact_pick":
        title = "The moment that mattered"
        body = f"{player_name} gets the impact slot because the decisive evidence is clear: {_join_chips(chips)}."
        return title, body
    if award_type == "progression_pick":
        title = "The route forward"
        line_breaks = int(metrics.get("line_breaks_completed") or 0)
        progressions = int(metrics.get("ball_progressions") or 0)
        body = (
            f"{player_name} earns the progression slot with {line_breaks} line breaks"
            f" and {progressions} ball progressions."
        )
        return title, body
    if award_type == "defensive_pick":
        title = "The defensive answer"
        body = f"{player_name} stood out through defensive actions: {_join_chips(chips)}."
        return title, body
    if award_type == "goalkeeper_watch":
        title = "The clean sheet under pressure"
        body = f"{player_name} gets the goalkeeper note because the clean sheet came with measurable pressure."
        return title, body
    if award_type == "hidden_gem":
        title = "The quieter useful game"
        body = f"{player_name} is the hidden-gem pick for the less obvious work behind the headline choices."
        return title, body
    return f"{player_name} made the edit", f"{player_name} had the clearest evidence for this slot."


def _static_zh_copy(
    player_name: str,
    award_type: str,
    metrics: dict[str, Any],
    chips: list[str],
) -> tuple[str, str]:
    goals = int(metrics.get("goals") or 0)
    assists = int(metrics.get("assists") or 0)
    on_target = int(metrics.get("on_target") or 0)
    if award_type == "player_of_the_day":
        if goals >= 3:
            title = "帽子戏法"
            body = f"{player_name}这场完成帽子戏法。"
        elif goals == 2:
            title = "梅开二度"
            body = f"{player_name}这场梅开二度。"
        elif goals == 1:
            title = "制胜球" if int(metrics.get("match_winning_goal") or 0) else "取得进球"
            body = f"{player_name}这场打进一球。"
        else:
            title = f"{player_name} 进入每日最佳"
            body = f"{player_name}这场表现进入每日最佳。"
        if int(metrics.get("comeback_winner") or 0):
            if "制胜" not in title and "反超" not in title:
                title = f"{title}制胜"
            body += " 这还是逆转制胜球。"
        elif int(metrics.get("match_winning_goal") or 0):
            if "制胜" not in title:
                title = f"{title}制胜"
            body += " 其中包括制胜球。"
        if assists:
            body += f" 他还送出 {assists} 次助攻。"
        elif on_target >= 3:
            body += f" 另外还有 {on_target} 次射正。"
        return title, body
    if award_type == "impact_pick":
        title = "制胜球" if int(metrics.get("match_winning_goal") or 0) else "关键进球"
        body = f"{player_name}这次影响力精选来自：{_join_chips(chips, language='zh')}。"
        return title, body
    if award_type == "progression_pick":
        title = "持续接球向前"
        line_breaks = int(metrics.get("line_breaks_completed") or 0)
        progressions = int(metrics.get("ball_progressions") or 0)
        body = f"{player_name}这场有 {line_breaks} 次打穿防线和 {progressions} 次带球推进。"
        return title, body
    if award_type == "defensive_pick":
        title = "防守端最抢眼"
        body = f"{player_name}这场防守端很突出：{_join_chips(chips, language='zh')}。"
        return title, body
    if award_type == "goalkeeper_watch":
        title = "有压力的零封"
        body = f"{player_name}的门将关注来自零封，以及对手制造出的可量化压力。"
        return title, body
    if award_type == "hidden_gem":
        title = "不抢镜，但有用"
        body = f"{player_name}是这期隐藏亮点，价值在于那些不一定进入头条的持续贡献。"
        return title, body
    return f"{player_name} 入选", f"{player_name} 的证据最能支撑这个席位。"


def _join_chips(chips: list[str], *, language: str = "en") -> str:
    separator = "、" if language == "zh" else ", "
    fallback = "关键证据" if language == "zh" else "strong match evidence"
    return separator.join(str(chip) for chip in chips[:3]) or fallback


def _display_player_name(player_name: str, language: str) -> str:
    if language != "zh":
        return player_name
    from football_data.editorial import ZH_PLAYER_NAMES

    fallback = ZH_PLAYER_NAMES.get(player_name, player_name)
    return player_display_name(player_name, language, fallback=fallback)


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
