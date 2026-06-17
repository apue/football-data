import sqlite3
from pathlib import Path

from football_data.database import build_database
from football_data.extract import extract_pdf


RAW_DIR = Path(__file__).resolve().parents[1] / "raw"


def test_build_database_loads_matches_shots_and_physical_rows(tmp_path):
    db_path = tmp_path / "latest.sqlite"
    records = [
        extract_pdf(RAW_DIR / "PMSR-M01 MEX V RSA.pdf"),
        extract_pdf(RAW_DIR / "PMSR-M02 KOR V CZE .pdf"),
        extract_pdf(RAW_DIR / "PMSR-M07-BRA-V-MAR.pdf"),
    ]

    build_database(db_path, records)

    conn = sqlite3.connect(db_path)
    try:
        match_count = conn.execute("select count(*) from matches").fetchone()[0]
        shot_count = conn.execute("select count(*) from shots").fetchone()[0]
        physical_count = conn.execute("select count(*) from player_physical_stats").fetchone()[0]
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
    assert fastest == ("SON Heungmin", "Korea Republic", 35.2)

