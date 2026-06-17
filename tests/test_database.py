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
    ]

    build_database(db_path, records)

    conn = sqlite3.connect(db_path)
    try:
        match_count = conn.execute("select count(*) from matches").fetchone()[0]
        shot_count = conn.execute("select count(*) from shots").fetchone()[0]
        physical_count = conn.execute("select count(*) from player_physical_stats").fetchone()[0]
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
    finally:
        conn.close()

    assert match_count == 3
    assert shot_count == 67
    assert physical_count >= 90
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
