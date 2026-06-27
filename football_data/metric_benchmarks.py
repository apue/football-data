from __future__ import annotations

from typing import Any


def progression_benchmark(player: dict[str, Any]) -> dict[str, Any]:
    line_breaks = _num(player, "line_breaks_completed")
    ball_progression_type = _num(player, "distribution_ball_progression")
    direct_progressions = _num(player, "ball_progressions")
    take_ons = _num(player, "take_ons")
    step_ins = _num(player, "step_ins")
    through = _num(player, "direction_through")
    around = _num(player, "direction_around")
    deep_units = (
        _num(player, "units_4_attacking_line") * 1.8
        + _num(player, "units_4_attacking_midfield_line") * 1.5
        + _num(player, "units_3_attacking_line") * 1.1
    )
    support_actions = direct_progressions + take_ons + step_ins + ball_progression_type
    score = (
        deep_units
        + through * 0.7
        + around * 0.25
        + direct_progressions * 1.6
        + take_ons * 1.4
        + step_ins * 0.7
        + ball_progression_type * 2.0
    )
    pass_only_volume = (
        line_breaks >= 15
        and ball_progression_type == 0
        and direct_progressions <= 1
        and take_ons == 0
        and _num(player, "in_between") == 0
        and _num(player, "in_behind") <= 1
    )
    if pass_only_volume:
        score *= 0.55
    quality = "strong" if score >= 24 else "useful" if score >= 18 else "thin"
    return {
        "score": round(score, 2),
        "quality": quality,
        "support_actions": support_actions,
        "pass_only_line_break_volume": pass_only_volume,
    }


def hidden_gem_profile(player: dict[str, Any]) -> dict[str, Any]:
    defensive_activity = (
        _num(player, "possession_regains")
        + _num(player, "possession_interrupted")
        + _num(player, "blocks")
    )
    close_result = abs(_num(player, "team_final_goals") - _num(player, "opponent_final_goals")) <= 1
    defensive_score = _role_score(player, "defensive")
    if close_result and defensive_score >= 30 and defensive_activity >= 16:
        return {
            "eligible": True,
            "profile": "defensive_resistance",
            "score": round(defensive_score + defensive_activity, 2),
        }

    off_ball_score = _role_score(player, "off_ball")
    if off_ball_score >= 45 and (_num(player, "in_behind") + _num(player, "in_between")) >= 25:
        return {
            "eligible": True,
            "profile": "off_ball_threat",
            "score": round(off_ball_score, 2),
        }

    progression = progression_benchmark(player)
    if progression["quality"] == "strong":
        return {
            "eligible": True,
            "profile": "progression_audit",
            "score": progression["score"],
        }

    return {
        "eligible": False,
        "profile": "insufficient_evidence",
        "score": max(defensive_score, off_ball_score, progression["score"]),
    }


def _role_score(player: dict[str, Any], role: str) -> float:
    return float(player.get("role_scores", {}).get(role, 0) or 0)


def _num(player: dict[str, Any], key: str) -> float:
    return float(player.get(key) or 0)
