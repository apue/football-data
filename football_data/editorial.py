from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SCORING_CONFIG = Path("config/scoring/v0.1.json")


AWARD_LABELS = {
    "player_of_the_day": {"en": "Player of the Day", "zh": "每日最佳球员"},
    "progression_pick": {"en": "Progression Pick", "zh": "推进精选"},
    "defensive_pick": {"en": "Defensive Pick", "zh": "防守精选"},
    "hidden_gem": {"en": "Hidden Gem", "zh": "隐藏亮点"},
}


ZH_TEAM_NAMES = {
    "Algeria": "阿尔及利亚",
    "Argentina": "阿根廷",
    "Austria": "奥地利",
    "France": "法国",
    "Jordan": "约旦",
    "Senegal": "塞内加尔",
}


ZH_PLAYER_NAMES = {
    "ABDALLAH NASIB": "纳西布",
    "Kylian MBAPPE": "姆巴佩",
    "Lionel MESSI": "梅西",
    "Nicolas SEIWALD": "塞瓦尔德",
    "Rayan AIT-NOURI": "艾特-努里",
    "Rodrigo DE PAUL": "德保罗",
}


def build_editorial_report(
    db_path: str | Path,
    match_date: str | None = None,
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
) -> dict[str, Any]:
    scoring = _load_scoring_config(scoring_config_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        selected_date = match_date or _latest_match_date(conn)
        matches = _matches_for_date(conn, selected_date)
        players = [_score_player(row, scoring) for row in _player_rows_for_date(conn, selected_date)]
    finally:
        conn.close()

    choices = _select_choices(players, scoring)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": selected_date,
        "scoring_version": scoring["version"],
        "matches": matches,
        "choices": choices,
        "audit": _build_audit(players, choices, selected_date),
    }


def write_editorial_artifacts(
    report: dict[str, Any],
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
) -> None:
    site_path = Path(site_dir)
    editorial_path = site_path / "editorial"
    dated_path = editorial_path / report["match_date"]
    reports_path = Path(reports_dir) / "editorial"
    dated_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    source_markdown_path = f"reports/editorial/{report['match_date']}.md"
    markdown_text = _render_markdown_report(report)
    evidence = _evidence_payload(report)
    compiled = compile_editorial_markdown(
        evidence,
        markdown_text,
        source_markdown_path=source_markdown_path,
    )

    (reports_path / f"{report['match_date']}.md").write_text(markdown_text, encoding="utf-8")
    (dated_path / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_compiled_editorial_artifacts(compiled, site_dir=site_path)


def render_editorial_markdown_file(
    *,
    match_date: str,
    site_dir: str | Path = "site",
    reports_dir: str | Path = "reports",
) -> dict[str, Any]:
    site_path = Path(site_dir)
    report_path = Path(reports_dir) / "editorial" / f"{match_date}.md"
    evidence_path = site_path / "editorial" / match_date / "evidence.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Missing editorial Markdown: {report_path}")
    if not evidence_path.exists():
        raise FileNotFoundError(f"Missing editorial evidence: {evidence_path}")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    markdown_text = report_path.read_text(encoding="utf-8")
    compiled = compile_editorial_markdown(
        evidence,
        markdown_text,
        source_markdown_path=f"reports/editorial/{match_date}.md",
    )
    write_compiled_editorial_artifacts(compiled, site_dir=site_path)
    return compiled


def write_compiled_editorial_artifacts(
    compiled: dict[str, Any],
    site_dir: str | Path = "site",
) -> None:
    site_path = Path(site_dir)
    editorial_path = site_path / "editorial"
    dated_path = editorial_path / compiled["match_date"]
    dated_path.mkdir(parents=True, exist_ok=True)
    editorial_path.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(compiled, ensure_ascii=False, indent=2) + "\n"
    (editorial_path / "latest.json").write_text(json_text, encoding="utf-8")
    (dated_path / "choices.json").write_text(json_text, encoding="utf-8")
    (dated_path / "index.html").write_text(_render_editorial_page(compiled), encoding="utf-8")
    (editorial_path / "index.html").write_text(_render_editorial_index(compiled), encoding="utf-8")


def compile_editorial_markdown(
    evidence: dict[str, Any],
    markdown_text: str,
    *,
    source_markdown_path: str,
) -> dict[str, Any]:
    choice_sections = _parse_choice_sections(markdown_text)
    evidence_choices = evidence.get("choices", [])
    if len(choice_sections) != len(evidence_choices):
        raise ValueError(
            "Markdown choice count does not match evidence: "
            f"{len(choice_sections)} markdown sections vs {len(evidence_choices)} evidence choices"
        )

    compiled_choices = []
    for choice, section in zip(evidence_choices, choice_sections, strict=True):
        compiled_choice = dict(choice)
        compiled_choice.pop("narrative", None)
        compiled_choice["content"] = {
            "en": _compile_language_content(section["en"]),
            "zh": _compile_language_content(section["zh"]),
        }
        compiled_choices.append(compiled_choice)

    return {
        "schema_version": 2,
        "generated_at": evidence["generated_at"],
        "compiled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": evidence["match_date"],
        "scoring_version": evidence["scoring_version"],
        "source_markdown_path": source_markdown_path,
        "matches": evidence["matches"],
        "choices": compiled_choices,
        "audit": evidence["audit"],
    }


def _load_scoring_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("version") != "v0.1":
        raise ValueError(f"Unsupported scoring config version: {config.get('version')}")
    return config


def _latest_match_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("select max(match_date) from matches").fetchone()
    if row is None or row[0] is None:
        raise ValueError("No matches available for editorial generation")
    return str(row[0])


def _matches_for_date(conn: sqlite3.Connection, match_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select match_key, match_no, match_date, kickoff_time, stadium,
               home_team, away_team, home_score, away_score
        from matches
        where match_date = ?
        order by match_no
        """,
        (match_date,),
    ).fetchall()
    return [_row_dict(row) for row in rows]


def _player_rows_for_date(conn: sqlite3.Connection, match_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        with shot_totals as (
          select match_key, team, upper(player_name) as player_name,
                 count(*) as shots,
                 sum(is_on_target) as on_target,
                 sum(is_goal) as goals
          from shots
          group by match_key, team, upper(player_name)
        )
        select
          m.match_key,
          m.match_no,
          m.match_date,
          m.home_team,
          m.away_team,
          case when a.team = m.home_team then m.away_team else m.home_team end as opponent,
          a.team,
          a.player_no,
          a.player_name,
          a.position,
          coalesce(s.shots, d.attempts_at_goal, 0) as shots,
          coalesce(s.on_target, 0) as on_target,
          coalesce(s.goals, d.goals, 0) as goals,
          coalesce(o.total_offers, 0) as total_offers,
          coalesce(o.offers_received, 0) as offers_received,
          coalesce(o.in_behind, 0) as in_behind,
          coalesce(o.in_between, 0) as in_between,
          coalesce(d.passes_completed, 0) as passes_completed,
          coalesce(d.line_breaks_completed, 0) as line_breaks_completed,
          coalesce(d.ball_progressions, 0) as ball_progressions,
          coalesce(d.take_ons, 0) as take_ons,
          coalesce(d.step_ins, 0) as step_ins,
          coalesce(x.tackles_won, 0) as tackles_won,
          coalesce(x.interceptions, 0) as interceptions,
          coalesce(x.blocks, 0) as blocks,
          coalesce(x.possession_regains, 0) as possession_regains,
          coalesce(x.possession_interrupted, 0) as possession_interrupted,
          coalesce(x.pressing_direct, 0) as pressing_direct,
          coalesce(x.pressing_indirect, 0) as pressing_indirect,
          coalesce(x.clearances, 0) as clearances,
          coalesce(p.top_speed_kmh, 0) as top_speed_kmh,
          coalesce(p.total_distance_m, 0) as total_distance_m
        from player_appearances a
        join matches m using(match_key)
        left join player_in_possession_distributions d
          on d.match_key = a.match_key
         and d.team = a.team
         and d.player_no = a.player_no
        left join player_offers_receptions o
          on o.match_key = a.match_key
         and o.team = a.team
         and o.player_no = a.player_no
        left join player_defensive_actions x
          on x.match_key = a.match_key
         and x.team = a.team
         and x.player_no = a.player_no
        left join player_physical_stats p
          on p.match_key = a.match_key
         and p.team = a.team
         and p.player_no = a.player_no
        left join shot_totals s
          on s.match_key = a.match_key
         and s.team = a.team
         and s.player_name = upper(a.player_name)
        where m.match_date = ?
        """,
        (match_date,),
    ).fetchall()


def _score_player(row: sqlite3.Row, scoring: dict[str, Any]) -> dict[str, Any]:
    features = _row_dict(row)
    role_scores: dict[str, float] = {}
    component_map: dict[str, list[dict[str, Any]]] = {}
    for score_name, weights in scoring["scores"].items():
        components = []
        total = 0.0
        for metric, weight in weights.items():
            value = float(features.get(metric) or 0)
            contribution = value * float(weight)
            if contribution:
                components.append(
                    {
                        "metric": metric,
                        "value": _clean_number(value),
                        "weight": weight,
                        "contribution": round(contribution, 2),
                    }
                )
            total += contribution
        role_scores[score_name] = round(total, 2)
        component_map[score_name] = sorted(
            components,
            key=lambda item: item["contribution"],
            reverse=True,
        )
    composite = 0.0
    for score_name, weight in scoring["composite_weights"].items():
        composite += role_scores.get(score_name, 0) * float(weight)
    features["role_scores"] = role_scores
    features["score_components"] = component_map
    features["composite_score"] = round(composite, 2)
    return features


def _select_choices(players: list[dict[str, Any]], scoring: dict[str, Any]) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    used_keys: set[tuple[str, str, int]] = set()

    players_of_day = sorted(players, key=lambda row: row["composite_score"], reverse=True)[
        : int(scoring["selection"]["players_of_the_day"])
    ]
    for rank, player in enumerate(players_of_day, start=1):
        choices.append(_choice("player_of_the_day", player, rank, primary_score="composite_score"))
        used_keys.add(_player_key(player))

    for award_type, score_name in [
        ("progression_pick", "progressor"),
        ("defensive_pick", "defensive"),
    ]:
        player = _top_unused_role_player(players, used_keys, score_name)
        if player is None:
            continue
        choices.append(_choice(award_type, player, 1, primary_score=score_name))
        used_keys.add(_player_key(player))

    hidden_min = float(scoring["selection"]["minimum_hidden_gem_role_score"])
    hidden_candidates = [
        player
        for player in players
        if _player_key(player) not in used_keys
        and int(player.get("goals") or 0) == 0
        and max(
            player["role_scores"]["progressor"],
            player["role_scores"]["off_ball"],
            player["role_scores"]["defensive"],
        )
        >= hidden_min
    ]
    hidden_candidates.sort(
        key=lambda row: max(
            row["role_scores"]["progressor"],
            row["role_scores"]["off_ball"],
            row["role_scores"]["defensive"],
        ),
        reverse=True,
    )
    for rank, player in enumerate(
        hidden_candidates[: int(scoring["selection"]["hidden_gems"])],
        start=1,
    ):
        choices.append(_choice("hidden_gem", player, rank, primary_score=_best_role_score(player)))
        used_keys.add(_player_key(player))

    return choices


def _choice(
    award_type: str,
    player: dict[str, Any],
    rank: int,
    primary_score: str,
) -> dict[str, Any]:
    if primary_score == "composite_score":
        score = player["composite_score"]
        components = _top_components_across_roles(player)
    else:
        score = player["role_scores"][primary_score]
        components = player["score_components"].get(primary_score, [])
    return {
        "award_type": award_type,
        "award_label": AWARD_LABELS[award_type],
        "rank": rank,
        "match_key": player["match_key"],
        "match_no": player["match_no"],
        "player_no": player["player_no"],
        "player_name": player["player_name"],
        "team": player["team"],
        "opponent": player["opponent"],
        "position": player["position"],
        "score": round(float(score), 1),
        "primary_score": primary_score,
        "role_scores": player["role_scores"],
        "score_components": components[:6],
        "evidence_chips": _evidence_chips(player, award_type),
        "draft": _draft_brief(player, award_type),
    }


def _top_unused_role_player(
    players: list[dict[str, Any]],
    used_keys: set[tuple[str, str, int]],
    score_name: str,
) -> dict[str, Any] | None:
    candidates = [
        player
        for player in players
        if _player_key(player) not in used_keys and player["role_scores"].get(score_name, 0) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row["role_scores"][score_name])


def _best_role_score(player: dict[str, Any]) -> str:
    return max(
        ["progressor", "off_ball", "defensive"],
        key=lambda score_name: player["role_scores"][score_name],
    )


def _top_components_across_roles(player: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for score_name, items in player["score_components"].items():
        for item in items:
            components.append({**item, "score": score_name})
    return sorted(components, key=lambda item: item["contribution"], reverse=True)


def _evidence_chips(player: dict[str, Any], award_type: str) -> dict[str, list[str]]:
    en: list[str] = []
    zh: list[str] = []
    goals = int(player.get("goals") or 0)
    if goals >= 3:
        en.append("hat-trick")
        zh.append("帽子戏法")
    elif goals == 2:
        en.append("brace")
        zh.append("梅开二度")
    elif goals == 1:
        en.append("goal scorer")
        zh.append("取得进球")

    _append_if(en, zh, player, "on_target", 3, "high shot quality", "射门质量突出")
    _append_if(en, zh, player, "line_breaks_completed", 15, "repeated line breaks", "持续打穿防线")
    _append_if(en, zh, player, "ball_progressions", 10, "constant carries", "推进很活跃")
    _append_if(en, zh, player, "offers_received", 25, "found again and again", "持续接应")
    _append_if(en, zh, player, "in_between", 15, "between-line presence", "在防线之间活跃")
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


def _draft_brief(player: dict[str, Any], award_type: str) -> dict[str, dict[str, str]]:
    return {
        "en": _english_draft_brief(player, award_type),
        "zh": _chinese_draft_brief(player, award_type),
    }


def _english_draft_brief(player: dict[str, Any], award_type: str) -> dict[str, str]:
    name = player["player_name"]
    team = player["team"]
    opponent = player["opponent"]
    title = f"Draft brief - {AWARD_LABELS[award_type]['en']}"
    body = (
        "Use this as evidence, then rewrite the English and Chinese copy separately. "
        f"{name} ({team} vs {opponent}) was selected for {AWARD_LABELS[award_type]['en']}. "
        f"Main evidence: {_english_metric_summary(player)}."
    )
    return {"title": title, "body": body}


def _chinese_draft_brief(player: dict[str, Any], award_type: str) -> dict[str, str]:
    name = _zh_player_name(player["player_name"])
    team = _zh_team_name(player["team"])
    opponent = _zh_team_name(player["opponent"])
    title = f"中文编辑草稿 - {AWARD_LABELS[award_type]['zh']}"
    body = (
        "这段只作为证据 brief，不是可发布文案。中英文应分别从同一份 evidence 改写，"
        f"不要互相翻译。{name}（{team}对{opponent}）入选{AWARD_LABELS[award_type]['zh']}。"
        f"主要依据：{_chinese_metric_summary(player)}。"
    )
    return {"title": title, "body": body}


def _english_metric_summary(player: dict[str, Any]) -> str:
    metrics = _metric_summary_items(player)
    return ", ".join(f"{item['label_en']} {item['value']}" for item in metrics)


def _chinese_metric_summary(player: dict[str, Any]) -> str:
    metrics = _metric_summary_items(player)
    return "，".join(f"{item['label_zh']}{item['value']}" for item in metrics)


def _metric_summary_items(player: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "goals": ("goals", "进球"),
        "attempts": ("attempts", "射门"),
        "on_target": ("on target", "射正"),
        "line_breaks_completed": ("line breaks", "打穿防线"),
        "ball_progressions": ("ball progressions", "推进"),
        "offers_received": ("offers received", "接应成功"),
        "in_between": ("between-line offers", "两线间接应"),
        "in_behind": ("in-behind offers", "身后接应"),
        "possession_regains": ("possession regains", "夺回球权"),
        "possession_interrupted": ("interruptions", "破坏进攻"),
        "blocks": ("blocks", "封堵"),
        "total_distance_m": ("distance metres", "跑动米数"),
        "top_speed_kmh": ("top speed km/h", "最高速度km/h"),
    }
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for component in player.get("score_components", {}).get("composite_score", []):
        metric = str(component.get("metric"))
        if metric in seen or metric not in labels:
            continue
        seen.add(metric)
        en, zh = labels[metric]
        items.append(
            {
                "label_en": en,
                "label_zh": zh,
                "value": str(_clean_number(float(component.get("value") or 0))),
            }
        )
        if len(items) >= 4:
            return items
    for metric, (en, zh) in labels.items():
        if metric in seen:
            continue
        value = float(player.get(metric) or 0)
        if value <= 0:
            continue
        items.append(
            {
                "label_en": en,
                "label_zh": zh,
                "value": str(_clean_number(value)),
            }
        )
        if len(items) >= 4:
            break
    return items


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


def _zh_team_name(team: str) -> str:
    return ZH_TEAM_NAMES.get(team, team)


def _zh_player_name(player_name: str) -> str:
    return ZH_PLAYER_NAMES.get(player_name, player_name)


def _build_audit(
    players: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    match_date: str,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if not choices:
        alerts.append(
            {
                "level": "warning",
                "code": "no_choices",
                "message": f"No editorial choices generated for {match_date}.",
            }
        )
    if players and choices:
        top_score = choices[0]["score"]
        if top_score <= 0:
            alerts.append(
                {
                    "level": "warning",
                    "code": "non_positive_top_score",
                    "message": "Top editorial score was not positive.",
                }
            )
    if not any(choice["award_type"] == "hidden_gem" for choice in choices):
        alerts.append(
            {
                "level": "info",
                "code": "no_hidden_gem",
                "message": "No hidden gem passed the current threshold.",
            }
        )
    return alerts


def _evidence_payload(report: dict[str, Any]) -> dict[str, Any]:
    evidence = json.loads(json.dumps(report, ensure_ascii=False))
    for choice in evidence["choices"]:
        choice.pop("narrative", None)
        choice.pop("draft", None)
    return evidence


def _parse_choice_sections(markdown_text: str) -> list[dict[str, list[str]]]:
    sections: list[dict[str, list[str]]] = []
    current: list[str] | None = None
    for line in markdown_text.splitlines():
        if line.startswith("### "):
            if current is not None:
                sections.append(_parse_choice_block(current))
            current = []
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        sections.append(_parse_choice_block(current))
    return sections


def _parse_choice_block(lines: list[str]) -> dict[str, list[str]]:
    en: list[str] = []
    zh: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if line == "#### English":
            current = en
            continue
        if line == "#### 中文":
            current = zh
            continue
        if line.startswith("Evidence:") or line.startswith("依据："):
            current = None
            continue
        if current is not None:
            current.append(line)
    if not en or not zh:
        raise ValueError("Each editorial choice must include English and 中文 sections")
    return {"en": en, "zh": zh}


def _compile_language_content(lines: list[str]) -> dict[str, str]:
    content_lines = _trim_blank_lines(lines)
    if not content_lines:
        raise ValueError("Editorial language section is empty")
    title = _extract_markdown_title(content_lines[0])
    body_lines = content_lines[1:] if title else content_lines
    if not title:
        title = content_lines[0]
    return {
        "title": title,
        "html": _markdown_blocks_to_html(body_lines),
    }


def _extract_markdown_title(line: str) -> str:
    match = re.fullmatch(r"\*\*(.+)\*\*", line.strip())
    return match.group(1).strip() if match else ""


def _markdown_blocks_to_html(lines: list[str]) -> str:
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
            continue
        if current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return "".join(f"<p>{_render_inline_markdown(block)}</p>" for block in blocks)


def _render_inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _render_editorial_page(report: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Editor's Choices - {html.escape(report["match_date"], quote=False)}</title>
  <style>{_editorial_css()}</style>
</head>
<body>
  <main>
    <p class="eyebrow">FIFA PMSR Data</p>
    <h1>Editor's Choices · {html.escape(report["match_date"], quote=False)}</h1>
    <p class="lede">Data-informed selections from the latest structured PMSR dataset. These are not official awards.</p>
    {_choices_html(report["choices"])}
  </main>
</body>
</html>
"""


def _render_editorial_index(report: dict[str, Any]) -> str:
    match_date = html.escape(report["match_date"], quote=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Editor's Choices</title>
  <style>{_editorial_css()}</style>
</head>
<body>
  <main>
    <p class="eyebrow">FIFA PMSR Data</p>
    <h1>Editor's Choices</h1>
    <p class="lede">Latest available match-day editorial picks: <a href="{match_date}/">{match_date}</a>.</p>
    {_choices_html(report["choices"])}
  </main>
</body>
</html>
"""


def _choices_html(choices: list[dict[str, Any]]) -> str:
    cards = []
    for choice in choices:
        en = choice["content"]["en"]
        zh = choice["content"]["zh"]
        chips = "".join(
            f"<span>{html.escape(chip, quote=False)}</span>"
            for chip in choice["evidence_chips"]["en"]
        )
        cards.append(
            f"""
    <article class="choice-card">
      <div>
        <p class="award">{html.escape(choice["award_label"]["en"], quote=False)}</p>
        <h2>{html.escape(choice["player_name"], quote=False)}</h2>
        <p class="meta">{html.escape(choice["team"], quote=False)} vs {html.escape(choice["opponent"], quote=False)} · Match {choice["match_no"]}</p>
        <h3>{html.escape(en["title"], quote=False)}</h3>
        {en["html"]}
        <h3>{html.escape(zh["title"], quote=False)}</h3>
        {zh["html"]}
      </div>
      <aside>
        <strong>{choice["score"]:.1f}</strong>
        <span>score</span>
        <div class="chips">{chips}</div>
      </aside>
    </article>
            """
        )
    return "\n".join(cards) if cards else "<p>No editorial choices generated.</p>"


def _render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Editor's Choices - {report['match_date']}",
        "",
        f"Scoring version: `{report['scoring_version']}`",
        "",
        "Data-informed selections from the structured PMSR dataset. These are not official FIFA awards.",
        "",
        "## Matches Covered",
        "",
    ]
    for match in report["matches"]:
        lines.append(
            f"- Match {match['match_no']}: {match['home_team']} {match['home_score']}-"
            f"{match['away_score']} {match['away_team']}"
        )
    lines.extend(["", "## Choices", ""])
    for choice in report["choices"]:
        lines.extend(
            [
                f"### {choice['award_label']['en']}: {choice['player_name']}",
                "",
                f"_{choice['team']} vs {choice['opponent']} · Match {choice['match_no']}_",
                "",
                "#### English",
                "",
                f"**{choice['draft']['en']['title']}**",
                "",
                choice["draft"]["en"]["body"],
                "",
                "#### 中文",
                "",
                f"**{choice['draft']['zh']['title']}**",
                "",
                choice["draft"]["zh"]["body"],
                "",
                "Evidence: " + ", ".join(choice["evidence_chips"]["en"]),
                "",
                "依据：" + "，".join(choice["evidence_chips"]["zh"]),
                "",
            ]
        )
    if report["audit"]:
        lines.extend(["## Audit", ""])
        lines.extend(f"- `{item['code']}`: {item['message']}" for item in report["audit"])
        lines.append("")
    return "\n".join(lines)


def _editorial_css() -> str:
    return """
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f5f7fb; }
    body { margin: 0; }
    main { max-width: 980px; margin: 0 auto; padding: 36px 20px 56px; }
    h1 { margin: 0 0 8px; font-size: 32px; }
    h2 { margin: 0 0 4px; font-size: 24px; }
    h3 { margin: 18px 0 6px; font-size: 16px; }
    p { line-height: 1.55; color: #435268; }
    .eyebrow, .award { color: #59677c; font-size: 12px; letter-spacing: 0; text-transform: uppercase; font-weight: 700; }
    .lede { margin-bottom: 24px; }
    .choice-card { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 18px; background: #fff; border: 1px solid #dde3ee; border-radius: 8px; padding: 22px; margin: 18px 0; }
    .choice-card aside { border-left: 1px solid #e8edf5; padding-left: 18px; }
    .choice-card aside strong { display: block; font-size: 34px; }
    .choice-card aside > span { color: #59677c; font-size: 12px; text-transform: uppercase; }
    .meta { margin: 0; color: #59677c; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
    .chips span { background: #edf2fa; border: 1px solid #dce5f2; border-radius: 999px; padding: 5px 9px; font-size: 12px; }
    @media (max-width: 720px) { .choice-card { grid-template-columns: 1fr; } .choice-card aside { border-left: 0; border-top: 1px solid #e8edf5; padding-left: 0; padding-top: 14px; } }
    """


def _player_key(player: dict[str, Any]) -> tuple[str, str, int]:
    return str(player["match_key"]), str(player["team"]), int(player["player_no"])


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _clean_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return round(value, 2)
