from __future__ import annotations

import html
import sqlite3
from pathlib import Path


def build_demo_site(db_path: str | Path, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
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
        _page(matches=matches, fastest=fastest, distance=distance, shots=shots),
        encoding="utf-8",
    )


def _query(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql))


def _page(
    *,
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
    p {{ margin: 0; color: #4b5b70; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; margin-top: 18px; }}
    section {{ background: #ffffff; border: 1px solid #dde3ee; border-radius: 8px; padding: 18px; }}
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
    <section style="margin-top:16px">
      <h2>Goals and On-Target Shots</h2>
      {_table(shots)}
    </section>
  </main>
</body>
</html>
"""


def _table(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    headers = rows[0].keys()
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(_format_value(row[header]))}</td>" for header in headers
            )
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}" if value >= 10 else f"{value:.2f}"
    return str(value)

