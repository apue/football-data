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
              (select count(*) from player_physical_stats) as player_rows
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
            select player_name, team, total_distance_m
            from player_physical_stats
            where total_distance_m is not null
            order by total_distance_m desc
            limit 5
            """,
        )
        shots = _query(
            conn,
            """
            select m.match_no, s.team, s.minute, s.player_name, s.outcome, s.delivery_type
            from shots s
            join matches m using(match_key)
            where s.is_goal = 1 or s.is_on_target = 1
            order by m.match_no, s.minute
            limit 20
            """,
        )
    finally:
        conn.close()

    (out / "index.html").write_text(
        _page(
            coverage=coverage,
            latest_run=latest_run,
            update_events=update_events,
            matches=matches,
            fastest=fastest,
            distance=distance,
            shots=shots,
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
    matches: list[sqlite3.Row],
    fastest: list[sqlite3.Row],
    distance: list[sqlite3.Row],
    shots: list[sqlite3.Row],
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
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
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ border: 1px solid #e2e8f3; border-radius: 8px; padding: 12px; background: #f9fbfe; }}
    .metric .value {{ display: block; color: #162334; font-size: 24px; font-weight: 700; }}
    .metric .label {{ display: block; color: #526277; font-size: 12px; text-transform: uppercase; }}
    section {{ background: #ffffff; border: 1px solid #dde3ee; border-radius: 8px; padding: 18px; }}
    section + section {{ margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e8edf5; padding: 8px 6px; text-align: left; vertical-align: top; }}
    th {{ color: #516178; font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ background: #edf2fa; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <header>
    <h1>FIFA PMSR Data Demo</h1>
    <p>Generated from <code>data/latest.sqlite</code>. Original PMSR reports are attributed to FIFA Training Centre.</p>
  </header>
  <main>
    <section>
      <h2>Update Summary</h2>
      {_coverage_metrics(coverage, latest_run)}
      <div class="grid">
        <div>
          <h3>New Matches</h3>
          {_table(update_events.get("new_matches", []))}
        </div>
        <div>
          <h3>Version Updates</h3>
          {_table(update_events.get("version_updates", []))}
        </div>
        <div>
          <h3>Failures</h3>
          {_table(latest_run.get("failures", []))}
        </div>
      </div>
    </section>
    <section>
      <h2>Loaded Matches</h2>
      {_table(matches)}
    </section>
    <div class="grid">
      <section>
        <h2>Top 5 Fastest Players</h2>
        {_table(fastest)}
      </section>
      <section>
        <h2>Top 5 Total Distance</h2>
        {_table(distance)}
      </section>
    </div>
    <section>
      <h2>Goals and On-Target Shots</h2>
      {_table(shots)}
    </section>
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
        ("Player Rows", _value(row, "player_rows")),
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


def _value(row: object, key: str) -> object:
    if isinstance(row, sqlite3.Row):
        return row[key]
    if isinstance(row, Mapping):
        return row.get(key)
    return ""


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
