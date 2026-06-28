from pathlib import Path

import pytest

from football_data.extract import _parse_shots, extract_pdf
from football_data.model import Match


RAW_DIR = Path(__file__).resolve().parents[1] / "raw"


def _pdf(pattern: str) -> Path:
    matches = sorted(RAW_DIR.glob(f"**/{pattern}"))
    assert matches, f"No PDF fixture found for {pattern}"
    return matches[-1]


def test_attempt_goal_prevented_is_not_parsed_as_goal():
    match = Match(
        match_key="FIFA-2026-M27-CAN-QAT",
        match_no=27,
        group_name="Group B",
        match_date="2026-06-18",
        kickoff_time="15:00",
        stadium="BC Place Vancouver",
        home_team="Canada",
        away_team="Qatar",
        home_score=6,
        away_score=0,
    )

    shots = _parse_shots(
        match,
        "test-source",
        [
            "Attempts at Goal",
            "Canada",
            "Minute",
            "Player",
            "Outcome",
            "Body Part",
            "Delivery Type",
            "37",
            "Tajon BUCHANAN",
            "On Target - Goal Prevented",
            "Right Foot",
            "Cross",
            "49",
            "Luis ROMO",
            "On Target - Goal",
            "Right Foot",
            "Pass",
            "18 June 2026 - BC Place Vancouver - 15:00",
        ],
    )

    prevented = next(shot for shot in shots if shot.player_name == "Tajon BUCHANAN")
    goal = next(shot for shot in shots if shot.player_name == "Luis ROMO")

    assert prevented.is_on_target is True
    assert prevented.is_goal is False
    assert goal.is_goal is True


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


def test_extract_player_appearances_from_lineup_page():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))

    vinicius = next(
        row
        for row in record.player_appearances
        if row.team == "Brazil" and row.player_name == "VINICIUS JUNIOR"
    )
    assert vinicius.player_no == 7
    assert vinicius.position == "FW"
    assert vinicius.roster_status == "starting"
    assert vinicius.started is True

    neymar = next(
        row
        for row in record.player_appearances
        if row.team == "Brazil" and row.player_name == "NEYMAR JR"
    )
    assert neymar.player_no == 10
    assert neymar.position == "FW"
    assert neymar.roster_status == "substitute"
    assert neymar.started is False

    hakimi = next(
        row
        for row in record.player_appearances
        if row.team == "Morocco" and row.player_name == "Achraf HAKIMI"
    )
    assert hakimi.player_no == 2
    assert hakimi.position == "DF"
    assert hakimi.started is True

    vinicius_markers = [
        row.raw_marker
        for row in record.player_event_markers
        if row.team == "Brazil" and row.player_name == "VINICIUS JUNIOR"
    ]
    assert "32'" in vinicius_markers


def test_extract_individual_in_possession_tables():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))

    vinicius_distribution = next(
        row
        for row in record.player_distributions
        if row.team == "Brazil" and row.player_name == "VINICIUS JUNIOR"
    )
    assert vinicius_distribution.passes_attempted == 32
    assert vinicius_distribution.line_breaks_completed == 5
    assert vinicius_distribution.ball_progressions == 11
    assert vinicius_distribution.take_ons == 10
    assert vinicius_distribution.attempts_at_goal == 1
    assert vinicius_distribution.goals == 1

    vinicius_offers = next(
        row
        for row in record.player_offers
        if row.team == "Brazil" and row.player_name == "VINICIUS JUNIOR"
    )
    assert vinicius_offers.total_offers == 61
    assert vinicius_offers.in_behind == 15
    assert vinicius_offers.no_movement == 28
    assert vinicius_offers.offers_received == 26


def test_extract_detailed_line_break_tables():
    record = extract_pdf(_pdf("PMSR-M25*.pdf"))

    krejci = next(
        row
        for row in record.player_line_breaks
        if row.team == "Czechia" and row.player_name == "Ladislav KREJCI"
    )
    mokoena = next(
        row
        for row in record.player_line_breaks
        if row.team == "South Africa" and row.player_name == "Teboho MOKOENA"
    )

    assert krejci.line_breaks_attempted == 20
    assert krejci.line_breaks_completed == 18
    assert krejci.units_4_attacking_line == 1
    assert krejci.units_3_attacking_line == 8
    assert krejci.units_2_midfield_line == 7
    assert krejci.direction_through == 7
    assert krejci.direction_around == 8
    assert krejci.distribution_pass == 19
    assert krejci.distribution_ball_progression == 0

    assert mokoena.line_breaks_attempted == 32
    assert mokoena.line_breaks_completed == 29
    assert mokoena.units_2_midfield_line == 16
    assert mokoena.direction_through == 11
    assert mokoena.direction_around == 14
    assert mokoena.distribution_ball_progression == 1


def test_extract_individual_out_of_possession_table():
    record = extract_pdf(_pdf("PMSR-M07*.pdf"))

    douglas = next(
        row
        for row in record.player_defensive_actions
        if row.team == "Brazil" and row.player_name == "DOUGLAS SANTOS"
    )
    assert douglas.tackles_made == 12
    assert douglas.tackles_won == 4
    assert douglas.pressing_direct == 14
    assert douglas.pressing_indirect == 17
    assert douglas.possession_regains == 8
    assert douglas.possession_interrupted == 6


def test_extract_lineup_name_continuation_rows():
    matches = sorted(RAW_DIR.glob("**/PMSR-M11*.pdf"))
    if not matches:
        pytest.skip("M11 PDF is downloaded by the update pipeline")
    record = extract_pdf(matches[-1])

    summerville = next(
        row
        for row in record.player_appearances
        if row.team == "Netherlands" and row.player_no == 24
    )
    assert summerville.player_name == "Crysencio SUMMERVILLE"
    assert summerville.position == "FW"
    assert len(record.player_appearances) == 52


def test_extract_right_lineup_name_continuation_rows():
    matches = sorted(RAW_DIR.glob("**/PMSR-M61*.pdf"))
    if not matches:
        pytest.skip("M61 PDF is downloaded by the update pipeline")
    record = extract_pdf(matches[-1])

    dembele = next(
        row
        for row in record.player_appearances
        if row.team == "France" and row.player_no == 7
    )
    assert dembele.player_name == "Ousmane DEMBELE"
    assert dembele.position == "FW"
    assert dembele.roster_status == "starting"
    assert dembele.started is True
    assert len(record.player_appearances) == 52


def test_extract_lineup_full_names_across_wide_name_columns():
    m61 = extract_pdf(_pdf("PMSR-M61*.pdf"))
    holmgren_pedersen = next(
        row
        for row in m61.player_appearances
        if row.team == "Norway" and row.player_no == 16
    )
    assert holmgren_pedersen.player_name == "Marcus HOLMGREN PEDERSEN"

    m64 = extract_pdf(_pdf("PMSR-M64*.pdf"))
    fernandez_pardo = next(
        row
        for row in m64.player_appearances
        if row.team == "Belgium" and row.player_no == 26
    )
    assert fernandez_pardo.player_name == "Matias FERNANDEZ-PARDO"


def test_extract_lineup_names_ignore_stoppage_time_markers():
    matches = sorted(RAW_DIR.glob("**/PMSR-M10*.pdf"))
    if not matches:
        pytest.skip("M10 PDF is downloaded by the update pipeline")
    record = extract_pdf(matches[-1])

    havertz = next(
        row
        for row in record.player_appearances
        if row.team == "Germany" and row.player_no == 7
    )
    assert havertz.player_name == "Kai HAVERTZ"

    dirty_names = [
        row.player_name
        for row in record.player_appearances
        if "45+5'" in row.player_name or "90+3'" in row.player_name
    ]
    assert dirty_names == []
