from __future__ import annotations

import html
import re
from typing import Any


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
