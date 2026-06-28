from __future__ import annotations

from typing import Any

from football_data.editorial_display_names import player_display_name


def build_test_selection_decision(
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    selection_config = experiment["selection"]
    if selection_config.get("strategy") != "overall_slate_v1":
        raise ValueError("test selection helper only supports selection.strategy overall_slate_v1")

    candidates = list(candidate_pool.get("selectable_candidates", []))
    award_limits = _selection_award_limits(selection_config)
    slate_constraints = selection_config.get("slate_constraints", {})
    if not isinstance(slate_constraints, dict):
        slate_constraints = {}
    target_count = _target_public_card_count(candidate_pool, selection_config, award_limits)
    award_preference = [
        str(item)
        for item in selection_config.get(
            "overall_slate_award_preference",
            [
                "player_of_the_day",
                "impact_pick",
            ],
        )
    ]
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    award_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    match_counts: dict[str, int] = {}
    ordered = sorted(candidates, key=_overall_slate_score, reverse=True)
    for candidate in ordered:
        if len(selected) >= target_count:
            break
        player_id = str(candidate["player_id"])
        if player_id in used:
            continue
        if not _slate_allows(candidate, team_counts, match_counts, slate_constraints):
            continue
        award_type = _best_overall_slate_award(
            candidate,
            award_counts,
            award_limits,
            award_preference,
        )
        if not award_type:
            continue
        selected.append(_selected_item(award_type, candidate))
        used.add(player_id)
        award_counts[award_type] = award_counts.get(award_type, 0) + 1
        _count_slate(candidate, team_counts, match_counts)
    skipped = _skipped_higher_ranked_potd(candidates, selected)
    return {
        "selected": selected,
        "skipped_higher_ranked": skipped,
        "skipped_notable_candidates": [],
        "warnings": [],
    }


def build_test_copy(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "en": _test_language_copy(payload, "en"),
        "zh": _test_language_copy(payload, "zh"),
    }


def write_passing_test_editorial_loop(
    audit_dir,
    selection: dict[str, Any],
    copy: dict[str, Any],
    candidate_pool: dict[str, Any] | None = None,
    experiment: dict[str, Any] | None = None,
) -> None:
    review_payload = None
    if candidate_pool is not None and experiment is not None:
        review_payload = _selection_review_payload(selection, candidate_pool, experiment)
    _write_test_json(
        audit_dir / "selection_rounds" / "round_1" / "selection_decision.json",
        selection,
    )
    _write_test_json(
        audit_dir / "selection_rounds" / "round_1" / "selection_review.json",
        build_passing_test_selection_review(selection, review_payload),
    )
    _write_test_json(audit_dir / "copy_rounds" / "round_1" / "copy.json", copy)
    _write_test_json(
        audit_dir / "copy_rounds" / "round_1" / "copy_review.json",
        build_passing_test_copy_review(copy),
    )


def build_passing_test_selection_review(
    selection: dict[str, Any],
    review_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = list(selection["selected"])
    required_unselected = _required_unselected_reviews(review_payload)
    strongest_omitted = _first_player_id(
        (review_payload or {}).get("required_unselected_candidate_reviews")
    ) or _first_player_id((review_payload or {}).get("required_impact_candidate_reviews"))
    impact_challenger = _first_player_id((review_payload or {}).get("required_impact_candidate_reviews"))
    add_challenger = _first_player_id((review_payload or {}).get("card_count_challengers"))
    return {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": [
            "selected_card_convincingness",
            "obvious_omission",
            "alternative_slate_comparison",
            "weakest_selected_card",
            "strongest_omitted_card",
            "impact_challenger_comparison",
            "card_count_verdict",
        ],
        "selected_player_reviews": [
            {
                "player_id": item["player_id"],
                "verdict": "pass",
                "note": "The public case is supported by direct match evidence.",
            }
            for item in selected
        ],
        "unselected_candidate_reviews": required_unselected,
        "slate_assessment": {
            "reader_questions": ["Is there a stronger direct-impact omission?"],
            "alternative_slate_comparison": [
                {"card_count": len(selected), "tradeoff": "current slate"},
                {"card_count": len(selected) + 1, "tradeoff": "add strongest omitted card"},
                {"card_count": max(0, len(selected) - 1), "tradeoff": "drop weakest selected"},
            ],
            "weakest_selected_card": {
                "player_id": selected[-1]["player_id"],
                "reason": "Checked against available omissions.",
            },
            "strongest_omitted_card": {
                "player_id": strongest_omitted,
                "reason": "No omitted candidate forced a replacement.",
            },
            "drop_weakest_verdict": {
                "decision": "keep",
                "reason": "The weakest selected card remains above the publishable line.",
            },
            "replace_weakest_verdict": {
                "decision": "keep",
                "replacement_player_id": strongest_omitted,
                "reason": "No replacement improves the slate.",
            },
            "impact_challenger_verdict": {
                "player_id": impact_challenger,
                "decision": "omit",
                "reason": "The strongest omitted impact challenger was checked.",
            },
            "add_card_verdict": {
                "player_id": add_challenger,
                "decision": "keep_count",
                "reason": "Adding the strongest omitted card would not improve the slate.",
            },
            "preferred_card_count": len(selected),
            "revision_decision": "keep",
        },
        "blocking_findings": [],
        "resolved_objections": [],
        "unresolved_objections": [],
        "revision_summary": "No blocking selection issue remains.",
    }


def _selection_review_payload(
    selection: dict[str, Any],
    candidate_pool: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    from football_data.editorial_loop import build_selection_review_payload
    from football_data.editorial_registry import load_selection_review_profile
    from football_data.editorial_validation import validate_selection_decision

    review_profile = load_selection_review_profile(experiment["selection_review_profile"])
    return build_selection_review_payload(
        selection_decision=selection,
        candidate_pool=candidate_pool,
        selection_validation=validate_selection_decision(selection, candidate_pool, experiment),
        review_profile=review_profile,
        selection_config=experiment["selection"],
    )


def _required_unselected_reviews(review_payload: dict[str, Any] | None) -> list[dict[str, str]]:
    seen: set[str] = set()
    reviews: list[dict[str, str]] = []
    for key in (
        "required_unselected_candidate_reviews",
        "required_impact_candidate_reviews",
        "card_count_challengers",
    ):
        for item in (review_payload or {}).get(key, []):
            if not isinstance(item, dict):
                continue
            player_id = str(item.get("player_id") or "")
            if not player_id or player_id in seen:
                continue
            seen.add(player_id)
            reviews.append(
                {
                    "player_id": player_id,
                    "status": "omit",
                    "note": "Checked as a required omitted candidate.",
                }
            )
    return reviews


def _first_player_id(items: Any) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        player_id = str(item.get("player_id") or "").strip()
        if player_id:
            return player_id
    return None


def build_passing_test_copy_review(copy: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "pass",
        "reviewed_dimensions": [
            "fact_support",
            "english_flow",
            "zh_style",
            "title_core_fact",
            "unsupported_claims",
        ],
        "item_reviews": [
            {
                "player_id": item["player_id"],
                "language": language,
                "verdict": "pass",
                "note": "The copy is supported by the selected evidence packet.",
            }
            for language in ("en", "zh")
            for item in copy.get(language, {}).get("items", [])
            if isinstance(item, dict)
        ],
        "blocking_findings": [],
        "resolved_comments": [],
        "unresolved_comments": [],
        "revision_summary": "No blocking copy issue remains.",
    }


def _write_test_json(path, payload: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _test_language_copy(payload: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "items": [_static_copy_item(choice, language) for choice in payload.get("choices", [])],
        "warnings": [],
    }


def _selection_award_limits(selection_config: dict[str, Any]) -> dict[str, int]:
    raw_limits = selection_config.get("award_limits")
    if not isinstance(raw_limits, dict):
        return {}
    return {str(key): int(value) for key, value in raw_limits.items()}


def _target_public_card_count(
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any],
    award_limits: dict[str, int],
) -> int:
    public_card_count = selection_config.get("public_card_count")
    if not isinstance(public_card_count, dict):
        return sum(int(value or 0) for value in award_limits.values())
    min_count = int(public_card_count.get("min") or 0)
    max_count = int(public_card_count.get("max") or 0)
    if min_count <= 0 or max_count <= 0:
        return sum(int(value or 0) for value in award_limits.values())
    if min_count > max_count:
        min_count, max_count = max_count, min_count
    candidate_count = len(candidate_pool.get("selectable_candidates", []))
    return max(min_count, min(max_count, candidate_count))


def _overall_slate_score(candidate: dict[str, Any]) -> tuple[float, float, float, float, float]:
    headline_rank = int(candidate.get("headline_rank") or 9999)
    if "player_of_the_day" in candidate.get("eligible_awards", []):
        direct, headline, decisive, rank_component = _candidate_award_score(
            candidate,
            "player_of_the_day",
        )
        return (3, direct, headline, decisive, rank_component)
    eligible_scores = [
        _candidate_award_score(candidate, str(award_type))
        for award_type in candidate.get("eligible_awards", [])
    ]
    best_role_score = max((float(score[0]) for score in eligible_scores), default=0.0)
    return (
        2,
        best_role_score,
        float(candidate.get("headline_score") or 0),
        0,
        -float(headline_rank),
    )


def _candidate_award_score(candidate: dict[str, Any], award_type: str) -> tuple[float, float, float, float]:
    role_scores = candidate.get("role_scores") or {}
    metrics = ((candidate.get("award_contexts") or {}).get(award_type) or {}).get("metrics") or {}
    headline_rank = int(candidate.get("headline_rank") or 9999)
    if award_type == "player_of_the_day":
        team_won = int(candidate.get("team_final_goals") or 0) > int(candidate.get("opponent_final_goals") or 0)
        direct_tier = (
            _num(metrics, "goals") * 100
            + _num(metrics, "assists") * 35
            + _num(metrics, "hat_trick") * 50
            + _num(metrics, "brace") * 10
            + (20 if team_won else 0)
        )
        decisive_tiebreak = (
            _num(metrics, "match_winning_goal")
            + _num(metrics, "comeback_winner")
            + _num(metrics, "late_match_winning_goal")
        )
        return (direct_tier, float(candidate.get("headline_score") or 0), decisive_tiebreak, -headline_rank)
    if award_type == "impact_pick":
        return (
            float(role_scores.get("impact") or 0),
            float(candidate.get("headline_score") or 0),
            -headline_rank,
            0,
        )
    return (float(candidate.get("headline_score") or 0), -headline_rank, 0, 0)


def _best_overall_slate_award(
    candidate: dict[str, Any],
    award_counts: dict[str, int],
    award_limits: dict[str, int],
    award_preference: list[str],
) -> str | None:
    eligible = {str(item) for item in candidate.get("eligible_awards", [])}
    for award_type in award_preference:
        if award_type not in eligible:
            continue
        if award_counts.get(award_type, 0) >= int(award_limits.get(award_type, 0)):
            continue
        return award_type
    return None


def _selected_item(award_type: str, candidate: dict[str, Any]) -> dict[str, Any]:
    award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
    chips = (award_context.get("evidence_chips") or {}).get("en")
    if not chips:
        chips = candidate.get("evidence_chips", {}).get("en", [])
    reason = ", ".join(str(chip) for chip in chips[:2]) or "strong all-round evidence"
    return {
        "award_type": award_type,
        "player_id": candidate["player_id"],
        "player_name": candidate["player_name"],
        "team": candidate["team"],
        "editorial_reason": f"Selected from the candidate pool for {reason}.",
        "evidence_used": [str(chip) for chip in chips[:4]],
        "selection_risk": "Low: deterministic evidence supports the selection.",
    }


def _skipped_higher_ranked_potd(
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    selected_ids = {str(item["player_id"]) for item in selected}
    selected_potd_ids = {
        item["player_id"]
        for item in selected
        if item["award_type"] == "player_of_the_day"
    }
    selected_potd_ranks = [
        int(candidate.get("headline_rank") or 9999)
        for candidate in candidates
        if candidate["player_id"] in selected_potd_ids
    ]
    worst_selected_rank = max(selected_potd_ranks or [0])
    for candidate in candidates:
        if "player_of_the_day" not in candidate.get("eligible_awards", []):
            continue
        rank = int(candidate.get("headline_rank") or 9999)
        if (
            rank < worst_selected_rank
            and candidate["player_id"] not in selected_potd_ids
            and str(candidate["player_id"]) not in selected_ids
        ):
            skipped.append(
                {
                    "award_type": "player_of_the_day",
                    "player_id": candidate["player_id"],
                    "player_name": candidate["player_name"],
                    "coarse_rank": candidate.get("headline_rank"),
                    "reason": "Higher raw rank, but the selected slate gives a broader match-day story.",
                }
            )
    return skipped


def _slate_allows(
    candidate: dict[str, Any],
    team_counts: dict[str, int],
    match_counts: dict[str, int],
    slate_constraints: dict[str, Any],
) -> bool:
    max_per_team = int(slate_constraints.get("max_per_team") or 0)
    max_per_match = int(slate_constraints.get("max_per_match") or 0)
    team = str(candidate.get("team") or "")
    match_key = str(candidate.get("match_key") or "")
    if max_per_team and team_counts.get(team, 0) >= max_per_team:
        return False
    if max_per_match and match_counts.get(match_key, 0) >= max_per_match:
        return False
    return True


def _count_slate(
    candidate: dict[str, Any],
    team_counts: dict[str, int],
    match_counts: dict[str, int],
) -> None:
    team = str(candidate.get("team") or "")
    match_key = str(candidate.get("match_key") or "")
    team_counts[team] = team_counts.get(team, 0) + 1
    match_counts[match_key] = match_counts.get(match_key, 0) + 1


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
        "warnings": ["test static copy"],
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
            body = f"{player_name} had the strongest evidence packet for this public card."
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
        body = f"{player_name} gets the impact angle because the decisive evidence is clear: {_join_chips(chips)}."
        return title, body
    if award_type in {"progression_pick", "defensive_pick", "goalkeeper_watch", "hidden_gem"}:
        raise ValueError(f"{award_type} is audit-only and cannot be rendered as public copy")
    return f"{player_name} made the edit", f"{player_name} had the clearest evidence for this public card."


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
    return f"{player_name} 入选", f"{player_name} 的证据最能支撑这个公共选择。"


def _join_chips(chips: list[str], *, language: str = "en") -> str:
    separator = "、" if language == "zh" else ", "
    fallback = "关键证据" if language == "zh" else "strong match evidence"
    return separator.join(str(chip) for chip in chips[:3]) or fallback


def _display_player_name(player_name: str, language: str) -> str:
    if language != "zh":
        return player_name
    return player_display_name(player_name, language, fallback=player_name)


def _num(metrics: dict[str, Any], key: str) -> float:
    return float(metrics.get(key) or 0)
