from __future__ import annotations

import html
import re
from typing import Any

from football_data.editorial_display_names import player_display_name


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
    fake: bool = True,
    text_client: object | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
    models: dict[str, str] | None = None,
) -> dict[str, Any]:
    del profiles, models
    if fake and text_client is None:
        return {
            "en": _fake_language_copy(payload, "en"),
            "zh": _fake_language_copy(payload, "zh"),
        }
    raise RuntimeError(
        "Cloud copy generation has been retired. Write copy.json through the local editor workflow."
    )


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
    if award_type in {"progression_pick", "defensive_pick", "goalkeeper_watch", "hidden_gem"}:
        raise ValueError(f"{award_type} is audit-only and cannot be rendered as public copy")
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
    if award_type in {"progression_pick", "defensive_pick", "goalkeeper_watch", "hidden_gem"}:
        raise ValueError(f"{award_type} is audit-only and cannot be rendered as public copy")
    return f"{player_name} 入选", f"{player_name} 的证据最能支撑这个席位。"


def _join_chips(chips: list[str], *, language: str = "en") -> str:
    separator = "、" if language == "zh" else ", "
    fallback = "关键证据" if language == "zh" else "strong match evidence"
    return separator.join(str(chip) for chip in chips[:3]) or fallback


def _display_player_name(player_name: str, language: str) -> str:
    if language != "zh":
        return player_name
    return player_display_name(player_name, language, fallback=player_name)


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
