import sqlite3
from pathlib import Path

from football_data.database import build_database
from football_data.extract import extract_pdf


RAW_DIR = Path(__file__).resolve().parents[1] / "raw"


def _pdf(pattern: str) -> Path:
    matches = sorted(RAW_DIR.glob(f"**/{pattern}"))
    assert matches, f"No PDF fixture found for {pattern}"
    return matches[-1]


def test_build_database_loads_matches_shots_and_physical_rows(tmp_path):
    db_path = tmp_path / "latest.sqlite"
    records = [
        extract_pdf(_pdf("PMSR-M01*.pdf")),
        extract_pdf(_pdf("PMSR-M02*.pdf")),
        extract_pdf(_pdf("PMSR-M07*.pdf")),
        extract_pdf(_pdf("PMSR-M25*.pdf")),
    ]

    build_database(db_path, records)

    conn = sqlite3.connect(db_path)
    try:
        match_count = conn.execute("select count(*) from matches").fetchone()[0]
        shot_count = conn.execute("select count(*) from shots").fetchone()[0]
        physical_count = conn.execute("select count(*) from player_physical_stats").fetchone()[0]
        appearance_count = conn.execute("select count(*) from player_appearances").fetchone()[0]
        offer_count = conn.execute("select count(*) from player_offers_receptions").fetchone()[0]
        defensive_count = conn.execute("select count(*) from player_defensive_actions").fetchone()[0]
        detailed_line_break_count = conn.execute(
            "select count(*) from player_line_breaks"
        ).fetchone()[0]
        source_columns = {
            row[1] for row in conn.execute("pragma table_info(source_documents)").fetchall()
        }
        shot_columns = {row[1] for row in conn.execute("pragma table_info(shots)").fetchall()}
        brazil_source = conn.execute(
            """
            select source_id, report_type, match_no, home_code, away_code, version, active
            from source_documents
            where match_no = 7
            """
        ).fetchone()
        brazil_shot_source = conn.execute(
            """
            select distinct source_id
            from shots
            where match_key = 'FIFA-2026-M07-BRA-MAR'
            """
        ).fetchall()
        fastest = conn.execute(
            """
            select player_name, team, top_speed_kmh
            from player_physical_stats
            order by top_speed_kmh desc
            limit 1
            """
        ).fetchone()
        vinicius = conn.execute(
            """
            select a.position, a.roster_status, o.total_offers, o.offers_received,
                   d.line_breaks_completed, d.ball_progressions
            from player_appearances a
            join player_offers_receptions o
              on o.match_key = a.match_key
             and o.team = a.team
             and o.player_no = a.player_no
            join player_in_possession_distributions d
              on d.match_key = a.match_key
             and d.team = a.team
             and d.player_no = a.player_no
            where a.match_key = 'FIFA-2026-M07-BRA-MAR'
              and a.team = 'Brazil'
              and a.player_name = 'VINICIUS JUNIOR'
            """
        ).fetchone()
        douglas = conn.execute(
            """
            select tackles_made, tackles_won, pressing_direct, possession_regains
            from player_defensive_actions
            where match_key = 'FIFA-2026-M07-BRA-MAR'
              and team = 'Brazil'
              and player_name = 'DOUGLAS SANTOS'
            """
        ).fetchone()
        krejci_line_breaks = conn.execute(
            """
            select line_breaks_attempted, line_breaks_completed, units_2_midfield_line,
                   direction_through, direction_around, distribution_pass,
                   distribution_ball_progression
            from player_line_breaks
            where match_key = 'FIFA-2026-M25-CZE-RSA'
              and team = 'Czechia'
              and player_name = 'Ladislav KREJCI'
            """
        ).fetchone()
    finally:
        conn.close()

    assert match_count == 4
    assert shot_count >= 90
    assert physical_count >= 90
    assert appearance_count >= 150
    assert offer_count >= 90
    assert defensive_count >= 90
    assert detailed_line_break_count >= 90
    assert {"source_id", "report_type", "version", "home_code", "away_code"}.issubset(
        source_columns
    )
    assert "source_id" in shot_columns
    assert brazil_source[0].startswith("fifa-world-cup-2026-pmsr-m07-bra-mar-v")
    assert brazil_source[1:] in {
        ("PMSR", 7, "BRA", "MAR", 1, 1),
        ("PMSR", 7, "BRA", "MAR", 2, 1),
    }
    assert brazil_shot_source == [(brazil_source[0],)]
    assert fastest == ("SON Heungmin", "Korea Republic", 35.2)
    assert vinicius == ("FW", "starting", 61, 26, 5, 11)
    assert douglas == (12, 4, 14, 8)
    assert krejci_line_breaks == (20, 18, 7, 7, 8, 19, 0)
