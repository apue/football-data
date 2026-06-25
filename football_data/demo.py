from __future__ import annotations

import html
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from football_data.flags import format_player, format_team


SCOPE_SPECS = [
    {
        "id": "group_round_1",
        "match_min": 1,
        "match_max": 24,
        "label": {"en": "Group Round 1", "zh": "小组赛第1轮"},
        "short": {"en": "Group R1", "zh": "小组第1轮"},
    },
    {
        "id": "group_round_2",
        "match_min": 25,
        "match_max": 48,
        "label": {"en": "Group Round 2", "zh": "小组赛第2轮"},
        "short": {"en": "Group R2", "zh": "小组第2轮"},
    },
    {
        "id": "group_round_3",
        "match_min": 49,
        "match_max": 72,
        "label": {"en": "Group Round 3", "zh": "小组赛第3轮"},
        "short": {"en": "Group R3", "zh": "小组第3轮"},
    },
    {
        "id": "round_of_32",
        "match_min": 73,
        "match_max": 88,
        "label": {"en": "Round of 32", "zh": "1/16决赛"},
        "short": {"en": "R32", "zh": "1/16"},
    },
    {
        "id": "round_of_16",
        "match_min": 89,
        "match_max": 96,
        "label": {"en": "Round of 16", "zh": "1/8决赛"},
        "short": {"en": "R16", "zh": "1/8"},
    },
    {
        "id": "quarter_finals",
        "match_min": 97,
        "match_max": 100,
        "label": {"en": "Quarter-finals", "zh": "1/4决赛"},
        "short": {"en": "QF", "zh": "1/4"},
    },
    {
        "id": "semi_finals",
        "match_min": 101,
        "match_max": 102,
        "label": {"en": "Semi-finals", "zh": "半决赛"},
        "short": {"en": "SF", "zh": "半决赛"},
    },
    {
        "id": "third_place",
        "match_min": 103,
        "match_max": 103,
        "label": {"en": "Third-place Play-off", "zh": "三四名决赛"},
        "short": {"en": "3rd", "zh": "三四名"},
    },
    {
        "id": "final",
        "match_min": 104,
        "match_max": 104,
        "label": {"en": "Final", "zh": "决赛"},
        "short": {"en": "Final", "zh": "决赛"},
    },
    {
        "id": "overall",
        "match_min": None,
        "match_max": None,
        "label": {"en": "Overall", "zh": "全部比赛"},
        "short": {"en": "Overall", "zh": "总体"},
    },
]

CATEGORY_SPECS = [
    {
        "id": "goalInvolvements",
        "metric": "goal_involvements",
        "title": {"en": "Goal Involvements", "zh": "进球参与"},
        "metric_label": {"en": "G+A", "zh": "进球+助攻"},
        "description": {
            "en": "Official goals and assists from the FIFA match timeline.",
            "zh": "来自 FIFA 比赛时间线的官方进球和助攻。",
        },
        "secondary": [
            ("goals", {"en": "Goals", "zh": "进球"}),
            ("assists", {"en": "Assists", "zh": "助攻"}),
        ],
        "tie_breakers": ["goals", "shots_on_target", "assists"],
    },
    {
        "id": "shotsOnTarget",
        "metric": "shots_on_target",
        "title": {"en": "Most Shots on Target", "zh": "射正最多"},
        "metric_label": {"en": "SOT", "zh": "射正"},
        "description": {
            "en": "Who kept turning chances into saves or goals.",
            "zh": "谁最稳定地把机会变成门框范围内的威胁。",
        },
        "secondary": [
            ("goals", {"en": "Goals", "zh": "进球"}),
            ("shots", {"en": "Shots", "zh": "射门"}),
        ],
    },
    {
        "id": "takeOns",
        "metric": "take_ons",
        "title": {"en": "Take-ons", "zh": "持球突破"},
        "metric_label": {"en": "Take-ons", "zh": "突破"},
        "description": {
            "en": "On-ball actions that beat or engaged defenders.",
            "zh": "持球直接挑战防守人的突破动作。",
        },
        "secondary": [
            ("ball_progressions", {"en": "Progressions", "zh": "推进球"}),
            ("progressive_line_breaks", {"en": "Progressive breaks", "zh": "推进打穿"}),
        ],
    },
    {
        "id": "ballProgressions",
        "metric": "ball_progressions",
        "title": {"en": "Ball Progressions", "zh": "推进球"},
        "metric_label": {"en": "Progressions", "zh": "推进"},
        "description": {
            "en": "Players who moved possession into more dangerous territory.",
            "zh": "把球权持续带到更有威胁区域的球员。",
        },
        "secondary": [
            ("progressive_line_breaks", {"en": "Progressive breaks", "zh": "推进打穿"}),
            ("take_ons", {"en": "Take-ons", "zh": "持球突破"}),
        ],
    },
    {
        "id": "progressiveLineBreaks",
        "metric": "progressive_line_breaks",
        "title": {"en": "Progressive Line Breaks", "zh": "推进型打穿防线"},
        "metric_label": {"en": "Breaks", "zh": "次数"},
        "description": {
            "en": "Line breaks created by carries or crosses, not raw pass volume.",
            "zh": "由带球推进或传中完成的打穿防线，不把普通传球堆量放在首位。",
        },
        "secondary": [
            ("line_break_ball_progression", {"en": "Carries", "zh": "带球"}),
            ("line_break_cross", {"en": "Crosses", "zh": "传中"}),
        ],
    },
    {
        "id": "completedCrosses",
        "metric": "crosses_completed",
        "title": {"en": "Completed Crosses", "zh": "成功传中"},
        "metric_label": {"en": "Completed", "zh": "成功"},
        "description": {
            "en": "Wide or final-third delivery that reached a teammate.",
            "zh": "边路或前场传中真正找到队友的次数。",
        },
        "secondary": [
            ("crosses_attempted", {"en": "Attempts", "zh": "尝试"}),
            ("progressive_line_breaks", {"en": "Progressive breaks", "zh": "推进打穿"}),
        ],
    },
    {
        "id": "defensiveStops",
        "metric": "defensive_stops",
        "title": {"en": "Defensive Stops", "zh": "防守阻断"},
        "metric_label": {"en": "Stops", "zh": "阻断"},
        "description": {
            "en": "Tackles won, interceptions and blocks in one defensive view.",
            "zh": "把成功抢断、拦截和封堵合在一起看防守存在感。",
        },
        "secondary": [
            ("tackles_won", {"en": "Tackles", "zh": "抢断"}),
            ("interceptions", {"en": "Interceptions", "zh": "拦截"}),
            ("blocks", {"en": "Blocks", "zh": "封堵"}),
        ],
    },
    {
        "id": "topSpeed",
        "metric": "top_speed_kmh",
        "title": {"en": "Top Speed", "zh": "最高速度"},
        "metric_label": {"en": "km/h", "zh": "km/h"},
        "description": {
            "en": "The fastest peak speed recorded in a match.",
            "zh": "单场比赛中被记录到的最高瞬时速度。",
        },
        "secondary": [
            ("sprints", {"en": "Sprints", "zh": "冲刺"}),
            ("high_speed_runs", {"en": "High-speed runs", "zh": "高速跑"}),
        ],
        "tie_breakers": ["sprints", "high_speed_runs", "total_distance_m"],
    },
    {
        "id": "distanceCovered",
        "metric": "total_distance_m",
        "title": {"en": "Distance Covered", "zh": "跑动距离"},
        "metric_label": {"en": "m", "zh": "米"},
        "description": {
            "en": "Total distance covered, best read with role and minutes in mind.",
            "zh": "全场跑动总距离，适合结合位置和出场时间一起看。",
        },
        "secondary": [
            ("high_speed_runs", {"en": "High-speed runs", "zh": "高速跑"}),
            ("sprints", {"en": "Sprints", "zh": "冲刺"}),
        ],
        "tie_breakers": ["high_speed_runs", "sprints", "top_speed_kmh"],
    },
    {
        "id": "sprints",
        "metric": "sprints",
        "title": {"en": "Sprints", "zh": "冲刺次数"},
        "metric_label": {"en": "Sprints", "zh": "冲刺"},
        "description": {
            "en": "Repeated high-intensity running actions.",
            "zh": "反复高速冲刺的身体输出。",
        },
        "secondary": [
            ("top_speed_kmh", {"en": "Top speed", "zh": "最高速度"}),
            ("total_distance_m", {"en": "Distance", "zh": "跑动距离"}),
        ],
        "tie_breakers": ["top_speed_kmh", "high_speed_runs", "total_distance_m"],
    },
]

METRIC_AGGREGATES = {
    "top_speed_kmh": "max",
}


def build_demo_site(
    db_path: str | Path,
    output_dir: str | Path,
    manifests_dir: str | Path = "manifests",
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests_path = Path(manifests_dir)
    latest_run = _load_json(manifests_path / "latest-run.json")
    update_events = _load_json(manifests_path / "update-events.json")
    latest_editorial = _load_json(out / "editorial" / "latest.json")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        coverage = _query(
            conn,
            """
            select
              count(*) as matches,
              (select count(*) from source_documents where active = 1) as active_sources,
              (select count(*) from shots) as shots,
              (select count(*) from player_appearances) as appearances,
              (select count(*) from player_physical_stats) as physical_rows
            from matches
            """,
        )
        matches = _query(
            conn,
            """
            select match_no, home_team, away_team, home_score, away_score, match_date
            from matches
            order by match_no
            """,
        )
        player_records = _query(
            conn,
            """
            with shot_totals as (
              select
                match_key,
                team,
                upper(player_name) as player_name,
                count(*) as shots,
                sum(is_on_target) as shots_on_target,
                sum(is_goal) as goals
              from shots
              group by match_key, team, upper(player_name)
            ),
            event_goals as (
              select
                match_key,
                team_name as team,
                upper(scorer_name) as player_name,
                count(*) as goals
              from goal_involvements
              group by match_key, team_name, upper(scorer_name)
            ),
            event_assists as (
              select
                match_key,
                team_name as team,
                upper(assister_name) as player_name,
                count(*) as assists
              from goal_involvements
              where assister_name is not null and assister_name != ''
              group by match_key, team_name, upper(assister_name)
            )
            select
              a.match_key,
              m.match_no,
              m.match_date,
              a.team,
              a.opponent,
              a.player_no,
              a.player_name,
              a.position,
              a.started,
              coalesce(s.shots, ip.attempts_at_goal, 0) as shots,
              coalesce(s.shots_on_target, 0) as shots_on_target,
              coalesce(eg.goals, s.goals, ip.goals, 0) as goals,
              coalesce(ea.assists, 0) as assists,
              coalesce(eg.goals, s.goals, ip.goals, 0) + coalesce(ea.assists, 0) as goal_involvements,
              coalesce(ip.passes_completed, 0) as passes_completed,
              coalesce(ip.crosses_attempted, 0) as crosses_attempted,
              coalesce(ip.crosses_completed, 0) as crosses_completed,
              coalesce(ip.line_breaks_completed, 0) as line_breaks_completed,
              coalesce(ip.ball_progressions, 0) as ball_progressions,
              coalesce(ip.take_ons, 0) as take_ons,
              coalesce(ip.step_ins, 0) as step_ins,
              coalesce(lb.distribution_ball_progression, 0) as line_break_ball_progression,
              coalesce(lb.distribution_cross, 0) as line_break_cross,
              coalesce(lb.distribution_pass, 0) as line_break_pass,
              coalesce(lb.distribution_ball_progression, 0) + coalesce(lb.distribution_cross, 0) as progressive_line_breaks,
              coalesce(o.total_offers, 0) as total_offers,
              coalesce(o.offers_received, 0) as offers_received,
              coalesce(o.in_behind, 0) as in_behind,
              coalesce(o.in_between, 0) as in_between,
              coalesce(da.tackles_won, 0) as tackles_won,
              coalesce(da.blocks, 0) as blocks,
              coalesce(da.interceptions, 0) as interceptions,
              coalesce(da.clearances, 0) as clearances,
              coalesce(da.tackles_won, 0) + coalesce(da.interceptions, 0) + coalesce(da.blocks, 0) as defensive_stops,
              coalesce(da.possession_regains, 0) as possession_regains,
              coalesce(da.possession_interrupted, 0) as possession_interrupted,
              coalesce(p.total_distance_m, 0) as total_distance_m,
              coalesce(p.high_speed_runs, 0) as high_speed_runs,
              coalesce(p.sprints, 0) as sprints,
              coalesce(p.top_speed_kmh, 0) as top_speed_kmh
            from player_appearances a
            join matches m on m.match_key = a.match_key
            left join player_in_possession_distributions ip
              on ip.match_key = a.match_key
             and ip.team = a.team
             and ip.player_no = a.player_no
            left join player_line_breaks lb
              on lb.match_key = a.match_key
             and lb.team = a.team
             and lb.player_no = a.player_no
            left join player_offers_receptions o
              on o.match_key = a.match_key
             and o.team = a.team
             and o.player_no = a.player_no
            left join player_defensive_actions da
              on da.match_key = a.match_key
             and da.team = a.team
             and da.player_no = a.player_no
            left join player_physical_stats p
              on p.match_key = a.match_key
             and p.team = a.team
             and p.player_no = a.player_no
            left join shot_totals s
              on s.match_key = a.match_key
             and s.team = a.team
             and s.player_name = upper(a.player_name)
            left join event_goals eg
              on eg.match_key = a.match_key
             and eg.team = a.team
             and eg.player_name = upper(a.player_name)
            left join event_assists ea
              on ea.match_key = a.match_key
             and ea.team = a.team
             and ea.player_name = upper(a.player_name)
            order by m.match_no, a.team, a.player_no
            """,
        )
    finally:
        conn.close()

    (out / "index.html").write_text(
        _page(
            coverage=coverage,
            latest_run=latest_run,
            update_events=update_events,
            latest_editorial=latest_editorial,
            latest_data_date=_latest_match_date(matches),
            matches=matches,
            leaderboard_payload=_leaderboard_payload(player_records),
        ),
        encoding="utf-8",
    )


def _query(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql))


def _latest_match_date(matches: list[sqlite3.Row]) -> str | None:
    dates = [str(match["match_date"]) for match in matches if match["match_date"]]
    return max(dates) if dates else None


def _page(
    *,
    coverage: list[sqlite3.Row],
    latest_run: dict[str, object],
    update_events: dict[str, object],
    latest_editorial: dict[str, object],
    latest_data_date: str | None,
    matches: list[sqlite3.Row],
    leaderboard_payload: dict[str, Any],
) -> str:
    leaderboard_json = _json_script(leaderboard_payload)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>FIFA PMSR Data Demo</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, "Noto Sans SC", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #16202a;
      background: #f4f6f8;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    body[data-lang="en"] [data-lang-panel="zh"], body[data-lang="zh"] [data-lang-panel="en"] {{ display: none; }}
    header {{ background: #ffffff; border-bottom: 1px solid #dbe2ea; }}
    .header-inner {{ max-width: 1220px; margin: 0 auto; padding: 24px 20px; display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }}
    main {{ max-width: 1220px; margin: 0 auto; padding: 24px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 46px); line-height: 1.05; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    p {{ margin: 0; color: #506073; line-height: 1.5; }}
    .eyebrow {{ margin-bottom: 6px; color: #0f766e; font-size: 12px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }}
    .lede {{ max-width: 760px; font-size: 16px; }}
    .language-toggle, .segmented {{ display: inline-flex; max-width: 100%; border: 1px solid #cfd9e5; border-radius: 8px; overflow: hidden; background: #f8fafc; }}
    #scope-controls {{ flex-wrap: wrap; overflow: visible; }}
    button {{ font: inherit; }}
    .language-toggle button, .segmented button {{ min-height: 38px; border: 0; border-right: 1px solid #cfd9e5; background: transparent; color: #425166; padding: 0 13px; cursor: pointer; }}
    .language-toggle button:last-child, .segmented button:last-child {{ border-right: 0; }}
    .language-toggle button.active, .segmented button.active {{ background: #17324d; color: #ffffff; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 16px; justify-content: space-between; align-items: flex-end; margin: 18px 0; }}
    .control-group {{ display: grid; min-width: 0; gap: 7px; }}
    .control-label {{ color: #5e6d80; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr)); gap: 16px; margin-top: 18px; }}
    .equal-height {{ align-items: stretch; }}
    .equal-height > .panel {{ display: flex; flex-direction: column; min-height: 100%; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ min-width: 0; border: 1px solid #e2e8f3; border-radius: 8px; padding: 12px; background: #f9fbfe; }}
    .metric .value {{ display: block; color: #162334; font-size: clamp(18px, 2vw, 24px); line-height: 1.15; font-weight: 700; overflow-wrap: anywhere; }}
    .metric .label {{ display: block; color: #526277; font-size: 12px; text-transform: uppercase; }}
    .summary {{ margin-bottom: 16px; }}
    .panel {{ min-width: 0; background: #ffffff; border: 1px solid #dde3ee; border-radius: 8px; padding: 18px; overflow-x: auto; }}
    .dashboard-shell {{ min-width: 0; background: #ffffff; border: 1px solid #dbe2ea; border-radius: 8px; padding: 20px; margin-bottom: 18px; overflow: hidden; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
    .leaderboard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 14px; }}
    .leaderboard-card {{ min-width: 0; border: 1px solid #dfe6ef; border-radius: 8px; background: #ffffff; min-height: 320px; overflow: hidden; }}
    .leaderboard-card header {{ border-bottom: 1px solid #e6ecf3; padding: 14px 15px; }}
    .leaderboard-card h3 {{ margin: 0; font-size: 16px; }}
    .leaderboard-card p {{ margin-top: 4px; font-size: 13px; }}
    .leaderboard-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    .leaderboard-table th:nth-child(1), .leaderboard-table td:nth-child(1) {{ width: 42px; text-align: center; }}
    .leaderboard-table th:nth-child(3), .leaderboard-table td:nth-child(3) {{ width: 86px; text-align: right; }}
    .rank {{ color: #64748b; font-weight: 800; }}
    .player-cell {{ min-width: 0; overflow-wrap: anywhere; }}
    .player-cell strong {{ display: block; color: #172033; font-size: 14px; line-height: 1.25; word-spacing: 2px; }}
    .player-cell span {{ display: block; color: #64748b; font-size: 12px; line-height: 1.3; margin-top: 3px; }}
    .value-cell strong {{ display: block; color: #0f766e; font-size: 20px; line-height: 1; }}
    .value-cell span {{ display: block; color: #64748b; font-size: 11px; margin-top: 3px; }}
    .secondary {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}
    .secondary span {{ border: 1px solid #e1e7ef; border-radius: 999px; color: #536579; font-size: 11px; padding: 2px 6px; }}
    .leaderboard-summary {{ margin: 10px 0 18px; color: #506073; font-size: 14px; }}
    .empty-state {{ padding: 22px 15px; color: #64748b; font-size: 14px; }}
    .editorial-card {{ display: grid; grid-template-columns: minmax(0, 1fr) 160px; gap: 16px; margin-top: 12px; }}
    .editorial-card h3 {{ font-size: 21px; margin: 2px 0 4px; }}
    .editorial-card .award {{ color: #59677c; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .editorial-card aside {{ border-left: 1px solid #e8edf5; padding-left: 16px; }}
    .editorial-card aside strong {{ display: block; font-size: 28px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .chips span {{ background: #edf2fa; border: 1px solid #dce5f2; border-radius: 999px; padding: 5px 9px; font-size: 12px; color: #35465d; }}
    .summary + .panel {{ margin-top: 16px; }}
    details.panel summary {{ cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    details.panel summary h2 {{ margin: 0; }}
    details.panel summary span {{ color: #526277; font-size: 13px; }}
    details.panel[open] summary {{ margin-bottom: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e8edf5; padding: 8px 6px; text-align: left; vertical-align: top; }}
    th {{ color: #516178; font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ background: #edf2fa; padding: 2px 5px; border-radius: 4px; }}
    @media (max-width: 640px) {{
      table {{ font-size: 12px; }}
      th, td {{ padding: 7px 5px; }}
      .header-inner, .section-head {{ display: block; }}
      .language-toggle {{ margin-top: 16px; }}
      .toolbar {{ gap: 12px; }}
      .control-group {{ width: 100%; }}
      .segmented {{ display: flex; width: 100%; }}
      .segmented button {{ flex: 1 1 0; min-width: 0; padding: 0 8px; }}
      .leaderboard-grid {{ grid-template-columns: 1fr; }}
      .leaderboard-table th:nth-child(1), .leaderboard-table td:nth-child(1) {{ width: 34px; }}
      .leaderboard-table th:nth-child(3), .leaderboard-table td:nth-child(3) {{ width: 74px; }}
      .editorial-card {{ grid-template-columns: 1fr; }}
      .editorial-card aside {{ border-left: 0; border-top: 1px solid #e8edf5; padding-left: 0; padding-top: 12px; }}
    }}
  </style>
</head>
<body data-lang="en">
  <header>
    <div class="header-inner">
      <div>
        <p class="eyebrow" data-i18n="hero.eyebrow">FIFA PMSR database</p>
        <h1 data-i18n="hero.title">Player-first World Cup data</h1>
        <p class="lede" data-i18n="hero.lede">Leaderboards built from FIFA Training Centre PMSR reports, with scopes for each active tournament phase and accumulated views.</p>
      </div>
      <div class="language-toggle" aria-label="Language">
        <button type="button" data-lang-button="en">EN</button>
        <button type="button" data-lang-button="zh">中文</button>
      </div>
    </div>
  </header>
  <main>
    <section class="dashboard-shell" aria-labelledby="leaderboard-title">
      <div class="section-head">
        <div>
          <p class="eyebrow" data-i18n="leaderboards.eyebrow">Player Leaderboards</p>
          <h2 id="leaderboard-title" data-i18n="leaderboards.title">Player Leaderboards</h2>
          <p data-i18n="leaderboards.copy">Switch between matchday peaks and accumulated totals. Phase filters appear as soon as that part of the tournament has data.</p>
        </div>
      </div>
      <div class="toolbar">
        <div class="control-group">
          <span class="control-label" data-i18n="controls.scope">Scope</span>
          <div class="segmented" id="scope-controls" aria-label="Scope">{_scope_buttons_html(leaderboard_payload["scopes"])}</div>
        </div>
        <div class="control-group">
          <span class="control-label" data-i18n="controls.mode">Mode</span>
          <div class="segmented" id="mode-controls" aria-label="Mode">
            <button type="button" data-mode="single">Single-match peak</button>
            <button type="button" data-mode="accumulated">Accumulated</button>
          </div>
        </div>
      </div>
      <p class="leaderboard-summary" id="leaderboard-summary"></p>
      <div class="leaderboard-grid" id="leaderboard-grid"></div>
    </section>
    <section class="summary">
      <h2>Update Summary</h2>
      {_coverage_metrics(coverage, latest_run)}
      <div class="grid">
        <details class="panel collapsible">
          <summary><h2>New Matches</h2><span>{_row_count(update_events.get("new_matches", []))} rows</span></summary>
          {_table(update_events.get("new_matches", []))}
        </details>
        <section class="panel">
          <h3>Version Updates</h3>
          {_table(update_events.get("version_updates", []))}
        </section>
        <section class="panel">
          <h3>Failures</h3>
          {_table(latest_run.get("failures", []))}
        </section>
      </div>
    </section>
    {_editorial_section(latest_editorial, latest_data_date=latest_data_date)}
    <details class="panel collapsible">
      <summary><h2>Loaded Matches</h2><span>{len(matches)} rows</span></summary>
      {_table(matches)}
    </details>
  </main>
  <script id="leaderboard-data" type="application/json">{leaderboard_json}</script>
  <script>
    const DATA = JSON.parse(document.getElementById("leaderboard-data").textContent);
    const I18N = {{
      en: {{
        "hero.eyebrow": "FIFA PMSR database",
        "hero.title": "Player-first World Cup data",
        "hero.lede": "Leaderboards built from FIFA Training Centre PMSR reports, with scopes for each active tournament phase and accumulated views.",
        "leaderboards.eyebrow": "Player Leaderboards",
        "leaderboards.title": "Player Leaderboards",
        "leaderboards.copy": "Switch between matchday peaks and accumulated totals. Phase filters appear as soon as that part of the tournament has data.",
        "controls.scope": "Scope",
        "controls.mode": "Mode",
        "modes.single": "Single-match peak",
        "modes.accumulated": "Accumulated",
        "table.rank": "Rank",
        "table.player": "Player",
        "table.value": "Value",
        "empty": "No player rows for this scope yet.",
        "summary": "{{scope}} · {{mode}} · {{matches}} matches loaded"
      }},
      zh: {{
        "hero.eyebrow": "FIFA PMSR 数据库",
        "hero.title": "以球员为中心的世界杯数据",
        "hero.lede": "基于 FIFA Training Centre PMSR 报告生成榜单，按已经有数据的赛事阶段和累计视角切换。",
        "leaderboards.eyebrow": "球员榜单",
        "leaderboards.title": "球员榜单",
        "leaderboards.copy": "在单场峰值和累计数据之间切换；某个赛事阶段有数据后，对应筛选会自动出现。",
        "controls.scope": "范围",
        "controls.mode": "模式",
        "modes.single": "单场峰值",
        "modes.accumulated": "累计",
        "table.rank": "排名",
        "table.player": "球员",
        "table.value": "数值",
        "empty": "这个范围还没有球员数据。",
        "summary": "{{scope}} · {{mode}} · 已载入 {{matches}} 场"
      }}
    }};
    const state = {{
      lang: localStorage.getItem("footballDataLang") || "en",
      scope: DATA.scopes[0]?.id || "overall",
      mode: "single"
    }};
    function tr(key) {{ return I18N[state.lang][key] || I18N.en[key] || key; }}
    function label(value) {{ return value[state.lang] || value.en || ""; }}
    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }}[char]));
    }}
    function setLanguage(lang) {{
      state.lang = lang;
      localStorage.setItem("footballDataLang", lang);
      document.documentElement.lang = lang === "zh" ? "zh-Hans" : "en";
      document.body.dataset.lang = lang;
      document.querySelectorAll("[data-i18n]").forEach(node => node.textContent = tr(node.dataset.i18n));
      document.querySelectorAll("[data-lang-button]").forEach(button => button.classList.toggle("active", button.dataset.langButton === lang));
      document.querySelector('[data-mode="single"]').textContent = tr("modes.single");
      document.querySelector('[data-mode="accumulated"]').textContent = tr("modes.accumulated");
      renderScopes();
      renderLeaderboards();
    }}
    function renderScopes() {{
      document.getElementById("scope-controls").innerHTML = DATA.scopes.map(scope =>
        `<button type="button" data-scope="${{scope.id}}" class="${{scope.id === state.scope ? "active" : ""}}">${{escapeHtml(label(scope.short))}}</button>`
      ).join("");
      document.querySelectorAll("[data-scope]").forEach(button => {{
        button.addEventListener("click", () => {{ state.scope = button.dataset.scope; renderScopes(); renderLeaderboards(); }});
      }});
    }}
    function renderLeaderboards() {{
      document.querySelectorAll("[data-mode]").forEach(button => button.classList.toggle("active", button.dataset.mode === state.mode));
      const scope = DATA.scopes.find(item => item.id === state.scope) || DATA.scopes[0];
      state.scope = scope.id;
      const modeLabel = tr(`modes.${{state.mode}}`);
      document.getElementById("leaderboard-summary").textContent = tr("summary")
        .replace("{{scope}}", label(scope.label))
        .replace("{{mode}}", modeLabel)
        .replace("{{matches}}", scope.match_count);
      const grid = document.getElementById("leaderboard-grid");
      const boards = DATA.leaderboards[state.scope][state.mode];
      grid.innerHTML = DATA.categories.map(category => renderCard(category, boards[category.id] || [])).join("");
    }}
    function renderCard(category, rows) {{
      const body = rows.length ? `
        <table class="leaderboard-table">
          <thead><tr><th>${{tr("table.rank")}}</th><th>${{tr("table.player")}}</th><th>${{tr("table.value")}}</th></tr></thead>
          <tbody>${{rows.map(row => renderRow(category, row)).join("")}}</tbody>
        </table>` : `<div class="empty-state">${{tr("empty")}}</div>`;
      return `<article class="leaderboard-card">
        <header><h3>${{escapeHtml(label(category.title))}}</h3><p>${{escapeHtml(label(category.description))}}</p></header>
        ${{body}}
      </article>`;
    }}
    function renderRow(category, row) {{
      const secondary = row.secondary.map(item =>
        `<span>${{escapeHtml(label(item.label))}} ${{escapeHtml(item.value)}}</span>`
      ).join("");
      return `<tr>
        <td class="rank">${{row.rank}}</td>
        <td class="player-cell"><strong>${{escapeHtml(row.player)}}</strong><span>${{escapeHtml(label(row.context))}}</span><div class="secondary">${{secondary}}</div></td>
        <td class="value-cell"><strong>${{escapeHtml(row.value)}}</strong><span>${{escapeHtml(label(category.metric_label))}}</span></td>
      </tr>`;
    }}
    document.querySelectorAll("[data-lang-button]").forEach(button => {{
      button.addEventListener("click", () => setLanguage(button.dataset.langButton));
    }});
    document.querySelectorAll("[data-mode]").forEach(button => {{
      button.addEventListener("click", () => {{ state.mode = button.dataset.mode; renderLeaderboards(); }});
    }});
    setLanguage(state.lang);
  </script>
</body>
</html>
"""


def _leaderboard_payload(rows: list[sqlite3.Row]) -> dict[str, Any]:
    records = [_record_from_row(row) for row in rows]
    scopes = _active_scope_payloads(records)
    leaderboards: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    scope_by_id = {scope["id"]: scope for scope in SCOPE_SPECS}
    for scope_payload in scopes:
        scope = scope_by_id[scope_payload["id"]]
        scoped_records = _records_for_scope(records, scope)
        leaderboards[scope["id"]] = {
            "single": _category_boards(scoped_records, mode="single"),
            "accumulated": _category_boards(scoped_records, mode="accumulated"),
        }
    return {
        "scopes": scopes,
        "categories": [
            {
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "metric_label": spec["metric_label"],
            }
            for spec in CATEGORY_SPECS
        ],
        "leaderboards": leaderboards,
    }


def _scope_buttons_html(scopes: list[dict[str, Any]]) -> str:
    first_scope_id = scopes[0]["id"] if scopes else ""
    return "".join(
        (
            f'<button type="button" data-scope="{html.escape(scope["id"])}"'
            f' class="{"active" if scope["id"] == first_scope_id else ""}">'
            f'{html.escape(scope["short"]["en"])}</button>'
        )
        for scope in scopes
    )


def _record_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _scope_payload(scope: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    scoped_records = _records_for_scope(records, scope)
    return {
        "id": scope["id"],
        "label": scope["label"],
        "short": scope["short"],
        "match_count": len({record["match_key"] for record in scoped_records}),
        "player_count": len(scoped_records),
    }


def _active_scope_payloads(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads = [_scope_payload(scope, records) for scope in SCOPE_SPECS]
    return [
        payload
        for payload in payloads
        if payload["id"] == "overall" or int(payload["match_count"]) > 0
    ]


def _records_for_scope(
    records: list[dict[str, Any]],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    match_min = scope["match_min"]
    match_max = scope["match_max"]
    if match_min is None or match_max is None:
        return records
    return [
        record
        for record in records
        if int(match_min) <= int(record["match_no"]) <= int(match_max)
    ]


def _category_boards(records: list[dict[str, Any]], *, mode: str) -> dict[str, list[dict[str, Any]]]:
    board_records = records if mode == "single" else _accumulated_records(records)
    boards: dict[str, list[dict[str, Any]]] = {}
    for spec in CATEGORY_SPECS:
        metric = spec["metric"]
        ranked = [
            record
            for record in board_records
            if _numeric(record.get(metric)) > 0
        ]
        ranked.sort(key=lambda record, spec=spec: _leaderboard_sort_key(record, spec), reverse=True)
        boards[spec["id"]] = [
            _leaderboard_row(record, spec, rank=index, mode=mode)
            for index, record in enumerate(ranked[:5], start=1)
        ]
    return boards


def _accumulated_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    metric_names = _leaderboard_metric_names()
    for record in records:
        key = (str(record["team"]), str(record["player_name"]))
        aggregate = grouped.setdefault(
            key,
            {
                "team": record["team"],
                "player_name": record["player_name"],
                "player_no": record["player_no"],
                "position": record["position"],
                "matches": set(),
                "opponents": [],
            },
        )
        aggregate["matches"].add(record["match_key"])
        aggregate["opponents"].append(record["opponent"])
        for metric in metric_names:
            aggregate[metric] = _accumulate_metric(metric, aggregate.get(metric), record.get(metric))
    results: list[dict[str, Any]] = []
    for aggregate in grouped.values():
        aggregate["match_count"] = len(aggregate.pop("matches"))
        results.append(aggregate)
    return results


def _secondary_metric_names() -> set[str]:
    names: set[str] = set()
    for spec in CATEGORY_SPECS:
        for metric, _label in spec["secondary"]:
            names.add(metric)
    return names


def _leaderboard_metric_names() -> set[str]:
    return {str(spec["metric"]) for spec in CATEGORY_SPECS} | _secondary_metric_names()


def _leaderboard_sort_key(record: dict[str, Any], spec: dict[str, Any]) -> tuple[float, ...]:
    metrics = [str(spec["metric"])] + [
        str(metric)
        for metric in spec.get(
            "tie_breakers",
            ["goals", "shots_on_target", "line_breaks_completed", "possession_regains"],
        )
    ]
    return tuple(_numeric(record.get(metric)) for metric in metrics)


def _accumulate_metric(metric: str, current: object, value: object) -> float:
    current_number = _numeric(current)
    next_number = _numeric(value)
    if METRIC_AGGREGATES.get(metric) == "max":
        return max(current_number, next_number)
    return current_number + next_number


def _leaderboard_row(
    record: dict[str, Any],
    spec: dict[str, Any],
    *,
    rank: int,
    mode: str,
) -> dict[str, Any]:
    metric = spec["metric"]
    context = _row_context(record, mode=mode)
    return {
        "rank": rank,
        "player": format_player(record.get("player_name"), record.get("team")),
        "team": format_team(record.get("team")),
        "value": _format_leaderboard_value(record.get(metric), metric=metric),
        "context": context,
        "secondary": [
            {
                "label": label,
                "value": _format_leaderboard_value(record.get(metric_name), metric=metric_name),
            }
            for metric_name, label in spec["secondary"]
        ],
    }


def _row_context(record: dict[str, Any], *, mode: str) -> dict[str, str]:
    if mode == "accumulated":
        matches = int(_numeric(record.get("match_count")))
        return {
            "en": f"{format_team(record.get('team'))} · {matches} matches",
            "zh": f"{format_team(record.get('team'))} · {matches} 场",
        }
    return {
        "en": (
            f"{format_team(record.get('team'))} vs {format_team(record.get('opponent'))}"
            f" · Match {record.get('match_no')}"
        ),
        "zh": (
            f"{format_team(record.get('team'))} vs {format_team(record.get('opponent'))}"
            f" · 第 {record.get('match_no')} 场"
        ),
    }


def _format_leaderboard_value(value: object, *, metric: str | None = None) -> str:
    numeric = _numeric(value)
    if metric == "total_distance_m":
        return f"{numeric:,.0f}"
    if metric == "top_speed_kmh":
        return f"{numeric:.1f}"
    return str(int(numeric)) if numeric == int(numeric) else f"{numeric:.1f}"


def _numeric(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _json_script(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _coverage_metrics(rows: list[sqlite3.Row], latest_run: dict[str, object]) -> str:
    row = rows[0] if rows else {}
    metrics = [
        ("Matches", _value(row, "matches")),
        ("Active PMSR", _value(row, "active_sources")),
        ("Shots", _value(row, "shots")),
        ("Appearances", _value(row, "appearances")),
        ("Physical Rows", _value(row, "physical_rows")),
        ("Run Status", latest_run.get("status", "")),
        ("Generated At", latest_run.get("generated_at", "")),
    ]
    return (
        '<div class="metrics">'
        + "".join(
            '<div class="metric">'
            f'<span class="value">{html.escape(_format_value(value))}</span>'
            f'<span class="label">{html.escape(label)}</span>'
            "</div>"
            for label, value in metrics
        )
        + "</div>"
    )


def _editorial_section(report: dict[str, object], *, latest_data_date: str | None) -> str:
    report_date = str(report.get("match_date") or "") if report else ""
    if latest_data_date and report_date != latest_data_date:
        latest_label = html.escape(latest_data_date, quote=False)
        published_label = html.escape(report_date or "none", quote=False)
        return (
            '<section class="summary">'
            '<h2><span data-lang-panel="en">Editor\'s Choices</span><span data-lang-panel="zh">编辑精选</span></h2>'
            f'<p data-lang-panel="en">Latest data is {latest_label}. Editorial for that match day has not been published yet. Last published: {published_label}. <a href="editorial/">Open archive</a>.</p>'
            f'<p data-lang-panel="zh">最新数据日是 {latest_label}，当天编辑精选尚未发布。最近已发布：{published_label}。<a href="editorial/">查看归档</a>。</p>'
            "</section>"
        )
    choices = report.get("choices")
    if not isinstance(choices, list) or not choices:
        return (
            '<section class="summary">'
            '<h2><span data-lang-panel="en">Editor\'s Choices</span><span data-lang-panel="zh">编辑精选</span></h2>'
            '<p data-lang-panel="en"><a href="editorial/">Open the editorial archive</a>.</p>'
            '<p data-lang-panel="zh"><a href="editorial/">查看编辑精选归档</a>。</p>'
            "</section>"
        )
    cards = []
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        en_chip_html = _chip_html(_nested_value(choice, "evidence_chips", "en"))
        zh_chip_html = _chip_html(_nested_value(choice, "evidence_chips", "zh"))
        cards.append(
            '<article class="panel editorial-card">'
            "<div>"
            f'{_editorial_language_block(choice, "en")}'
            f'{_editorial_language_block(choice, "zh")}'
            "</div>"
            "<aside>"
            f'<div class="chips" data-lang-panel="en">{en_chip_html}</div>'
            f'<div class="chips" data-lang-panel="zh">{zh_chip_html}</div>'
            "</aside>"
            "</article>"
        )
    match_date = html.escape(_format_value(report.get("match_date")), quote=False)
    return (
        '<section class="summary">'
        '<h2><span data-lang-panel="en">Editor\'s Choices</span><span data-lang-panel="zh">编辑精选</span></h2>'
        f'<p data-lang-panel="en">Latest editorial picks for local match day {match_date}. <a href="editorial/">Open archive</a>.</p>'
        f'<p data-lang-panel="zh">当前最新比赛日 {match_date} 的编辑精选。<a href="editorial/">查看归档</a>。</p>'
        + "".join(cards)
        + "</section>"
    )


def _editorial_language_block(choice: Mapping[str, object], lang: str) -> str:
    label = _nested_value(choice, "award_label", lang)
    title = _editorial_title(choice, lang)
    body_html = _editorial_body_html(choice, lang)
    match_label = "Match" if lang == "en" else "第"
    match_suffix = "" if lang == "en" else " 场"
    return (
        f'<div data-lang-panel="{lang}">'
        f'<span class="award">{html.escape(_format_value(label), quote=False)}</span>'
        f"<h3>{html.escape(format_player(choice.get('player_name'), choice.get('team')), quote=False)}</h3>"
        f"<p>{html.escape(format_team(choice.get('team')), quote=False)} vs "
        f"{html.escape(format_team(choice.get('opponent')), quote=False)}"
        f" · {match_label} {html.escape(_format_value(choice.get('match_no')), quote=False)}{match_suffix}</p>"
        f"<h3>{html.escape(_format_value(title), quote=False)}</h3>"
        f"{body_html}"
        "</div>"
    )


def _chip_html(chips: object) -> str:
    if not isinstance(chips, list):
        return ""
    return "".join(
        f"<span>{html.escape(_format_value(chip), quote=False)}</span>"
        for chip in chips[:4]
    )


def _editorial_title(choice: Mapping[str, object], lang: str) -> object:
    return _nested_value(choice, "content", lang, "title") or _nested_value(
        choice,
        "narrative",
        lang,
        "title",
    )


def _editorial_body_html(choice: Mapping[str, object], lang: str) -> str:
    content_html = _nested_value(choice, "content", lang, "html")
    if content_html:
        return _format_value(content_html)
    body = _nested_value(choice, "narrative", lang, "body")
    return f"<p>{html.escape(_format_value(body), quote=False)}</p>"


def _table(rows: object) -> str:
    if not rows:
        return "<p>No rows.</p>"
    rows = list(rows)  # type: ignore[arg-type]
    headers = [header for header in rows[0].keys() if header != "Score"]
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(_format_table_cell(row, header))}</td>" for header in headers
            )
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_table_cell(row: object, header: str) -> str:
    value = _value(row, header)
    if header in {"Player", "player_name"}:
        return format_player(value, _row_team(row))
    if header in {"Team", "team", "home_team", "away_team"}:
        return format_team(value)
    return _format_value(value)


def _row_team(row: object) -> object:
    return _value(row, "Team") or _value(row, "team")


def _row_count(rows: object) -> int:
    if not rows:
        return 0
    return len(list(rows))  # type: ignore[arg-type]


def _value(row: object, key: str) -> object:
    if isinstance(row, sqlite3.Row):
        return row[key]
    if isinstance(row, Mapping):
        return row.get(key)
    return ""


def _nested_value(row: object, *keys: str) -> object:
    value: object = row
    for key in keys:
        if isinstance(value, Mapping):
            value = value.get(key)
        else:
            return ""
    return value


def _format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}" if value >= 10 else f"{value:.2f}"
    return str(value)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
