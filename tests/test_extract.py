from pathlib import Path

from football_data.extract import extract_pdf


RAW_DIR = Path(__file__).resolve().parents[1] / "raw"


def _pdf(pattern: str) -> Path:
    matches = sorted(RAW_DIR.glob(f"**/{pattern}"))
    assert matches, f"No PDF fixture found for {pattern}"
    return matches[-1]


def test_extract_match_metadata_from_brazil_morocco_pdf():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))

    assert record.match.match_key == "FIFA-2026-M07-BRA-MAR"
    assert record.match.home_team == "Brazil"
    assert record.match.away_team == "Morocco"
    assert record.match.home_score == 1
    assert record.match.away_score == 1
    assert record.match.group_name == "Group C"
    assert record.match.match_no == 7
    assert record.match.match_date == "2026-06-13"
    assert record.match.kickoff_time == "18:00"
    assert record.match.stadium == "New York/New Jersey Stadium"


def test_extract_brazil_shots_from_detail_page():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))
    brazil_shots = [shot for shot in record.shots if shot.team == "Brazil"]

    assert len(brazil_shots) == 12
    assert brazil_shots[0].minute == 8
    assert brazil_shots[0].player_name == "RAPHINHA"
    assert brazil_shots[0].outcome == "Incomplete - Blocked"
    assert brazil_shots[0].body_part == "Left Foot"
    assert brazil_shots[0].delivery_type == "Pass"

    goal = next(shot for shot in brazil_shots if shot.is_goal)
    assert goal.minute == 31
    assert goal.player_name == "VINICIUS JUNIOR"
    assert goal.is_on_target is True


def test_extract_physical_data_for_fastest_player():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))

    vinicius = next(
        row
        for row in record.player_physical
        if row.team == "Brazil" and row.player_name == "VINICIUS JUNIOR"
    )
    assert vinicius.total_distance_m == 10103.7
    assert vinicius.sprints == 60
    assert vinicius.top_speed_kmh == 34.1

    saibari = next(
        row
        for row in record.player_physical
        if row.team == "Morocco" and row.player_name == "Ismael SAIBARI"
    )
    assert saibari.total_distance_m == 10124.4
    assert saibari.top_speed_kmh == 33.7
