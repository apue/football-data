from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football_data.editorial_fingerprint import editorial_input_fingerprint
from football_data.flags import format_player, format_team
from football_data.match_flow import build_match_flows, player_flow_impacts
from football_data.metric_benchmarks import hidden_gem_profile, progression_benchmark


DEFAULT_SCORING_CONFIG = Path("config/scoring/v0.4.json")


AWARD_LABELS = {
    "player_of_the_day": {"en": "Player of the Day", "zh": "每日最佳球员"},
    "impact_pick": {"en": "Impact Pick", "zh": "影响力精选"},
    "progression_pick": {"en": "Progression Engine", "zh": "进攻发动机"},
    "defensive_pick": {"en": "Defensive Pick", "zh": "防守精选"},
    "goalkeeper_watch": {"en": "Goalkeeper Watch", "zh": "门将关注"},
    "hidden_gem": {"en": "Hidden Gem", "zh": "隐藏亮点"},
}


AWARD_DISPLAY_ORDER = [
    "player_of_the_day",
    "impact_pick",
    "progression_pick",
    "defensive_pick",
    "goalkeeper_watch",
    "hidden_gem",
]


AWARD_DISPLAY_PRIORITY = {
    award_type: index
    for index, award_type in enumerate(AWARD_DISPLAY_ORDER)
}


ZH_TEAM_NAMES = {
    "Algeria": "阿尔及利亚",
    "Argentina": "阿根廷",
    "Australia": "澳大利亚",
    "Austria": "奥地利",
    "Belgium": "比利时",
    "Bosnia and Herzegovina": "波黑",
    "Brazil": "巴西",
    "Cabo Verde": "佛得角",
    "Canada": "加拿大",
    "Colombia": "哥伦比亚",
    "Congo DR": "刚果（金）",
    "Croatia": "克罗地亚",
    "Curaçao": "库拉索",
    "Czechia": "捷克",
    "Côte d'Ivoire": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Egypt": "埃及",
    "England": "英格兰",
    "France": "法国",
    "Germany": "德国",
    "Ghana": "加纳",
    "Haiti": "海地",
    "IR Iran": "伊朗",
    "Iraq": "伊拉克",
    "Japan": "日本",
    "Jordan": "约旦",
    "Korea Republic": "韩国",
    "Mexico": "墨西哥",
    "Morocco": "摩洛哥",
    "Netherlands": "荷兰",
    "New Zealand": "新西兰",
    "Norway": "挪威",
    "Panama": "巴拿马",
    "Paraguay": "巴拉圭",
    "Portugal": "葡萄牙",
    "Qatar": "卡塔尔",
    "Saudi Arabia": "沙特阿拉伯",
    "Scotland": "苏格兰",
    "Senegal": "塞内加尔",
    "South Africa": "南非",
    "Spain": "西班牙",
    "Sweden": "瑞典",
    "Switzerland": "瑞士",
    "Tunisia": "突尼斯",
    "Türkiye": "土耳其",
    "Uruguay": "乌拉圭",
    "USA": "美国",
    "Uzbekistan": "乌兹别克斯坦",
}


ZH_PLAYER_NAMES = {
    "ABDALLAH NASIB": "纳西布",
    "Alireza BEIRANVAND": "贝兰万德",
    "Andres ANDRADE": "安德烈斯·安德拉德",
    "Ayase UEDA": "上田绮世",
    "Brian BROBBEY": "布罗比",
    "BRUNO FERNANDES": "布鲁诺·费尔南德斯",
    "Deniz UNDAV": "恩达夫",
    "Felix NMECHA": "恩梅查",
    "JOAO NEVES": "若昂·内维斯",
    "Jonas ADJETEY": "乔纳斯·阿杰泰",
    "Joshua KIMMICH": "基米希",
    "Kylian MBAPPE": "姆巴佩",
    "Lionel MESSI": "梅西",
    "Erling HAALAND": "哈兰德",
    "Amine GOUIRI": "古伊里",
    "Ibrahim MAZA": "马扎",
    "MOHANNAD ABUTAHA": "阿布塔哈",
    "Sadio MANE": "马内",
    "Nadhir BENBOUALI": "本布阿里",
    "MARAWAN ATTIA": "阿蒂亚",
    "Maxi ARAUJO": "马克西·阿劳霍",
    "Mikel OYARZABAL": "奥亚萨瓦尔",
    "MOHAMED SALAH": "萨拉赫",
    "Nicolas SEIWALD": "塞瓦尔德",
    "PICO LOPES": "皮科·洛佩斯",
    "Pedro VITE": "维特",
    "Rayan AIT-NOURI": "艾特-努里",
    "Rodrigo DE PAUL": "德保罗",
    "TOMAS ARAUJO": "托马斯·阿劳若",
    "VITINHA": "维蒂尼亚",
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
        match_flows = build_match_flows(db_path, match_date=selected_date)
        flow_impacts = player_flow_impacts(match_flows)
        players = [
            _score_player(row, scoring, flow_impacts=flow_impacts)
            for row in _player_rows_for_date(conn, selected_date)
        ]
        _attach_flow_contexts(players, match_flows)
    finally:
        conn.close()

    selection_result = _select_choices_with_review(players, scoring)
    choices = selection_result["choices"]
    input_fingerprint = editorial_input_fingerprint(
        db_path,
        selected_date,
        scoring_config_path,
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": selected_date,
        "scoring_version": scoring["version"],
        "editorial_input_hash": input_fingerprint["input_hash"],
        "editorial_input": input_fingerprint,
        "matches": matches,
        "match_flows": match_flows,
        "choices": choices,
        "selection_review": selection_result["review"],
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
    markdown_path = reports_path / f"{report['match_date']}.md"
    markdown_text = _render_markdown_report(report)
    evidence = _evidence_payload(report)
    compiled = compile_editorial_markdown(
        evidence,
        markdown_text,
        source_markdown_path=source_markdown_path,
    )

    markdown_path.write_text(markdown_text, encoding="utf-8")
    (dated_path / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (dated_path / "fact_bank.zh.json").write_text(
        json.dumps(_zh_fact_bank_payload(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (dated_path / "brief.en.json").write_text(
        json.dumps(_english_brief_payload(report), ensure_ascii=False, indent=2) + "\n",
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
    (dated_path / "choices.json").write_text(json_text, encoding="utf-8")
    (dated_path / "index.html").write_text(_render_editorial_page(compiled), encoding="utf-8")
    latest = _latest_editorial_report(editorial_path, compiled)
    (editorial_path / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive_items = _editorial_archive_items(editorial_path, compiled)
    (editorial_path / "index.html").write_text(
        _render_editorial_index(archive_items),
        encoding="utf-8",
    )


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
        for internal_key in ("score", "primary_score", "role_scores", "score_components"):
            compiled_choice.pop(internal_key, None)
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
        "editorial_generation": _editorial_generation(evidence),
        "editorial_input_hash": evidence.get("editorial_input_hash"),
        "editorial_input": evidence.get("editorial_input"),
        "source_markdown_path": source_markdown_path,
        "matches": evidence["matches"],
        "match_flows": evidence.get("match_flows", {}),
        "choices": compiled_choices,
        "selection_review": evidence.get("selection_review"),
        "audit": evidence["audit"],
    }


def _editorial_generation(evidence: dict[str, Any]) -> dict[str, Any]:
    editorial_input = evidence.get("editorial_input")
    uses_goal_involvements = (
        isinstance(editorial_input, dict)
        and "goal_involvements" in editorial_input
    )
    return {
        "scoring_version": evidence.get("scoring_version"),
        "uses_official_assists": uses_goal_involvements,
        "uses_goal_involvements": uses_goal_involvements,
        "event_source": "fifa_timeline_api" if uses_goal_involvements else None,
    }


def _latest_editorial_report(editorial_path: Path, current: dict[str, Any]) -> dict[str, Any]:
    reports = [current]
    latest = _load_json(editorial_path / "latest.json")
    if latest:
        reports.append(latest)
    for choices_path in editorial_path.glob("*/choices.json"):
        report = _load_json(choices_path)
        if report:
            reports.append(report)
    return max(reports, key=lambda report: str(report.get("match_date") or ""))


def _editorial_archive_items(
    editorial_path: Path,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for choices_path in editorial_path.glob("*/choices.json"):
        report = _load_json(choices_path)
        match_date = str(report.get("match_date") or "")
        if match_date:
            by_date[match_date] = _archive_item(report)
    by_date[str(current["match_date"])] = _archive_item(current)
    return [by_date[match_date] for match_date in sorted(by_date, reverse=True)]


def _archive_item(report: dict[str, Any]) -> dict[str, Any]:
    generation = report.get("editorial_generation")
    if not isinstance(generation, dict):
        generation = {}
    matches = report.get("matches")
    return {
        "match_date": str(report.get("match_date") or ""),
        "match_count": len(matches) if isinstance(matches, list) else 0,
        "generated_at": report.get("generated_at"),
        "compiled_at": report.get("compiled_at"),
        "scoring_version": report.get("scoring_version"),
        "uses_official_assists": bool(generation.get("uses_official_assists")),
        "uses_goal_involvements": bool(generation.get("uses_goal_involvements")),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scoring_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("version") not in {"v0.3", "v0.4"}:
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
                 sum(case when outcome like '% - Goal' then 1 else 0 end) as goals
          from shots
          group by match_key, team, upper(player_name)
        ),
        assist_totals as (
          select match_key,
                 team_name as team,
                 upper(assister_name) as player_name,
                 count(*) as assists
          from goal_involvements
          where assister_name is not null
          group by match_key, team_name, upper(assister_name)
        ),
        goal_rows as (
          select
            s.match_key,
            s.team,
            upper(s.player_name) as player_name,
            s.minute,
            s.shot_no,
            m.home_team,
            m.away_team,
            m.home_score,
            m.away_score,
            case when s.team = m.home_team then m.away_team else m.home_team end as opponent,
            case when s.team = m.home_team then m.home_score else m.away_score end as team_final_goals,
            case when s.team = m.home_team then m.away_score else m.home_score end as opponent_final_goals,
            row_number() over (
              partition by s.match_key
              order by s.minute, case when s.team = m.home_team then 0 else 1 end, s.shot_no
            ) as goal_order
          from shots s
          join matches m using(match_key)
          where s.outcome like '% - Goal'
        ),
        goal_states as (
          select
            g.match_key,
            g.team,
            g.player_name,
            g.minute,
            g.team_final_goals,
            g.opponent_final_goals,
            coalesce(sum(case when prev.team = g.team then 1 else 0 end), 0) as team_goals_before,
            coalesce(sum(case when prev.team = g.opponent then 1 else 0 end), 0) as opponent_goals_before
          from goal_rows g
          left join goal_rows prev
            on prev.match_key = g.match_key
           and prev.goal_order < g.goal_order
          group by
            g.match_key,
            g.team,
            g.player_name,
            g.opponent,
            g.minute,
            g.goal_order,
            g.team_final_goals,
            g.opponent_final_goals
        ),
        goal_impacts as (
          select
            match_key,
            team,
            player_name,
            sum(case when team_goals_before = 0 and opponent_goals_before = 0 then 1 else 0 end) as opening_goal,
            sum(case when team_goals_before < opponent_goals_before and team_goals_before + 1 = opponent_goals_before then 1 else 0 end) as equalizing_goal,
            sum(case when team_goals_before <= opponent_goals_before and team_goals_before + 1 > opponent_goals_before then 1 else 0 end) as go_ahead_goal,
            sum(
              case
                when team_final_goals > opponent_final_goals
                 and team_goals_before + 1 = opponent_final_goals + 1
                 and (
                   team_final_goals - opponent_final_goals = 1
                   or team_goals_before < opponent_goals_before
                 )
                then 1 else 0
              end
            ) as match_winning_goal,
            sum(case when minute >= 75 then 1 else 0 end) as late_goal,
            sum(case when minute >= 90 then 1 else 0 end) as stoppage_time_goal,
            sum(
              case
                when minute >= 85
                 and team_final_goals > opponent_final_goals
                 and team_goals_before + 1 = opponent_final_goals + 1
                 and (
                   team_final_goals - opponent_final_goals = 1
                   or team_goals_before < opponent_goals_before
                 )
                then 1 else 0
              end
            ) as late_match_winning_goal
          from goal_states
          group by match_key, team, player_name
        ),
        saved_shot_totals as (
          select
            match_key,
            team as shooting_team,
            count(*) as saved_shots
          from shots
          where outcome like '%Saved%'
          group by match_key, team
        )
        select
          m.match_key,
          m.match_no,
          m.match_date,
          m.home_team,
          m.away_team,
          m.home_score,
          m.away_score,
          case when a.team = m.home_team then m.away_team else m.home_team end as opponent,
          case when a.team = m.home_team then m.home_score else m.away_score end as team_final_goals,
          case when a.team = m.home_team then m.away_score else m.home_score end as opponent_final_goals,
          coalesce(ts.xg, 0) as team_xg,
          coalesce(ts.attempts_total, 0) as team_attempts_total,
          coalesce(ts.attempts_on_target, 0) as team_attempts_on_target,
          coalesce(ots.xg, 0) as opponent_xg,
          coalesce(ots.attempts_total, 0) as opponent_attempts_total,
          coalesce(ots.attempts_on_target, 0) as opponent_attempts_on_target,
          case when (case when a.team = m.home_team then m.away_score else m.home_score end) = 0 then 1 else 0 end as clean_sheet,
          coalesce(kss.saved_shots, 0) as keeper_saved_shots,
          a.team,
          a.player_no,
          a.player_name,
          a.position,
          a.roster_status,
          a.started,
          coalesce(s.shots, d.attempts_at_goal, 0) as shots,
          coalesce(s.on_target, 0) as on_target,
          coalesce(s.goals, d.goals, 0) as goals,
          coalesce(ast.assists, 0) as assists,
          coalesce(s.goals, d.goals, 0) + coalesce(ast.assists, 0) as goal_involvements,
          case when coalesce(s.goals, d.goals, 0) >= 2 then 1 else 0 end as brace,
          case when coalesce(s.goals, d.goals, 0) >= 3 then 1 else 0 end as hat_trick,
          case when a.started = 0 then coalesce(s.goals, d.goals, 0) else 0 end as substitute_goal,
          case when a.started = 0 and coalesce(s.goals, d.goals, 0) >= 2 then 1 else 0 end as substitute_brace,
          case
            when coalesce(s.goals, d.goals, 0) > 0
             and (
               (a.team = m.home_team and m.home_score = 1 and m.away_score = 0)
               or (a.team = m.away_team and m.away_score = 1 and m.home_score = 0)
             )
            then 1 else 0
          end as only_goal_winner,
          coalesce(g.opening_goal, 0) as opening_goal,
          coalesce(g.equalizing_goal, 0) as equalizing_goal,
          coalesce(g.go_ahead_goal, 0) as go_ahead_goal,
          coalesce(g.match_winning_goal, 0) as match_winning_goal,
          coalesce(g.late_goal, 0) as late_goal,
          coalesce(g.stoppage_time_goal, 0) as stoppage_time_goal,
          coalesce(g.late_match_winning_goal, 0) as late_match_winning_goal,
          coalesce(o.total_offers, 0) as total_offers,
          coalesce(o.offers_received, 0) as offers_received,
          coalesce(o.in_behind, 0) as in_behind,
          coalesce(o.in_between, 0) as in_between,
          coalesce(d.passes_completed, 0) as passes_completed,
          coalesce(d.line_breaks_completed, 0) as line_breaks_completed,
          coalesce(lb.units_4_attacking_line, 0) as units_4_attacking_line,
          coalesce(lb.units_4_attacking_midfield_line, 0) as units_4_attacking_midfield_line,
          coalesce(lb.units_4_midfield_line, 0) as units_4_midfield_line,
          coalesce(lb.units_4_defensive_line, 0) as units_4_defensive_line,
          coalesce(lb.units_3_attacking_line, 0) as units_3_attacking_line,
          coalesce(lb.units_3_midfield_line, 0) as units_3_midfield_line,
          coalesce(lb.units_3_defensive_line, 0) as units_3_defensive_line,
          coalesce(lb.units_2_midfield_line, 0) as units_2_midfield_line,
          coalesce(lb.units_2_defensive_line, 0) as units_2_defensive_line,
          coalesce(lb.direction_through, 0) as direction_through,
          coalesce(lb.direction_around, 0) as direction_around,
          coalesce(lb.direction_over, 0) as direction_over,
          coalesce(lb.distribution_pass, 0) as distribution_pass,
          coalesce(lb.distribution_cross, 0) as distribution_cross,
          coalesce(lb.distribution_ball_progression, 0) as distribution_ball_progression,
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
        left join player_line_breaks lb
          on lb.match_key = a.match_key
         and lb.team = a.team
         and lb.player_no = a.player_no
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
        left join assist_totals ast
          on ast.match_key = a.match_key
         and ast.team = a.team
         and ast.player_name = upper(a.player_name)
        left join goal_impacts g
          on g.match_key = a.match_key
         and g.team = a.team
         and g.player_name = upper(a.player_name)
        left join team_match_stats ts
          on ts.match_key = a.match_key
         and ts.team = a.team
        left join team_match_stats ots
          on ots.match_key = a.match_key
         and ots.team = case when a.team = m.home_team then m.away_team else m.home_team end
        left join saved_shot_totals kss
          on kss.match_key = a.match_key
         and kss.shooting_team = case when a.team = m.home_team then m.away_team else m.home_team end
        where m.match_date = ?
        """,
        (match_date,),
    ).fetchall()


def _score_player(
    row: sqlite3.Row,
    scoring: dict[str, Any],
    *,
    flow_impacts: dict[tuple[str, str, str], dict[str, int]] | None = None,
) -> dict[str, Any]:
    features = _row_dict(row)
    if flow_impacts:
        key = (
            str(features["match_key"]),
            str(features["team"]),
            str(features["player_name"]).upper(),
        )
        features.update(flow_impacts.get(key, {}))
    role_scores: dict[str, float] = {}
    component_map: dict[str, list[dict[str, Any]]] = {}
    for score_name, weights in scoring["scores"].items():
        if score_name == "goalkeeper" and not _is_starting_goalkeeper(features):
            role_scores[score_name] = 0.0
            component_map[score_name] = []
            continue
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
    headline = composite
    for score_name, weight in scoring.get("headline_weights", {}).items():
        if score_name == "composite_score":
            headline += composite * float(weight)
        else:
            headline += role_scores.get(score_name, 0) * float(weight)
    features["role_scores"] = role_scores
    features["score_components"] = component_map
    features["composite_score"] = round(composite, 2)
    features["headline_score"] = round(headline, 2)
    features["progression_benchmark"] = progression_benchmark(features)
    features["hidden_gem_profile"] = hidden_gem_profile(features)
    return features


def _is_starting_goalkeeper(player: dict[str, Any]) -> bool:
    return str(player.get("position") or "").upper() == "GK" and int(player.get("started") or 0) == 1


def _attach_flow_contexts(
    players: list[dict[str, Any]],
    match_flows: dict[str, dict[str, Any]],
) -> None:
    for player in players:
        player["flow_context"] = _player_flow_context(
            player,
            match_flows.get(str(player["match_key"])),
        )


def _player_flow_context(
    player: dict[str, Any],
    match_flow: dict[str, Any] | None,
) -> dict[str, Any]:
    if not match_flow:
        return {
            "goals": [],
            "allowed_claims": {"en": [], "zh": []},
            "team_came_from_behind_to_win": False,
        }
    player_name = str(player["player_name"]).upper()
    team = str(player["team"])
    goals = [
        goal
        for goal in match_flow.get("goals", [])
        if str(goal.get("team")) == team and str(goal.get("player_name", "")).upper() == player_name
    ]
    en_claims: list[str] = []
    zh_claims: list[str] = []
    team_came_from_behind_to_win = _team_came_from_behind_to_win(match_flow, team)
    if team_came_from_behind_to_win:
        _append_unique(en_claims, "comeback win")
        _append_unique(zh_claims, "逆转取胜")
    for goal in goals:
        tags = {str(tag) for tag in goal.get("tags", [])}
        minute = int(goal.get("minute") or 0)
        if "opening_goal" in tags:
            _append_unique(en_claims, "opening goal")
            _append_unique(zh_claims, "首开纪录")
        if "equalizer" in tags:
            _append_unique(en_claims, "equaliser")
            _append_unique(zh_claims, "扳平")
        if "go_ahead_goal" in tags:
            _append_unique(en_claims, "go-ahead goal")
            _append_unique(zh_claims, "取得领先")
        if "match_winning_goal" in tags:
            _append_unique(en_claims, "match-winning goal")
            _append_unique(zh_claims, "制胜球")
        if "stoppage_time_goal" in tags:
            _append_unique(en_claims, "stoppage-time goal")
            _append_unique(zh_claims, "补时进球")
        if "late_match_winning_goal" in tags:
            _append_unique(en_claims, "late winner")
            _append_unique(zh_claims, "补时制胜")
        if "comeback_winner" in tags:
            _append_unique(en_claims, "comeback winner")
            _append_unique(zh_claims, "逆转制胜")
        if "comeback_equalizer" in tags:
            _append_unique(en_claims, "comeback equaliser")
            _append_unique(zh_claims, "逆转过程中的扳平球")
            _append_unique(zh_claims, "逆转扳平")
        if "stoppage_time_goal" in tags and "match_winning_goal" in tags:
            _append_unique(en_claims, f"{minute}' stoppage-time winner")
            _append_unique(zh_claims, f"{minute}' 补时制胜")
        elif "match_winning_goal" in tags:
            _append_unique(en_claims, f"{minute}' winner")
            _append_unique(zh_claims, f"{minute}' 制胜")
        elif "equalizer" in tags:
            _append_unique(en_claims, f"{minute}' equaliser")
            _append_unique(zh_claims, f"{minute}' 扳平")
    return {
        "match_key": match_flow["match_key"],
        "team_came_from_behind_to_win": team_came_from_behind_to_win,
        "allowed_claims": {"en": en_claims, "zh": zh_claims},
        "goals": goals,
        "decisive_goal": next(
            (goal for goal in goals if "match_winning_goal" in goal.get("tags", [])),
            None,
        ),
    }


def _team_came_from_behind_to_win(match_flow: dict[str, Any], team: str) -> bool:
    if team == match_flow.get("home_team"):
        return bool(match_flow.get("home_came_from_behind_to_win"))
    if team == match_flow.get("away_team"):
        return bool(match_flow.get("away_came_from_behind_to_win"))
    return False


def _select_choices_with_review(
    players: list[dict[str, Any]],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    baseline_choices = _select_choices(players, scoring)
    baseline_review = _review_editorial_selection(players, baseline_choices, scoring)
    iterations = [_selection_review_iteration(1, baseline_choices, baseline_review)]

    final_choices = baseline_choices
    final_review = baseline_review
    if baseline_review["status"] != "publishable":
        adjusted_choices = _select_choices(players, scoring, apply_editorial_guards=True)
        adjusted_review = _review_editorial_selection(players, adjusted_choices, scoring)
        iterations.append(_selection_review_iteration(2, adjusted_choices, adjusted_review))
        final_choices = adjusted_choices
        final_review = adjusted_review

    return {
        "choices": final_choices,
        "review": {
            "status": final_review["status"],
            "alerts": final_review["alerts"],
            "iterations": iterations,
        },
    }


def _select_choices(
    players: list[dict[str, Any]],
    scoring: dict[str, Any],
    *,
    apply_editorial_guards: bool = False,
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str, int], dict[str, Any]] = {}
    headline_keys: set[tuple[str, str, int]] = set()
    headline_teams: set[str] = set()

    players_of_day = sorted(players, key=lambda row: row["headline_score"], reverse=True)[
        : int(scoring["selection"]["players_of_the_day"])
    ]
    player_of_day_keys: set[tuple[str, str, int]] = set()
    for rank, player in enumerate(players_of_day, start=1):
        _add_choice_award(candidates, player, "player_of_the_day", rank, "headline_score")
        player_key = _player_key(player)
        player_of_day_keys.add(player_key)
        headline_keys.add(player_key)
        headline_teams.add(str(player["team"]))

    impact_min = float(scoring["selection"].get("minimum_impact_pick_score", 0))
    impact_slots = int(scoring["selection"].get("impact_picks", 0))
    impact_candidates = [
        player
        for player in players
        if player["role_scores"].get("impact", 0) >= impact_min
    ]
    impact_candidates.sort(key=lambda row: row["role_scores"]["impact"], reverse=True)
    impact_award_keys: set[tuple[str, str, int]] = set()
    for rank, player in enumerate(impact_candidates[:impact_slots], start=1):
        player_key = _player_key(player)
        _add_choice_award(candidates, player, "impact_pick", rank, "impact")
        impact_award_keys.add(player_key)
        headline_keys.add(player_key)
        headline_teams.add(str(player["team"]))
    supplemental_impact_candidates = [
        player
        for player in impact_candidates
        if _player_key(player) not in player_of_day_keys
        and _player_key(player) not in impact_award_keys
        and str(player["team"]) not in headline_teams
    ]
    for rank, player in enumerate(supplemental_impact_candidates[:impact_slots], start=1):
        player_key = _player_key(player)
        _add_choice_award(candidates, player, "impact_pick", impact_slots + rank, "impact")
        impact_award_keys.add(player_key)
        headline_keys.add(player_key)
        headline_teams.add(str(player["team"]))

    player = _top_role_player(
        players,
        "progressor",
        avoid_heavy_defensive_loss=apply_editorial_guards,
    )
    if player is not None:
        _add_choice_award(candidates, player, "progression_pick", 1, "progressor")

    player = _top_role_player(
        players,
        "defensive",
        avoid_heavy_defensive_loss=apply_editorial_guards,
    )
    if player is not None:
        _add_choice_award(candidates, player, "defensive_pick", 1, "defensive")

    player = _top_goalkeeper_watch_player(players, scoring)
    if player is not None:
        _add_choice_award(candidates, player, "goalkeeper_watch", 1, "goalkeeper")

    hidden_player = _top_hidden_gem_player(
        players,
        excluded_keys=headline_keys,
        excluded_teams=headline_teams,
        used_teams={str(candidate["player"]["team"]) for candidate in candidates.values()},
        attachable_keys=set(candidates) - headline_keys,
        scoring=scoring,
    )
    if hidden_player is not None:
        _add_choice_award(candidates, hidden_player, "hidden_gem", 1, _best_role_score(hidden_player))

    choices = [_choice_from_candidate(candidate) for candidate in candidates.values()]
    return sorted(
        choices,
        key=lambda choice: (
            AWARD_DISPLAY_PRIORITY.get(choice["award_type"], 999),
            int(choice["rank"]),
            -float(choice["score"]),
            str(choice["player_name"]),
        ),
    )


def _add_choice_award(
    candidates: dict[tuple[str, str, int], dict[str, Any]],
    player: dict[str, Any],
    award_type: str,
    rank: int,
    primary_score: str,
) -> None:
    key = _player_key(player)
    candidate = candidates.setdefault(key, {"player": player, "awards": {}})
    score = _score_value(player, primary_score)
    existing = candidate["awards"].get(award_type)
    if existing is not None and float(existing["score"]) >= score:
        return
    candidate["awards"][award_type] = {
        "rank": rank,
        "primary_score": primary_score,
        "score": score,
    }


def _score_value(player: dict[str, Any], primary_score: str) -> float:
    if primary_score in {"composite_score", "headline_score"}:
        return float(player[primary_score])
    return float(player["role_scores"][primary_score])


def _choice_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    player = candidate["player"]
    awards = candidate["awards"]
    primary_award_type = min(
        awards,
        key=lambda award_type: (
            AWARD_DISPLAY_PRIORITY.get(award_type, 999),
            int(awards[award_type]["rank"]),
            -float(awards[award_type]["score"]),
        ),
    )
    primary = awards[primary_award_type]
    award_types = sorted(
        awards,
        key=lambda award_type: (
            AWARD_DISPLAY_PRIORITY.get(award_type, 999),
            int(awards[award_type]["rank"]),
            -float(awards[award_type]["score"]),
        ),
    )
    return _choice(
        primary_award_type,
        player,
        int(primary["rank"]),
        primary_score=str(primary["primary_score"]),
        award_types=award_types,
    )


def _choice(
    award_type: str,
    player: dict[str, Any],
    rank: int,
    primary_score: str,
    *,
    award_types: list[str] | None = None,
) -> dict[str, Any]:
    award_types = award_types or [award_type]
    if primary_score in {"composite_score", "headline_score"}:
        score = player[primary_score]
        components = _top_components_across_roles(player)
    else:
        score = player["role_scores"][primary_score]
        components = player["score_components"].get(primary_score, [])
    audit_components = _audit_score_components(player, components)
    return {
        "award_type": award_type,
        "award_types": award_types,
        "award_label": AWARD_LABELS[award_type],
        "badges": [_award_badge(label_type) for label_type in award_types],
        "rank": rank,
        "match_key": player["match_key"],
        "match_no": player["match_no"],
        "player_no": player["player_no"],
        "player_name": player["player_name"],
        "team": player["team"],
        "opponent": player["opponent"],
        "home_score": player.get("home_score"),
        "away_score": player.get("away_score"),
        "team_final_goals": player.get("team_final_goals"),
        "opponent_final_goals": player.get("opponent_final_goals"),
        "position": player["position"],
        "score": round(float(score), 1),
        "primary_score": primary_score,
        "role_scores": player["role_scores"],
        "progression_benchmark": player.get("progression_benchmark"),
        "hidden_gem_profile": player.get("hidden_gem_profile"),
        "flow_context": player.get("flow_context"),
        "metrics": _choice_metrics(player, award_type),
        "score_components": audit_components,
        "evidence_chips": _evidence_chips(player, award_type),
        "draft": _draft_brief(player, award_type),
    }


def _award_badge(award_type: str) -> dict[str, Any]:
    return {
        "type": award_type,
        "label": AWARD_LABELS[award_type],
    }


def _audit_score_components(
    player: dict[str, Any],
    base_components: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    important_metrics = {
        "goals",
        "assists",
        "goal_involvements",
        "only_goal_winner",
        "opening_goal",
        "equalizing_goal",
        "go_ahead_goal",
        "match_winning_goal",
        "late_match_winning_goal",
        "comeback_equalizer",
        "comeback_winner",
        "brace",
        "hat_trick",
        "substitute_goal",
        "substitute_brace",
    }
    selected: list[dict[str, Any]] = []
    seen_metrics: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        metric = str(item.get("metric") or "")
        if metric and metric not in seen_metrics:
            selected.append(item)
            seen_metrics.add(metric)

    for item in base_components:
        if len(selected) >= min(8, limit):
            break
        add(item)

    for item in _top_components_across_roles(player):
        if len(selected) >= limit:
            break
        if str(item.get("metric") or "") in important_metrics:
            add(item)

    return selected


def _choice_metrics(player: dict[str, Any], award_type: str) -> dict[str, int | float]:
    if award_type == "goalkeeper_watch":
        metric_names = [
            "clean_sheet",
            "opponent_xg",
            "opponent_attempts_on_target",
            "opponent_attempts_total",
            "keeper_saved_shots",
        ]
    elif award_type in {"player_of_the_day", "impact_pick"} and _has_direct_scoring_case(player):
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
        metric: _clean_number(float(player.get(metric) or 0))
        for metric in metric_names
        if float(player.get(metric) or 0) > 0
    }


def _has_direct_scoring_case(player: dict[str, Any]) -> bool:
    return (
        int(player.get("goals") or 0) > 0
        or int(player.get("assists") or 0) > 0
        or int(player.get("goal_involvements") or 0) > 0
    )


def _top_hidden_gem_player(
    players: list[dict[str, Any]],
    *,
    excluded_keys: set[tuple[str, str, int]],
    excluded_teams: set[str],
    used_teams: set[str],
    attachable_keys: set[tuple[str, str, int]],
    scoring: dict[str, Any],
) -> dict[str, Any] | None:
    if int(scoring["selection"].get("hidden_gems", 0)) <= 0:
        return None
    hidden_min = float(scoring["selection"]["minimum_hidden_gem_role_score"])
    require_distinct_team = bool(scoring["selection"].get("require_hidden_gem_distinct_team", True))
    candidates = [
        player
        for player in players
        if _player_key(player) not in excluded_keys
        and player["team"] not in excluded_teams
        and (
            not require_distinct_team
            or player["team"] not in used_teams
            or _player_key(player) in attachable_keys
        )
        and int(player.get("goals") or 0) == 0
        and _hidden_selection_score(player) >= hidden_min
        and _hidden_gem_profile_is_publishable(player, scoring)
        and not _hidden_gem_contextual_risk(player)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda player: (
            _hidden_profile_priority(player),
            float(player.get("hidden_gem_profile", {}).get("score") or 0),
            _hidden_role_score(player),
        ),
    )


def _top_goalkeeper_watch_player(
    players: list[dict[str, Any]],
    scoring: dict[str, Any],
) -> dict[str, Any] | None:
    selection = scoring.get("selection", {})
    if int(selection.get("goalkeeper_watch", 0)) <= 0:
        return None
    min_xg = float(selection.get("minimum_goalkeeper_opponent_xg", 1.0))
    min_on_target = float(selection.get("minimum_goalkeeper_opponent_on_target", 5))
    min_score = float(selection.get("minimum_goalkeeper_score", 0))
    require_clean_sheet = bool(selection.get("require_goalkeeper_clean_sheet", True))
    candidates = [
        player
        for player in players
        if str(player.get("position") or "").upper() == "GK"
        and int(player.get("started") or 0) == 1
        and (not require_clean_sheet or int(player.get("clean_sheet") or 0) == 1)
        and float(player.get("opponent_xg") or 0) >= min_xg
        and float(player.get("opponent_attempts_on_target") or 0) >= min_on_target
        and player["role_scores"].get("goalkeeper", 0) >= min_score
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda player: (
            player["role_scores"].get("goalkeeper", 0),
            float(player.get("opponent_xg") or 0),
            float(player.get("opponent_attempts_on_target") or 0),
        ),
    )


def _top_role_player(
    players: list[dict[str, Any]],
    score_name: str,
    *,
    avoid_heavy_defensive_loss: bool = False,
) -> dict[str, Any] | None:
    candidates = [
        player
        for player in players
        if str(player.get("position") or "").upper() != "GK"
        and player["role_scores"].get(score_name, 0) > 0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: row["role_scores"][score_name], reverse=True)
    if score_name == "defensive" and avoid_heavy_defensive_loss:
        safer_candidate = _top_safer_defensive_candidate(
            candidates,
            minimum_score=candidates[0]["role_scores"][score_name] * 0.75,
        )
        if safer_candidate is not None:
            return safer_candidate
    return candidates[0]


def _review_editorial_selection(
    players: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    if not choices:
        alerts.append(
            {
                "level": "high",
                "code": "no_editorial_choices",
                "message": "No editorial choices were generated.",
            }
        )
        return {"status": "needs_adjustment", "alerts": alerts}

    defensive_pick = next(
        (choice for choice in choices if _choice_has_award(choice, "defensive_pick")),
        None,
    )
    if defensive_pick is not None and _heavy_defensive_loss(defensive_pick):
        replacement = _safer_defensive_replacement(players, choices, defensive_pick)
        alerts.append(
            {
                "level": "high" if replacement else "medium",
                "code": "defensive_pick_from_heavy_loss",
                "message": (
                    f"{defensive_pick['player_name']} has the top defensive score, "
                    f"but {defensive_pick['team']} conceded "
                    f"{_team_goals_conceded(defensive_pick)} in a heavy loss."
                ),
                "player_name": defensive_pick["player_name"],
                "team": defensive_pick["team"],
                "replacement_candidate": replacement["player_name"] if replacement else None,
            }
        )

    hidden_gem = next((choice for choice in choices if _choice_has_award(choice, "hidden_gem")), None)
    if hidden_gem is not None:
        teams_before_hidden = {
            choice["team"]
            for choice in choices
            if choice is not hidden_gem
        }
        replacement = _diverse_hidden_gem_replacement(
            players,
            choices,
            hidden_gem,
            minimum_role_score=float(scoring["selection"]["minimum_hidden_gem_role_score"]),
        )
        if hidden_gem["team"] in teams_before_hidden and replacement is not None:
            alerts.append(
                {
                    "level": "high",
                    "code": "hidden_gem_duplicates_existing_team",
                    "message": (
                        f"{hidden_gem['player_name']} is a strong hidden-gem profile, "
                        f"but {hidden_gem['team']} already has another pick and "
                        f"{replacement['player_name']} gives the slate a distinct match angle."
                    ),
                    "player_name": hidden_gem["player_name"],
                    "team": hidden_gem["team"],
                    "replacement_candidate": replacement["player_name"],
                }
            )
        if _hidden_gem_contextual_risk(hidden_gem) and replacement is not None:
            alerts.append(
                {
                    "level": "high",
                    "code": "hidden_gem_defensive_profile_from_heavy_loss",
                    "message": (
                        f"{hidden_gem['player_name']} has a strong defensive hidden-gem profile, "
                        f"but {hidden_gem['team']} conceded "
                        f"{_team_goals_conceded(hidden_gem)} in a heavy loss."
                    ),
                    "player_name": hidden_gem["player_name"],
                    "team": hidden_gem["team"],
                    "replacement_candidate": replacement["player_name"],
                }
            )

    team_counts: dict[str, int] = {}
    for choice in choices:
        team_counts[choice["team"]] = team_counts.get(choice["team"], 0) + 1
    repeated_teams = [
        {"team": team, "count": count}
        for team, count in sorted(team_counts.items())
        if count > 1
    ]
    if repeated_teams:
        alerts.append(
            {
                "level": "info",
                "code": "same_team_multiple_picks",
                "message": "Multiple picks can still come from one team when roles are clearly distinct.",
                "teams": repeated_teams,
            }
        )

    status = "needs_adjustment" if any(alert["level"] == "high" for alert in alerts) else "publishable"
    return {"status": status, "alerts": alerts}


def _choice_has_award(choice: dict[str, Any], award_type: str) -> bool:
    return award_type in _choice_award_types(choice)


def _choice_award_types(choice: dict[str, Any]) -> list[str]:
    award_types = choice.get("award_types")
    if isinstance(award_types, list) and award_types:
        return [str(item) for item in award_types]
    return [str(choice.get("award_type") or "")]


def _selection_review_iteration(
    iteration: int,
    choices: list[dict[str, Any]],
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "status": review["status"],
        "alerts": review["alerts"],
        "choice_names": [choice["player_name"] for choice in choices],
    }


def _top_safer_defensive_candidate(
    candidates: list[dict[str, Any]],
    *,
    minimum_score: float,
) -> dict[str, Any] | None:
    safer_candidates = [
        player
        for player in candidates
        if player["role_scores"].get("defensive", 0) >= minimum_score
        and not _heavy_defensive_loss(player)
    ]
    return safer_candidates[0] if safer_candidates else None


def _safer_defensive_replacement(
    players: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    current: dict[str, Any],
) -> dict[str, Any] | None:
    current_key = _player_key(current)
    used_keys = {
        _player_key(choice)
        for choice in choices
        if _player_key(choice) != current_key
    }
    candidates = [
        player
        for player in players
        if _player_key(player) not in used_keys
        and player["role_scores"].get("defensive", 0)
        >= current["role_scores"].get("defensive", 0) * 0.75
        and not _heavy_defensive_loss(player)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row["role_scores"]["defensive"])


def _diverse_hidden_gem_replacement(
    players: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    current: dict[str, Any],
    *,
    minimum_role_score: float,
) -> dict[str, Any] | None:
    current_key = _player_key(current)
    used_keys = {
        _player_key(choice)
        for choice in choices
        if _player_key(choice) != current_key
    }
    used_teams = {
        choice["team"]
        for choice in choices
        if _player_key(choice) != current_key
    }
    candidates = [
        player
        for player in players
        if _player_key(player) not in used_keys
        and player["team"] not in used_teams
        and int(player.get("goals") or 0) == 0
        and _hidden_selection_score(player) >= minimum_role_score
        and _hidden_gem_profile_is_publishable(player, {"selection": {}})
        and not _hidden_gem_contextual_risk(player)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda player: (
            _hidden_profile_priority(player),
            float(player.get("hidden_gem_profile", {}).get("score") or 0),
            _hidden_role_score(player),
        ),
    )


def _hidden_profile_priority(player: dict[str, Any]) -> int:
    profile = player.get("hidden_gem_profile", {}).get("profile")
    if profile == "off_ball_threat":
        return 3
    if profile == "defensive_resistance":
        return 2
    if profile == "progression_engine":
        return 1
    return 0


def _hidden_gem_profile_is_publishable(
    player: dict[str, Any],
    scoring: dict[str, Any],
) -> bool:
    profile = player.get("hidden_gem_profile", {})
    if not profile.get("eligible"):
        return False
    profile_name = str(profile.get("profile") or "")
    profile_score = float(profile.get("score") or 0)
    selection = scoring.get("selection", {})
    thresholds = (
        selection.get("hidden_gem_profile_thresholds", {})
        if isinstance(selection, dict)
        else {}
    )
    default_thresholds = {
        "off_ball_threat": 62.0,
        "defensive_resistance": 55.0,
        "progression_engine": 30.0,
    }
    threshold = float(thresholds.get(profile_name, default_thresholds.get(profile_name, 999.0)))
    return profile_score >= threshold


def _heavy_defensive_loss(player: dict[str, Any]) -> bool:
    return _team_goals_conceded(player) >= 3 and _team_goal_difference(player) <= -2


def _hidden_gem_contextual_risk(player: dict[str, Any]) -> bool:
    return _heavy_defensive_loss(player)


def _team_goals_conceded(player: dict[str, Any]) -> int:
    return int(player.get("opponent_final_goals") or 0)


def _team_goal_difference(player: dict[str, Any]) -> int:
    return int(player.get("team_final_goals") or 0) - int(player.get("opponent_final_goals") or 0)


def _hidden_role_score(player: dict[str, Any]) -> float:
    return max(
        player["role_scores"]["progressor"],
        player["role_scores"]["off_ball"],
        player["role_scores"]["defensive"],
    )


def _hidden_selection_score(player: dict[str, Any]) -> float:
    profile_score = float(player.get("hidden_gem_profile", {}).get("score") or 0)
    return max(_hidden_role_score(player), profile_score)


def _best_role_score(player: dict[str, Any]) -> str:
    return max(
        ["progressor", "off_ball", "defensive"],
        key=lambda score_name: player["role_scores"][score_name],
    )


def _top_components_across_roles(player: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for score_name, items in player["score_components"].items():
        if score_name == "goalkeeper" and str(player.get("position") or "").upper() != "GK":
            continue
        for item in items:
            components.append({**item, "score": score_name})
    return sorted(components, key=lambda item: item["contribution"], reverse=True)


def _evidence_chips(player: dict[str, Any], award_type: str) -> dict[str, list[str]]:
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
    direct_scoring_case = _has_direct_scoring_case(player)
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


def _draft_brief(player: dict[str, Any], award_type: str) -> dict[str, dict[str, str]]:
    return {
        "en": _english_draft_brief(player, award_type),
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


def _english_metric_summary(player: dict[str, Any]) -> str:
    metrics = _metric_summary_items(player)
    return ", ".join(f"{item['label_en']} {item['value']}" for item in metrics)


def _metric_summary_items(player: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "goals": ("goals", "进球"),
        "assists": ("assists", "助攻"),
        "goal_involvements": ("goal involvements", "参与进球"),
        "brace": ("brace", "梅开二度"),
        "hat_trick": ("hat-trick", "帽子戏法"),
        "substitute_goal": ("substitute goals", "替补进球"),
        "substitute_brace": ("substitute brace", "替补双响"),
        "only_goal_winner": ("only goal", "全场唯一进球"),
        "opening_goal": ("opening goal", "首开纪录"),
        "equalizing_goal": ("equaliser", "扳平进球"),
        "go_ahead_goal": ("go-ahead goal", "领先进球"),
        "match_winning_goal": ("match-winning goal", "制胜进球"),
        "late_goal": ("late goal", "晚段进球"),
        "stoppage_time_goal": ("stoppage-time goal", "补时进球"),
        "late_match_winning_goal": ("late winner", "补时制胜球"),
        "team_came_from_behind_goal": ("comeback goal", "逆转进程进球"),
        "comeback_equalizer": ("comeback equaliser", "逆转扳平球"),
        "comeback_winner": ("comeback winner", "逆转制胜球"),
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
        "clean_sheet": ("clean sheet", "零封"),
        "opponent_xg": ("opponent xG", "对手xG"),
        "opponent_attempts_on_target": ("opponent shots on target", "对手射正"),
        "opponent_attempts_total": ("opponent attempts", "对手射门"),
        "keeper_saved_shots": ("saved-shot outcomes", "Saved结果"),
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
    if not any(_choice_has_award(choice, "hidden_gem") for choice in choices):
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


def _zh_fact_bank_payload(report: dict[str, Any]) -> dict[str, Any]:
    matches_by_key = {
        str(match["match_key"]): match
        for match in report.get("matches", [])
    }
    return {
        "schema_version": 1,
        "language": "zh",
        "generated_at": report["generated_at"],
        "match_date": report["match_date"],
        "scoring_version": report["scoring_version"],
        "editorial_process": "from_scratch_chinese_sports_editor",
        "editorial_voice": (
            "严肃足球数据分析员面向大众发帖：判断清楚，语气可以轻松一点；"
            "先讲球场作用，再自然带一两个关键事实。"
        ),
        "forbidden_inputs": [
            "英文稿",
            "英文标题",
            "英文成稿",
            "已成型选择理由句子",
        ],
        "editorial_review_guidance": [
            "先用中文体育编辑视角从事实重写，不继承旧稿句式。",
            "再做 qu-ai-wei 式严格审稿：删翻译腔、空话、事实越界。",
            "只在卡片不顺时做 humanizer-zh 式语感修复。",
        ],
        "choices": [
            _zh_fact_bank_choice(choice, matches_by_key.get(str(choice["match_key"])))
            for choice in report["choices"]
        ],
    }


def _zh_fact_bank_choice(
    choice: dict[str, Any],
    match: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "award_type": choice["award_type"],
        "award_types": _choice_award_types(choice),
        "award_label": choice["award_label"]["zh"],
        "award_badges": [
            str(badge.get("label", {}).get("zh") or "")
            for badge in choice.get("badges", [])
            if isinstance(badge, dict)
        ],
        "player_name": _zh_player_name(choice["player_name"]),
        "team": _zh_team_name(choice["team"]),
        "opponent": _zh_team_name(choice["opponent"]),
        "match_no": choice["match_no"],
        "match_scoreline": _zh_match_scoreline(choice, match),
        "position": choice.get("position"),
        "facts": _zh_fact_bank_facts(choice),
        "allowed_angles": _zh_allowed_angles(choice),
        "evidence_chips": choice["evidence_chips"]["zh"],
    }


def _zh_match_scoreline(choice: dict[str, Any], match: dict[str, Any] | None) -> str:
    if not match:
        return ""
    home = _zh_team_name(str(match["home_team"]))
    away = _zh_team_name(str(match["away_team"]))
    if choice["team"] == match["away_team"]:
        return f"{away} {match['away_score']}-{match['home_score']} {home}"
    return f"{home} {match['home_score']}-{match['away_score']} {away}"


def _zh_fact_bank_facts(choice: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    for chip in choice["evidence_chips"]["zh"]:
        _append_unique(facts, chip)
    for fact in _zh_flow_facts(choice):
        _append_unique(facts, fact)
    for item in _choice_metric_items(choice, "zh"):
        _append_unique(facts, _zh_metric_fact(item))
    return facts


def _zh_flow_facts(choice: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    flow_context = choice.get("flow_context") or {}
    if flow_context.get("team_came_from_behind_to_win"):
        _append_unique(
            facts,
            (
                f"{_zh_team_name(choice['team'])} 0-1 落后后 "
                f"{choice['team_final_goals']}-{choice['opponent_final_goals']} 逆转取胜"
            ),
        )
    for goal in flow_context.get("goals", []):
        minute = int(goal.get("minute") or 0)
        tags = {str(tag) for tag in goal.get("tags", [])}
        if "equalizer" in tags:
            _append_unique(facts, f"{minute}' 扳平")
        if "stoppage_time_goal" in tags and "match_winning_goal" in tags:
            _append_unique(facts, f"{minute}' 补时制胜")
        elif "match_winning_goal" in tags:
            _append_unique(facts, f"{minute}' 制胜")
        if "comeback_winner" in tags:
            _append_unique(facts, "完成逆转制胜球")
    return facts


def _zh_metric_fact(item: dict[str, Any]) -> str:
    metric = str(item["metric"])
    value = _format_zh_value(item["value"])
    label = str(item["label"])
    unit = str(item.get("unit") or "")
    if metric == "goals":
        return f"{value} 个进球"
    if metric == "clean_sheet":
        return "完成零封"
    if metric == "opponent_xg":
        return f"对手 xG {value}"
    if metric == "opponent_attempts_on_target":
        return f"对手 {value} 次射正"
    if metric == "opponent_attempts_total":
        return f"对手 {value} 次射门"
    if metric == "keeper_saved_shots":
        return f"对手射门有 {value} 次 Saved 结果"
    if metric == "total_distance_m":
        return f"跑动距离 {value} {unit}"
    return f"{value} 次{label}"


def _format_zh_value(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _append_unique(items: list[str], item: str) -> None:
    if item and item not in items:
        items.append(item)


def _zh_allowed_angles(choice: dict[str, Any]) -> list[str]:
    goals = _metric_value(choice, "goals")
    flow_context = choice.get("flow_context") or {}
    allowed = list(flow_context.get("allowed_claims", {}).get("zh", []))
    if _metric_value(choice, "comeback_winner") > 0:
        return [*allowed[:3], "逆转过程中的决定性人物", "补时制胜要写清楚来龙去脉"]
    if _metric_value(choice, "substitute_brace") > 0:
        return [*allowed[:2], "替补双响", "改变比赛走势", "不用包装得太复杂"]
    if _metric_value(choice, "only_goal_winner") > 0:
        return ["全场唯一进球", "决定比分", "直接写关键性"]
    if goals >= 3:
        return ["明显最佳", "不必绕远", "可以补充他不只负责最后一脚"]
    if goals >= 2:
        return ["进球很醒目", "优先写进球和助攻", "不要把身后接应和接应成功写成同一动作"]
    if _metric_value(choice, "late_match_winning_goal") > 0:
        return ["补时绝杀", "不只靠最后一脚", "全场贡献支撑这个瞬间"]
    if _metric_value(choice, "match_winning_goal") > 0:
        return ["制胜球", "决定比分走势", "不只靠最后一脚"]
    if _choice_has_award(choice, "progression_pick"):
        if _choice_goal_difference(choice) < 0:
            return ["输球方亮点", "把球从压力里带出来", "推进出口"]
        if (choice.get("flow_context") or {}).get("team_came_from_behind_to_win"):
            return ["落后阶段保持向前路线", "把球从压力里带出来", "推进出口"]
        return ["把球从压力里带出来", "推进出口", "帮助球队持续向前处理"]
    if _choice_has_award(choice, "defensive_pick"):
        return ["承压局防守", "让对手进攻停下来", "脏活和硬活"]
    if _choice_has_award(choice, "goalkeeper_watch"):
        return [
            "零封有压力",
            "对手射正和xG说明防守承压",
            "不要写成官方扑救、扑出或被他挡出",
        ]
    if _choice_has_award(choice, "hidden_gem"):
        return ["不抢镜", "持续提供接应角度", "让前场不断线"]
    return ["中场连接点", "接应和转移", "帮助球队持续向前处理"]


def _english_brief_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "language": "en",
        "generated_at": report["generated_at"],
        "match_date": report["match_date"],
        "scoring_version": report["scoring_version"],
        "editorial_voice": _english_editorial_voice(),
        "choices": [
            _english_choice_brief(choice)
            for choice in report["choices"]
        ],
        "review_checklist": _english_review_checklist(),
    }


def _english_choice_brief(choice: dict[str, Any]) -> dict[str, Any]:
    return {
        "award_type": choice["award_type"],
        "award_types": _choice_award_types(choice),
        "award_label": choice["award_label"]["en"],
        "award_badges": [
            str(badge.get("label", {}).get("en") or "")
            for badge in choice.get("badges", [])
            if isinstance(badge, dict)
        ],
        "player_name": choice["player_name"],
        "team": choice["team"],
        "opponent": choice["opponent"],
        "match_no": choice["match_no"],
        "score": choice["score"],
        "why_selected": _en_selection_angle(choice),
        "title_candidates": _en_title_candidates(choice),
        "action_notes": _en_action_notes(choice),
        "flow_notes": _en_flow_notes(choice),
        "allowed_claims": (choice.get("flow_context") or {}).get("allowed_claims", {}).get("en", []),
        "key_metrics": _choice_metric_items(choice, "en"),
        "evidence_chips": choice["evidence_chips"]["en"],
        "avoid": [
            "metric dumps",
            "generic AI phrasing",
            "claims that imply video review",
        ],
    }


def _english_editorial_voice() -> str:
    return (
        "A data-aware football analyst writing for a general audience: clear, light, "
        "and grounded in the evidence without sounding like a table."
    )


def _english_review_checklist() -> list[str]:
    return [
        "Title reads like natural English sports copy.",
        "Each pick has a distinct football angle.",
        "Evidence supports the claim without metric dumping.",
        "No implied video review or outside rating source.",
    ]


def _en_selection_angle(choice: dict[str, Any]) -> str:
    goals = _metric_value(choice, "goals")
    if _metric_value(choice, "comeback_winner") > 0:
        return "Lead with the comeback: he equalised, then scored the stoppage-time winner."
    if _metric_value(choice, "substitute_brace") > 0:
        return "Lead with the substitute brace and the way it changed the match."
    if _metric_value(choice, "only_goal_winner") > 0:
        return "Lead with the only goal in a one-goal match."
    if goals >= 3:
        return "Obvious pick: the hat-trick decides the top-line argument."
    if goals >= 2:
        return "Lead with the goals and assists; use off-ball counts only as separate supporting evidence."
    if _metric_value(choice, "late_match_winning_goal") > 0:
        return "Lead with the stoppage-time winner, then support it with the rest of his match profile."
    if _metric_value(choice, "match_winning_goal") > 0:
        return "Lead with the decisive goal, then support it with the broader match profile."
    if _choice_has_award(choice, "progression_pick"):
        if _choice_goal_difference(choice) < 0:
            return "Focus on moving the ball through pressure from a losing side."
        if (choice.get("flow_context") or {}).get("team_came_from_behind_to_win"):
            return "Focus on the forward passing that helped the team recover from a trailing position."
        return "Focus on moving the ball through pressure and into territory."
    if _choice_has_award(choice, "defensive_pick"):
        return "Focus on stopping attacks and forcing resets."
    if _choice_has_award(choice, "goalkeeper_watch"):
        return "Focus on the clean sheet under measurable shot pressure; avoid presenting saved-shot outcomes as an official goalkeeper saves table."
    if _choice_has_award(choice, "hidden_gem"):
        return "Explain the quieter linking work that kept possession connected."
    return "Focus on the connective midfield role."


def _en_title_candidates(choice: dict[str, Any]) -> list[str]:
    goals = _metric_value(choice, "goals")
    if _metric_value(choice, "comeback_winner") > 0:
        return ["The comeback finisher", "Level, then winner", "Two goals that turned it"]
    if _metric_value(choice, "substitute_brace") > 0:
        return ["The substitute who changed it", "Two goals off the bench", "The bench answer"]
    if _metric_value(choice, "only_goal_winner") > 0:
        return ["The only goal mattered", "The decisive scorer", "The 1-0 answer"]
    if goals >= 3:
        return ["The hat-trick was enough", "Three goals, no debate", "The obvious top pick"]
    if goals >= 2:
        if _metric_value(choice, "assists") > 0:
            return ["Two goals and an assist", "The direct scoring case", "The finisher with one more touch"]
        return ["Two goals, clean argument", "The direct scoring case", "The brace that stood out"]
    if _metric_value(choice, "late_match_winning_goal") > 0:
        return ["The late answer", "The winner at the end", "One finish that changed the day"]
    if _metric_value(choice, "match_winning_goal") > 0:
        return ["The decisive touch", "The goal that tilted it", "The moment that mattered"]
    if _choice_has_award(choice, "progression_pick"):
        if _choice_goal_difference(choice) < 0:
            return ["Progression from a losing side", "Carrying through pressure", "The best route forward"]
        if (choice.get("flow_context") or {}).get("team_came_from_behind_to_win"):
            return ["The route back into it", "Forward passing under pressure", "Progression in the comeback"]
        return ["The best route forward", "Carrying through pressure", "Forward passing under control"]
    if _choice_has_award(choice, "defensive_pick"):
        return ["The stubborn stopper", "Breaking the flow", "The defender who kept resetting attacks"]
    if _choice_has_award(choice, "goalkeeper_watch"):
        return ["The clean sheet under pressure", "A harder clean sheet than it looked", "The zero that mattered"]
    if _choice_has_award(choice, "hidden_gem"):
        return ["The quiet connector", "The link behind the highlights", "A useful game between the lines"]
    return ["The midfield connector", "The link in possession", "A quiet route through midfield"]


def _en_action_notes(choice: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for note in _en_flow_notes(choice):
        _append_unique(notes, note)
    if _metric_value(choice, "substitute_brace") > 0:
        notes.append("scored twice after coming off the bench")
    if _metric_value(choice, "only_goal_winner") > 0:
        notes.append("scored the only goal of the match")
    if _metric_value(choice, "late_match_winning_goal") > 0:
        notes.append("scored the stoppage-time winner")
    elif _metric_value(choice, "match_winning_goal") > 0:
        notes.append("scored the match-winning goal")
    if _metric_value(choice, "goals") >= 3:
        notes.append("scored a hat-trick")
    elif _metric_value(choice, "goals") >= 2:
        notes.append("scored twice")
    if _metric_value(choice, "line_breaks_completed") >= 12:
        notes.append("repeatedly broke the opponent's lines")
    if _metric_value(choice, "ball_progressions") >= 10:
        notes.append("carried the ball through pressure")
    if _metric_value(choice, "offers_received") >= 25:
        notes.append("kept giving teammates a passing option")
    if _metric_value(choice, "in_between") >= 15:
        notes.append("kept appearing between the lines")
    if _metric_value(choice, "possession_regains") >= 8:
        notes.append("won possession back repeatedly")
    if _metric_value(choice, "blocks") >= 8:
        notes.append("blocked attacks before they became cleaner chances")
    if _choice_has_award(choice, "goalkeeper_watch"):
        if _metric_value(choice, "clean_sheet") > 0:
            notes.append("kept a clean sheet")
        if _metric_value(choice, "opponent_attempts_on_target") >= 5:
            notes.append("faced sustained on-target pressure")
        if _metric_value(choice, "opponent_xg") >= 1.0:
            notes.append("held up against opponent xG pressure")
    return notes[:4]


def _en_flow_notes(choice: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    flow_context = choice.get("flow_context") or {}
    if flow_context.get("team_came_from_behind_to_win"):
        _append_unique(
            notes,
            (
                f"{choice['team']} came from behind to win "
                f"{choice['team_final_goals']}-{choice['opponent_final_goals']}"
            ),
        )
    for goal in flow_context.get("goals", []):
        minute = int(goal.get("minute") or 0)
        tags = {str(tag) for tag in goal.get("tags", [])}
        if "equalizer" in tags:
            _append_unique(notes, f"{minute}' equaliser")
        if "stoppage_time_goal" in tags and "match_winning_goal" in tags:
            _append_unique(notes, f"{minute}' stoppage-time winner")
        elif "match_winning_goal" in tags:
            _append_unique(notes, f"{minute}' winner")
        if "comeback_winner" in tags:
            _append_unique(notes, "comeback winner")
    return notes


def _choice_goal_difference(choice: dict[str, Any]) -> int:
    return int(choice.get("team_final_goals") or 0) - int(choice.get("opponent_final_goals") or 0)


def _choice_metric_items(choice: dict[str, Any], language: str) -> list[dict[str, Any]]:
    labels = {
        "goals": {"en": "goals", "zh": "进球"},
        "assists": {"en": "assists", "zh": "助攻"},
        "goal_involvements": {"en": "goal involvements", "zh": "参与进球"},
        "brace": {"en": "brace", "zh": "梅开二度"},
        "hat_trick": {"en": "hat-trick", "zh": "帽子戏法"},
        "substitute_goal": {"en": "substitute goals", "zh": "替补进球"},
        "substitute_brace": {"en": "substitute brace", "zh": "替补双响"},
        "only_goal_winner": {"en": "only goal", "zh": "全场唯一进球"},
        "opening_goal": {"en": "opening goal", "zh": "首开纪录"},
        "equalizing_goal": {"en": "equaliser", "zh": "扳平进球"},
        "go_ahead_goal": {"en": "go-ahead goal", "zh": "领先进球"},
        "match_winning_goal": {"en": "match-winning goal", "zh": "制胜进球"},
        "late_goal": {"en": "late goal", "zh": "晚段进球"},
        "stoppage_time_goal": {"en": "stoppage-time goal", "zh": "补时进球"},
        "late_match_winning_goal": {"en": "late winner", "zh": "补时制胜球"},
        "team_came_from_behind_goal": {"en": "comeback goal", "zh": "逆转进程进球"},
        "comeback_equalizer": {"en": "comeback equaliser", "zh": "逆转扳平球"},
        "comeback_winner": {"en": "comeback winner", "zh": "逆转制胜球"},
        "on_target": {"en": "shots on target", "zh": "射正"},
        "line_breaks_completed": {"en": "completed line breaks", "zh": "打穿防线"},
        "ball_progressions": {"en": "ball progressions", "zh": "推进"},
        "take_ons": {"en": "take-ons", "zh": "尝试过人"},
        "offers_received": {"en": "received offers", "zh": "接应成功"},
        "in_between": {"en": "between-line offers", "zh": "两线间接应"},
        "in_behind": {"en": "in-behind offers", "zh": "身后接应"},
        "possession_regains": {"en": "possession regains", "zh": "夺回球权"},
        "possession_interrupted": {"en": "interruptions", "zh": "破坏进攻"},
        "blocks": {"en": "blocks", "zh": "封堵"},
        "clean_sheet": {"en": "clean sheet", "zh": "零封"},
        "opponent_xg": {"en": "opponent xG", "zh": "对手xG"},
        "opponent_attempts_on_target": {"en": "opponent shots on target", "zh": "对手射正"},
        "opponent_attempts_total": {"en": "opponent attempts", "zh": "对手射门"},
        "keeper_saved_shots": {"en": "saved-shot outcomes", "zh": "Saved结果"},
        "total_distance_m": {"en": "distance", "zh": "跑动距离"},
    }
    direct_goal_story = (
        any(
            award_type in {"player_of_the_day", "impact_pick"}
            for award_type in _choice_award_types(choice)
        )
        and (
            _metric_value(choice, "goals") > 0
            or _metric_value(choice, "assists") > 0
        )
    )
    direct_story_skip = {
        "offers_received",
        "in_between",
        "in_behind",
        "total_distance_m",
        "top_speed_kmh",
    }
    items: list[dict[str, Any]] = []
    for component in choice.get("score_components", []):
        metric = str(component.get("metric"))
        if direct_goal_story and metric in direct_story_skip:
            continue
        if metric not in labels:
            continue
        value = _clean_number(float(component.get("value") or 0))
        unit = "m" if metric == "total_distance_m" and language == "en" else ""
        unit = "米" if metric == "total_distance_m" and language == "zh" else unit
        items.append(
            {
                "metric": metric,
                "label": labels[metric][language],
                "value": value,
                "unit": unit,
            }
        )
        if len(items) >= 5:
            break
    return items


def _metric_value(choice: dict[str, Any], metric: str) -> float:
    for component in choice.get("score_components", []):
        if component.get("metric") == metric:
            return float(component.get("value") or 0)
    return 0.0


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


def _render_editorial_index(items: list[dict[str, Any]]) -> str:
    latest = items[0] if items else {}
    latest_date = html.escape(str(latest.get("match_date") or ""), quote=False)
    latest_line = (
        f'Latest available match-day editorial picks: <a href="{latest_date}/">{latest_date}</a>.'
        if latest_date
        else "No editorial reports have been published yet."
    )
    links = "\n".join(_archive_item_html(item) for item in items)
    if not links:
        links = '<p class="lede">Run the editorial workflow to publish the first report.</p>'
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
    <p class="lede">{latest_line}</p>
    <section class="archive-list" aria-label="Editorial archive">
      {links}
    </section>
  </main>
</body>
</html>
"""


def _archive_item_html(item: dict[str, Any]) -> str:
    match_date = html.escape(str(item["match_date"]), quote=False)
    badge_class = "badge official" if item["uses_official_assists"] else "badge legacy"
    badge_label = "official assists" if item["uses_official_assists"] else "legacy: no official assists"
    match_count = int(item.get("match_count") or 0)
    match_label = "match" if match_count == 1 else "matches"
    return (
        '<a class="archive-row" href="'
        f'{match_date}/">'
        f"<strong>{match_date}</strong>"
        f'<span>{match_count} {match_label}</span>'
        f'<span class="{badge_class}">{html.escape(badge_label, quote=False)}</span>'
        "</a>"
    )


def _choices_html(choices: list[dict[str, Any]]) -> str:
    cards = []
    for choice in choices:
        en = choice["content"]["en"]
        zh = choice["content"]["zh"]
        chips = "".join(
            f"<span>{html.escape(chip, quote=False)}</span>"
            for chip in choice["evidence_chips"]["en"]
        )
        badges = "".join(
            (
                '<span class="award-badge">'
                f'{html.escape(str(badge.get("label", {}).get("en") or ""), quote=False)}'
                "</span>"
            )
            for badge in choice.get("badges", [])
            if isinstance(badge, dict)
        )
        card = f"""
    <article class="choice-card">
      <div>
        <p class="award">{html.escape(choice["award_label"]["en"], quote=False)}</p>
        <div class="award-badges">{badges}</div>
        <h2>{html.escape(format_player(choice["player_name"], choice["team"]), quote=False)}</h2>
        <p class="meta">{html.escape(format_team(choice["team"]), quote=False)} vs {html.escape(format_team(choice["opponent"]), quote=False)} · Match {choice["match_no"]}</p>
        <h3>{html.escape(en["title"], quote=False)}</h3>
        {en["html"]}
        <h3>{html.escape(zh["title"], quote=False)}</h3>
        {zh["html"]}
      </div>
      <aside>
        <div class="chips">{chips}</div>
      </aside>
    </article>
        """
        cards.append("\n".join(line.rstrip() for line in card.strip("\n").splitlines()))
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
        zh_placeholder = _zh_markdown_placeholder(choice)
        tags = " · ".join(
            badge["label"]["en"]
            for badge in choice.get("badges", [])
            if isinstance(badge, dict)
        )
        lines.extend(
            [
                f"### {choice['award_label']['en']}: {choice['player_name']}",
                "",
                f"_{choice['team']} vs {choice['opponent']} · Match {choice['match_no']}_",
                "",
                f"_Tags: {tags}_",
                "",
                "#### English",
                "",
                f"**{choice['draft']['en']['title']}**",
                "",
                choice["draft"]["en"]["body"],
                "",
                "#### 中文",
                "",
                f"**{zh_placeholder['title']}**",
                "",
                zh_placeholder["body"],
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


def _zh_markdown_placeholder(choice: dict[str, Any]) -> dict[str, str]:
    facts = "，".join(_zh_fact_bank_facts(choice)[:4]) or "详见 fact_bank.zh.json"
    return {
        "title": f"中文素材 - {choice['award_label']['zh']}",
        "body": (
            "中文成稿由 editor agent 基于 fact_bank.zh.json 独立生成；"
            f"这里仅保留结构化事实占位。关键事实：{facts}。"
        ),
    }


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
    .award-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: -6px 0 10px; }
    .award-badge { border: 1px solid #dce5f2; background: #f7f9fc; color: #35465d; border-radius: 999px; padding: 4px 8px; font-size: 12px; font-weight: 700; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
    .chips span { background: #edf2fa; border: 1px solid #dce5f2; border-radius: 999px; padding: 5px 9px; font-size: 12px; }
    .archive-list { display: grid; gap: 10px; margin-top: 22px; }
    .archive-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 14px 16px; color: inherit; text-decoration: none; background: #fff; border: 1px solid #dde3ee; border-radius: 8px; }
    .archive-row:hover { border-color: #b7c4d4; }
    .archive-row span { color: #59677c; font-size: 13px; }
    .badge { justify-self: end; border-radius: 999px; padding: 4px 9px; border: 1px solid #dce5f2; background: #edf2fa; color: #35465d; font-size: 12px; }
    .badge.official { border-color: #b7dfd4; background: #e7f7f1; color: #0f766e; }
    .badge.legacy { border-color: #e7d8ad; background: #fff7df; color: #806215; }
    @media (max-width: 720px) { .choice-card { grid-template-columns: 1fr; } .choice-card aside { border-left: 0; border-top: 1px solid #e8edf5; padding-left: 0; padding-top: 14px; } }
    @media (max-width: 720px) { .archive-row { grid-template-columns: 1fr; align-items: start; } .badge { justify-self: start; } }
    """


def _player_key(player: dict[str, Any]) -> tuple[str, str, int]:
    return str(player["match_key"]), str(player["team"]), int(player["player_no"])


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _clean_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return round(value, 2)
