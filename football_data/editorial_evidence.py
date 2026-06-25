from __future__ import annotations

from typing import Any

from football_data.editorial_scoring import clean_number


def choice_metrics(player: dict[str, Any], award_type: str) -> dict[str, int | float]:
    if award_type == "goalkeeper_watch":
        metric_names = [
            "clean_sheet",
            "opponent_xg",
            "opponent_attempts_on_target",
            "opponent_attempts_total",
            "keeper_saved_shots",
        ]
    elif award_type in {"player_of_the_day", "impact_pick"} and has_direct_scoring_case(player):
        metric_names = [
            "shots",
            "on_target",
            "goals",
            "assists",
            "goal_involvements",
            "brace",
            "hat_trick",
            "opening_goal",
            "equalizing_goal",
            "go_ahead_goal",
            "match_winning_goal",
            "late_goal",
            "stoppage_time_goal",
            "late_match_winning_goal",
            "comeback_equalizer",
            "comeback_winner",
            "only_goal_winner",
            "substitute_goal",
            "substitute_brace",
        ]
    elif award_type == "progression_pick":
        metric_names = [
            "passes_completed",
            "line_breaks_completed",
            "ball_progressions",
            "take_ons",
            "step_ins",
            "offers_received",
        ]
    elif award_type == "defensive_pick":
        metric_names = [
            "possession_regains",
            "possession_interrupted",
            "tackles_won",
            "interceptions",
            "blocks",
            "clearances",
        ]
    elif award_type == "hidden_gem":
        metric_names = [
            "offers_received",
            "in_behind",
            "in_between",
            "line_breaks_completed",
            "ball_progressions",
            "possession_regains",
            "possession_interrupted",
            "blocks",
        ]
    else:
        metric_names = [
            "shots",
            "on_target",
            "goals",
            "assists",
            "goal_involvements",
            "line_breaks_completed",
            "ball_progressions",
            "possession_regains",
            "possession_interrupted",
            "blocks",
        ]
    return {
        metric: clean_number(float(player.get(metric) or 0))
        for metric in metric_names
        if float(player.get(metric) or 0) > 0
    }


def evidence_chips(player: dict[str, Any], award_type: str) -> dict[str, list[str]]:
    en: list[str] = []
    zh: list[str] = []
    if award_type == "goalkeeper_watch":
        if int(player.get("clean_sheet") or 0) > 0:
            en.append("clean sheet")
            zh.append("零封")
        if float(player.get("opponent_attempts_on_target") or 0) >= 5:
            en.append("faced heavy on-target pressure")
            zh.append("对手射正压力高")
        if float(player.get("opponent_xg") or 0) >= 1.0:
            en.append("xG pressure resisted")
            zh.append("承受较高xG")
        if float(player.get("keeper_saved_shots") or 0) >= 5:
            en.append("Saved outcomes in shot log")
            zh.append("射门记录Saved结果较多")
        if not en:
            en.append("clean-sheet profile")
            zh.append("零封画像")
        return {"en": en[:4], "zh": zh[:4]}

    if int(player.get("hat_trick") or 0) > 0:
        en.append("hat-trick")
        zh.append("帽子戏法")
    elif int(player.get("brace") or 0) > 0:
        en.append("brace")
        zh.append("梅开二度")

    if int(player.get("substitute_brace") or 0) > 0:
        en.append("substitute brace")
        zh.append("替补双响")
    elif int(player.get("substitute_goal") or 0) > 0:
        en.append("substitute goal")
        zh.append("替补进球")

    if int(player.get("only_goal_winner") or 0) > 0:
        en.append("only goal")
        zh.append("全场唯一进球")

    if int(player.get("comeback_winner") or 0) > 0:
        en.append("comeback winner")
        zh.append("逆转制胜")
    elif int(player.get("comeback_equalizer") or 0) > 0:
        en.append("comeback equaliser")
        zh.append("逆转扳平")

    if int(player.get("late_match_winning_goal") or 0) > 0:
        en.append("late winner")
        zh.append("补时制胜")
    elif int(player.get("match_winning_goal") or 0) > 0:
        en.append("match-winning goal")
        zh.append("打入制胜球")
    elif int(player.get("opening_goal") or 0) > 0:
        en.append("opening goal")
        zh.append("首开纪录")
    elif int(player.get("go_ahead_goal") or 0) > 0:
        en.append("go-ahead goal")
        zh.append("取得领先")
    elif int(player.get("equalizing_goal") or 0) > 0:
        en.append("equaliser")
        zh.append("扳平进球")

    goals = int(player.get("goals") or 0)
    assists = int(player.get("assists") or 0)
    if goals >= 3 and "hat-trick" not in en:
        en.append("hat-trick")
        zh.append("帽子戏法")
    elif goals == 2 and "brace" not in en:
        en.append("brace")
        zh.append("梅开二度")
    elif goals == 1:
        en.append("goal scorer")
        zh.append("取得进球")
    if assists >= 2:
        en.append("multiple assists")
        zh.append("多次助攻")
    elif assists == 1:
        en.append("assist")
        zh.append("送出助攻")

    _append_if(en, zh, player, "on_target", 3, "high shot quality", "射门质量突出")
    direct_scoring_case = has_direct_scoring_case(player)
    include_progression = award_type in {"progression_pick", "hidden_gem"} or not direct_scoring_case
    include_off_ball = award_type == "hidden_gem" or not direct_scoring_case
    include_defensive = award_type in {"defensive_pick", "hidden_gem"} or not direct_scoring_case
    if include_progression:
        _append_if(en, zh, player, "line_breaks_completed", 15, "repeated line breaks", "持续打穿防线")
        _append_if(en, zh, player, "ball_progressions", 10, "constant carries", "推进很活跃")
    if include_off_ball:
        _append_if(en, zh, player, "offers_received", 25, "found again and again", "持续接应")
        _append_if(en, zh, player, "in_between", 15, "between-line presence", "在防线之间活跃")
    if include_defensive:
        _append_if(en, zh, player, "possession_regains", 8, "ball-winning profile", "夺回球权能力突出")
        _append_if(en, zh, player, "possession_interrupted", 8, "disrupted attacks", "持续破坏进攻")

    if not en:
        if award_type == "defensive_pick":
            en.append("defensive activity profile")
            zh.append("防守参与度突出")
        elif award_type == "progression_pick":
            en.append("progression profile")
            zh.append("推进画像突出")
        else:
            en.append("balanced data profile")
            zh.append("综合数据画像突出")

    return {"en": en[:4], "zh": zh[:4]}


def has_direct_scoring_case(player: dict[str, Any]) -> bool:
    return (
        int(player.get("goals") or 0) > 0
        or int(player.get("assists") or 0) > 0
        or int(player.get("goal_involvements") or 0) > 0
    )


def top_components_across_roles(player: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for score_name, items in player["score_components"].items():
        if score_name == "goalkeeper" and str(player.get("position") or "").upper() != "GK":
            continue
        for item in items:
            components.append({**item, "score": score_name})
    return sorted(components, key=lambda item: item["contribution"], reverse=True)


def _append_if(
    en: list[str],
    zh: list[str],
    player: dict[str, Any],
    metric: str,
    threshold: float,
    en_text: str,
    zh_text: str,
) -> None:
    if float(player.get(metric) or 0) >= threshold:
        en.append(en_text)
        zh.append(zh_text)
