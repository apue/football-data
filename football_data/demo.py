from __future__ import annotations

import html
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path


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
        fastest = _query(
            conn,
            """
            select player_name, team, top_speed_kmh
            from player_physical_stats
            where top_speed_kmh is not null
            order by top_speed_kmh desc
            limit 5
            """,
        )
        distance = _query(
            conn,
            """
            select player_name as Player, team as Team, total_distance_m as "Distance (m)"
            from player_physical_stats
            where total_distance_m is not null
            order by total_distance_m desc
            limit 5
            """,
        )
        attacking_threats = _query(
            conn,
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
              m.match_no as Match,
              a.player_name as Player,
              a.team as Team,
              a.position as Pos,
              round(
                coalesce(s.goals, 0) * 6.0
                + coalesce(s.on_target, 0) * 2.0
                + coalesce(d.attempts_at_goal, 0) * 1.0
                + coalesce(o.offers_received, 0) * 0.20
                + coalesce(o.in_behind, 0) * 0.25,
                1
              ) as Score,
              coalesce(s.shots, d.attempts_at_goal, 0) as Shots,
              coalesce(s.on_target, 0) as "On Target",
              coalesce(o.offers_received, 0) as Received,
              coalesce(o.in_behind, 0) as "In Behind"
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
            left join shot_totals s
              on s.match_key = a.match_key
             and s.team = a.team
             and s.player_name = upper(a.player_name)
            where Score > 0
            order by Score desc, Shots desc
            limit 5
            """,
        )
        progressors = _query(
            conn,
            """
            select
              m.match_no as Match,
              d.player_name as Player,
              d.team as Team,
              round(
                coalesce(d.line_breaks_completed, 0) * 2.0
                + coalesce(d.ball_progressions, 0) * 1.0
                + coalesce(d.take_ons, 0) * 0.5
                + coalesce(d.step_ins, 0) * 0.5
                + coalesce(d.passes_completed, 0) * 0.02,
                1
              ) as Score,
              d.line_breaks_completed as "Line Breaks",
              d.ball_progressions as Progressions,
              d.take_ons as "Take Ons"
            from player_in_possession_distributions d
            join matches m using(match_key)
            where Score > 0
            order by Score desc, "Line Breaks" desc
            limit 5
            """,
        )
        off_ball_receivers = _query(
            conn,
            """
            select
              m.match_no as Match,
              o.player_name as Player,
              o.team as Team,
              round(
                coalesce(o.offers_received, 0) * 1.0
                + coalesce(o.in_behind, 0) * 0.6
                + coalesce(o.in_between, 0) * 0.4
                + coalesce(o.total_offers, 0) * 0.1,
                1
              ) as Score,
              o.total_offers as Offers,
              o.offers_received as Received,
              o.in_behind as "In Behind",
              o.in_between as "Between Lines"
            from player_offers_receptions o
            join matches m using(match_key)
            where Score > 0
            order by Score desc, Received desc
            limit 5
            """,
        )
        defensive_contributors = _query(
            conn,
            """
            select
              m.match_no as Match,
              d.player_name as Player,
              d.team as Team,
              round(
                coalesce(d.tackles_won, 0) * 1.5
                + coalesce(d.interceptions, 0) * 1.5
                + coalesce(d.blocks, 0) * 1.0
                + coalesce(d.possession_regains, 0) * 1.3
                + coalesce(d.possession_interrupted, 0) * 1.0
                + coalesce(d.pressing_direct, 0) * 0.3
                + coalesce(d.pressing_indirect, 0) * 0.05
                + coalesce(d.clearances, 0) * 0.5,
                1
              ) as Score,
              d.tackles_won as "Tackles Won",
              d.interceptions as Interceptions,
              d.possession_regains as Regains,
              d.possession_interrupted as Interrupted
            from player_defensive_actions d
            join matches m using(match_key)
            where Score > 0
            order by Score desc, Regains desc
            limit 5
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
            matches=matches,
            fastest=fastest,
            distance=distance,
            attacking_threats=attacking_threats,
            progressors=progressors,
            off_ball_receivers=off_ball_receivers,
            defensive_contributors=defensive_contributors,
        ),
        encoding="utf-8",
    )


def _query(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql))


def _page(
    *,
    coverage: list[sqlite3.Row],
    latest_run: dict[str, object],
    update_events: dict[str, object],
    latest_editorial: dict[str, object],
    matches: list[sqlite3.Row],
    fastest: list[sqlite3.Row],
    distance: list[sqlite3.Row],
    attacking_threats: list[sqlite3.Row],
    progressors: list[sqlite3.Row],
    off_ball_receivers: list[sqlite3.Row],
    defensive_contributors: list[sqlite3.Row],
) -> str:
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
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17202a;
      background: #f5f7fb;
    }}
    body {{ margin: 0; }}
    header {{ background: #ffffff; border-bottom: 1px solid #dde3ee; padding: 28px 32px; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin: 0 0 14px; font-size: 19px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    p {{ margin: 0; color: #4b5b70; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; margin-top: 18px; }}
    .equal-height {{ align-items: stretch; }}
    .equal-height > .panel {{ display: flex; flex-direction: column; min-height: 100%; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ border: 1px solid #e2e8f3; border-radius: 8px; padding: 12px; background: #f9fbfe; }}
    .metric .value {{ display: block; color: #162334; font-size: 24px; font-weight: 700; }}
    .metric .label {{ display: block; color: #526277; font-size: 12px; text-transform: uppercase; }}
    .summary {{ margin-bottom: 16px; }}
    .panel {{ background: #ffffff; border: 1px solid #dde3ee; border-radius: 8px; padding: 18px; overflow-x: auto; }}
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
      .editorial-card {{ grid-template-columns: 1fr; }}
      .editorial-card aside {{ border-left: 0; border-top: 1px solid #e8edf5; padding-left: 0; padding-top: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>FIFA PMSR Data Demo</h1>
    <p>Generated from <code>data/latest.sqlite</code>. Original PMSR reports are attributed to FIFA Training Centre.</p>
  </header>
  <main>
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
    {_editorial_section(latest_editorial)}
    <details class="panel collapsible">
      <summary><h2>Loaded Matches</h2><span>{len(matches)} rows</span></summary>
      {_table(matches)}
    </details>
    <div class="grid equal-height">
      <section class="panel">
        <h2>Top 5 Fastest Players</h2>
        {_table(fastest)}
      </section>
      <section class="panel">
        <h2>Top 5 Total Distance</h2>
        {_table(distance)}
      </section>
    </div>
    <div class="grid equal-height">
      <section class="panel">
        <h2>Top 5 Attacking Threats</h2>
        {_table(attacking_threats)}
      </section>
      <section class="panel">
        <h2>Top 5 Progressors</h2>
        {_table(progressors)}
      </section>
    </div>
    <div class="grid equal-height">
      <section class="panel">
        <h2>Top 5 Off-Ball Receivers</h2>
        {_table(off_ball_receivers)}
      </section>
      <section class="panel">
        <h2>Top 5 Defensive Contributors</h2>
        {_table(defensive_contributors)}
      </section>
    </div>
  </main>
</body>
</html>
"""


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


def _editorial_section(report: dict[str, object]) -> str:
    choices = report.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    cards = []
    for choice in choices[:3]:
        if not isinstance(choice, Mapping):
            continue
        label = _nested_value(choice, "award_label", "en")
        title = _nested_value(choice, "narrative", "en", "title")
        body = _nested_value(choice, "narrative", "en", "body")
        zh_title = _nested_value(choice, "narrative", "zh", "title")
        zh_body = _nested_value(choice, "narrative", "zh", "body")
        chips = _nested_value(choice, "evidence_chips", "en")
        if isinstance(chips, list):
            chip_html = "".join(
                f"<span>{html.escape(_format_value(chip), quote=False)}</span>"
                for chip in chips[:4]
            )
        else:
            chip_html = ""
        cards.append(
            '<article class="panel editorial-card">'
            "<div>"
            f'<span class="award">{html.escape(_format_value(label), quote=False)}</span>'
            f"<h3>{html.escape(_format_value(choice.get('player_name')), quote=False)}</h3>"
            f"<p>{html.escape(_format_value(choice.get('team')), quote=False)} vs "
            f"{html.escape(_format_value(choice.get('opponent')), quote=False)}"
            f" · Match {html.escape(_format_value(choice.get('match_no')), quote=False)}</p>"
            f"<h3>{html.escape(_format_value(title), quote=False)}</h3>"
            f"<p>{html.escape(_format_value(body), quote=False)}</p>"
            f"<h3>{html.escape(_format_value(zh_title), quote=False)}</h3>"
            f"<p>{html.escape(_format_value(zh_body), quote=False)}</p>"
            "</div>"
            "<aside>"
            f"<strong>{html.escape(_format_value(choice.get('score')), quote=False)}</strong>"
            "<span>score</span>"
            f'<div class="chips">{chip_html}</div>'
            "</aside>"
            "</article>"
        )
    match_date = html.escape(_format_value(report.get("match_date")), quote=False)
    return (
        '<section class="summary">'
        f"<h2>Editor's Choices</h2>"
        f"<p>Latest editorial picks for local match day {match_date}.</p>"
        + "".join(cards)
        + "</section>"
    )


def _table(rows: object) -> str:
    if not rows:
        return "<p>No rows.</p>"
    rows = list(rows)  # type: ignore[arg-type]
    headers = rows[0].keys()
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(_format_value(_value(row, header)))}</td>" for header in headers
            )
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


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
