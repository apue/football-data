from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz

from football_data import __version__
from football_data.discovery import source_from_filename
from football_data.model import (
    DiscoveredSource,
    ExtractedMatch,
    Match,
    PlayerAppearance,
    PlayerDefensiveActionStat,
    PlayerDistributionStat,
    PlayerEventMarker,
    PlayerOffersReceptions,
    PlayerPhysicalStat,
    Shot,
    SourceDocument,
    TeamMatchStat,
)


MONTHS = {
    "January": "01",
    "February": "02",
    "March": "03",
    "April": "04",
    "May": "05",
    "June": "06",
    "July": "07",
    "August": "08",
    "September": "09",
    "October": "10",
    "November": "11",
    "December": "12",
}

Word = tuple[float, float, float, float, str]
WordRow = list[Word]


def extract_pdf(path: str | Path, source: DiscoveredSource | None = None) -> ExtractedMatch:
    pdf_path = Path(path)
    doc = fitz.open(pdf_path)
    pages = [_clean_lines(page.get_text()) for page in doc]
    word_rows = [_word_rows(page) for page in doc]
    source_hint = source or source_from_filename(
        pdf_path.name,
        source_url=None,
        discovered_at=None,
    )
    match = _parse_match(pages[0], source_hint)
    source_document = _source_document_for_pdf(pdf_path, match, source_hint)
    source = SourceDocument(
        source_id=source_document.source_id,
        competition=source_document.competition,
        report_type=source_document.report_type,
        match_no=source_document.match_no,
        home_code=source_document.home_code,
        away_code=source_document.away_code,
        version=source_document.version,
        source_url=source_document.source_url or None,
        file_name=source_document.file_name,
        sha256=_sha256(pdf_path),
        file_size=pdf_path.stat().st_size,
        discovered_at=source_document.discovered_at,
        fetched_at=extraction_timestamp(),
        active=source_document.active,
        status=source_document.status,
    )
    appearances, event_markers = _parse_appearances(match, source.source_id, pages, word_rows)
    return ExtractedMatch(
        pdf_path=pdf_path,
        source=source,
        match=match,
        team_stats=_parse_team_stats(match, source.source_id, pages[2]),
        shots=_parse_shots(match, source.source_id, *pages),
        player_physical=_parse_physical(match, source.source_id, *pages),
        player_appearances=appearances,
        player_event_markers=event_markers,
        player_distributions=_parse_distributions(match, source.source_id, pages, word_rows),
        player_offers=_parse_offers(match, source.source_id, pages, word_rows),
        player_defensive_actions=_parse_defensive_actions(
            match,
            source.source_id,
            pages,
            word_rows,
        ),
    )


def parser_version() -> str:
    return __version__


def extraction_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_document_for_pdf(
    pdf_path: Path,
    match: Match,
    source_hint: DiscoveredSource | None,
) -> DiscoveredSource:
    if source_hint is not None:
        return source_hint
    home_code = _fallback_team_code(match.home_team)
    away_code = _fallback_team_code(match.away_team)
    return DiscoveredSource(
        source_id=f"fifa-world-cup-2026-pmsr-m{match.match_no:02d}-{home_code.lower()}-{away_code.lower()}-v1",
        competition="fifa-world-cup-2026",
        report_type="PMSR",
        match_no=match.match_no,
        home_code=home_code,
        away_code=away_code,
        version=1,
        source_url="",
        file_name=pdf_path.name,
        discovered_at=extraction_timestamp(),
    )


def _parse_match(lines: list[str], source: DiscoveredSource | None = None) -> Match:
    score_line = lines[0]
    score_match = re.match(r"(.+?)\s+(\d+)\s+-\s+(\d+)\s+(.+)", score_line)
    if not score_match:
        raise ValueError(f"Could not parse match score line: {score_line!r}")
    home_team, home_score, away_score, away_team = score_match.groups()

    group_match = re.match(r"(.+)\s+-\s+Match\s+(\d+)", lines[1])
    if not group_match:
        raise ValueError(f"Could not parse group/match line: {lines[1]!r}")
    group_name, match_no = group_match.groups()

    match_date = _parse_date(lines[2])
    kickoff_time = lines[3].replace(" Kick Off", "")
    stadium = lines[4]
    home_code = source.home_code if source else _fallback_team_code(home_team)
    away_code = source.away_code if source else _fallback_team_code(away_team)
    match_key = f"FIFA-2026-M{int(match_no):02d}-{home_code}-{away_code}"

    return Match(
        match_key=match_key,
        match_no=int(match_no),
        group_name=group_name,
        match_date=match_date,
        kickoff_time=kickoff_time,
        stadium=stadium,
        home_team=home_team,
        away_team=away_team,
        home_score=int(home_score),
        away_score=int(away_score),
    )


def _parse_date(value: str) -> str:
    day, month_name, year = value.split()
    return f"{year}-{MONTHS[month_name]}-{int(day):02d}"


def _fallback_team_code(name: str) -> str:
    words = re.findall(r"[A-Za-z]+", name.upper())
    if len(words) == 1:
        return words[0][:3]
    return "".join(word[0] for word in words)[:3]


def _parse_team_stats(match: Match, source_id: str, lines: list[str]) -> list[TeamMatchStat]:
    home_values: dict[str, object] = {"goals": match.home_score}
    away_values: dict[str, object] = {"goals": match.away_score}

    if "Possession" in lines:
        start = lines.index("Possession")
        percents = [_parse_percent(line) for line in lines[start : start + 8] if line.endswith("%")]
        if len(percents) >= 3:
            home_values["possession_pct"] = percents[0]
            away_values["possession_pct"] = percents[-1]

    metric_map = {
        "xG (Expected Goals)": ("xg", _parse_float),
        "Attempts at Goal (On Target)": ("attempts", _parse_attempts),
        "Total Passes (Complete)": ("passes", _parse_attempts),
        "Pass Completion %": ("pass_completion_pct", _parse_percent),
        "Completed Line Breaks": ("completed_line_breaks", _parse_int),
        "Defensive Line Breaks": ("defensive_line_breaks", _parse_int),
        "Receptions in the Final Third": ("receptions_final_third", _parse_int),
        "Crosses": ("crosses", _parse_int),
        "Ball Progressions": ("ball_progressions", _parse_int),
        "Defensive Pressures Applied (Direct Pressures)": ("pressures", _parse_attempts),
        "Forced Turnovers": ("forced_turnovers", _parse_int),
        "Second Balls": ("second_balls", _parse_int),
        "Total Distance Covered": ("total_distance_km", _parse_km),
        "Zone 4 – Low Speed Sprinting: 20-25 km/h": ("zone4_low_speed_sprinting_km", _parse_km),
    }

    for label, (field, parser) in metric_map.items():
        if label not in lines:
            continue
        idx = lines.index(label)
        if idx == 0 or idx + 1 >= len(lines):
            continue
        home_raw, away_raw = lines[idx - 1], lines[idx + 1]
        home_parsed, away_parsed = parser(home_raw), parser(away_raw)
        if field == "attempts":
            home_values["attempts_total"], home_values["attempts_on_target"] = home_parsed
            away_values["attempts_total"], away_values["attempts_on_target"] = away_parsed
        elif field == "passes":
            home_values["passes_total"], home_values["passes_complete"] = home_parsed
            away_values["passes_total"], away_values["passes_complete"] = away_parsed
        elif field == "pressures":
            home_values["defensive_pressures"], home_values["direct_pressures"] = home_parsed
            away_values["defensive_pressures"], away_values["direct_pressures"] = away_parsed
        else:
            home_values[field] = home_parsed
            away_values[field] = away_parsed

    return [
        TeamMatchStat(
            match_key=match.match_key,
            team=match.home_team,
            opponent=match.away_team,
            source_id=source_id,
            **home_values,
        ),
        TeamMatchStat(
            match_key=match.match_key,
            team=match.away_team,
            opponent=match.home_team,
            source_id=source_id,
            **away_values,
        ),
    ]


def _parse_shots(match: Match, source_id: str, *pages: list[str]) -> list[Shot]:
    shots: list[Shot] = []
    shot_no_by_team: dict[str, int] = {}
    for lines in pages:
        if len(lines) < 8 or lines[0] != "Attempts at Goal":
            continue
        if "Delivery Type" not in lines:
            continue
        team = lines[1]
        idx = lines.index("Delivery Type") + 1
        shot_no = shot_no_by_team.get(team, 0)
        while idx + 4 < len(lines):
            if re.match(r"\d{1,2} \w+ 2026", lines[idx]):
                break
            minute_raw = lines[idx]
            if not minute_raw.isdigit():
                idx += 1
                continue
            minute = int(minute_raw)
            player_name = lines[idx + 1]
            outcome = lines[idx + 2]
            body_part = lines[idx + 3]
            delivery_type = lines[idx + 4]
            is_goal = outcome.endswith(" - Goal")
            shot_no += 1
            shots.append(
                Shot(
                    match_key=match.match_key,
                    team=team,
                    shot_no=shot_no,
                    minute=minute,
                    player_name=player_name,
                    outcome=outcome,
                    body_part=body_part,
                    delivery_type=delivery_type,
                    is_goal=is_goal,
                    is_on_target=("On Target" in outcome) or is_goal,
                    source_id=source_id,
                )
            )
            idx += 5
        shot_no_by_team[team] = shot_no
    return shots


def _parse_physical(match: Match, source_id: str, *pages: list[str]) -> list[PlayerPhysicalStat]:
    rows: list[PlayerPhysicalStat] = []
    for lines in pages:
        if not lines or lines[0] != "Physical Data":
            continue
        team = lines[1]
        try:
            idx = lines.index("(km/h)") + 1
        except ValueError:
            continue
        while idx + 1 < len(lines):
            if re.match(r"\d{1,2} \w+ 2026", lines[idx]):
                break
            if not (_is_int(lines[idx]) and not _is_number(lines[idx + 1])):
                idx += 1
                continue
            player_no = int(lines[idx])
            player_name = lines[idx + 1]
            idx += 2
            values: list[float] = []
            while idx < len(lines):
                if re.match(r"\d{1,2} \w+ 2026", lines[idx]):
                    break
                if idx + 1 < len(lines) and _is_int(lines[idx]) and not _is_number(lines[idx + 1]):
                    break
                if _is_number(lines[idx]):
                    values.append(float(lines[idx]))
                idx += 1
            padded = values[:9] + [None] * max(0, 9 - len(values))
            rows.append(
                PlayerPhysicalStat(
                    match_key=match.match_key,
                    team=team,
                    player_no=player_no,
                    player_name=player_name,
                    source_id=source_id,
                    total_distance_m=padded[0],
                    zone1_m=padded[1],
                    zone2_m=padded[2],
                    zone3_m=padded[3],
                    zone4_m=padded[4],
                    zone5_m=padded[5],
                    high_speed_runs=padded[6],
                    sprints=padded[7],
                    top_speed_kmh=padded[8],
                )
            )
    return rows


def _parse_appearances(
    match: Match,
    source_id: str,
    pages: list[list[str]],
    word_rows: list[list[WordRow]],
) -> tuple[list[PlayerAppearance], list[PlayerEventMarker]]:
    appearances: list[PlayerAppearance] = []
    event_markers: list[PlayerEventMarker] = []
    for page_index, lines in enumerate(pages):
        if not lines or lines[0] != "Match Summary - Teams":
            continue
        rows = word_rows[page_index]
        left_sub_y = _section_y(rows, "SUBSTITUTES", 0, 120)
        right_sub_y = _section_y(rows, "SUBSTITUTES", 820, 930)
        for row_index, row in enumerate(rows):
            left = _parse_left_lineup_row(row, left_sub_y, rows, row_index)
            if left is not None:
                appearance, markers = _lineup_row_to_records(
                    match=match,
                    source_id=source_id,
                    team=match.home_team,
                    opponent=match.away_team,
                    page_number=page_index + 1,
                    row=left,
                )
                appearances.append(appearance)
                event_markers.extend(markers)

            right = _parse_right_lineup_row(row, right_sub_y)
            if right is not None:
                appearance, markers = _lineup_row_to_records(
                    match=match,
                    source_id=source_id,
                    team=match.away_team,
                    opponent=match.home_team,
                    page_number=page_index + 1,
                    row=right,
                )
                appearances.append(appearance)
                event_markers.extend(markers)
    return appearances, event_markers


def _parse_distributions(
    match: Match,
    source_id: str,
    pages: list[list[str]],
    word_rows: list[list[WordRow]],
) -> list[PlayerDistributionStat]:
    rows: list[PlayerDistributionStat] = []
    columns = {
        "passes_attempted": (190, 236),
        "passes_completed": (245, 291),
        "pass_completion_pct": (300, 345),
        "switches_of_play": (350, 400),
        "crosses_attempted": (405, 455),
        "crosses_completed": (465, 510),
        "line_breaks_attempted": (515, 565),
        "line_breaks_completed": (570, 620),
        "line_break_completion_pct": (625, 675),
        "ball_progressions": (680, 730),
        "take_ons": (735, 785),
        "step_ins": (790, 835),
        "attempts_at_goal": (845, 890),
        "goals": (895, 940),
    }
    percent_fields = {"pass_completion_pct", "line_break_completion_pct"}
    for page_index, lines in enumerate(pages):
        if len(lines) < 2 or lines[0] != "In Possession - Distributions":
            continue
        team = lines[1]
        for row in word_rows[page_index]:
            identity = _player_identity_from_metric_row(row)
            if identity is None:
                continue
            player_no, player_name = identity
            values = {
                name: (
                    _parse_percent_cell(_row_text_between(row, *bounds))
                    if name in percent_fields
                    else _parse_int_cell(_row_text_between(row, *bounds))
                )
                for name, bounds in columns.items()
            }
            rows.append(
                PlayerDistributionStat(
                    match_key=match.match_key,
                    team=team,
                    player_no=player_no,
                    player_name=player_name,
                    source_id=source_id,
                    page_number=page_index + 1,
                    **values,
                )
            )
    return rows


def _parse_offers(
    match: Match,
    source_id: str,
    pages: list[list[str]],
    word_rows: list[list[WordRow]],
) -> list[PlayerOffersReceptions]:
    rows: list[PlayerOffersReceptions] = []
    columns = {
        "total_offers": (190, 260),
        "in_front": (285, 350),
        "in_between": (380, 455),
        "out_to_in": (480, 545),
        "in_to_out": (575, 640),
        "in_behind": (670, 735),
        "no_movement": (765, 830),
        "offers_received": (860, 930),
    }
    for page_index, lines in enumerate(pages):
        if len(lines) < 2 or lines[0] != "In Possession - Offers & Receptions":
            continue
        team = lines[1]
        for row in word_rows[page_index]:
            identity = _player_identity_from_metric_row(row)
            if identity is None:
                continue
            player_no, player_name = identity
            values = {
                name: _parse_int_cell(_row_text_between(row, *bounds))
                for name, bounds in columns.items()
            }
            rows.append(
                PlayerOffersReceptions(
                    match_key=match.match_key,
                    team=team,
                    player_no=player_no,
                    player_name=player_name,
                    source_id=source_id,
                    page_number=page_index + 1,
                    **values,
                )
            )
    return rows


def _parse_defensive_actions(
    match: Match,
    source_id: str,
    pages: list[list[str]],
    word_rows: list[list[WordRow]],
) -> list[PlayerDefensiveActionStat]:
    rows: list[PlayerDefensiveActionStat] = []
    columns = {
        "blocks": (250, 290),
        "interceptions": (300, 350),
        "pressing_direct": (360, 405),
        "pressing_indirect": (415, 455),
        "duels_won_aerial": (470, 505),
        "duels_won_physical": (520, 555),
        "possession_contests_won": (575, 610),
        "clearances": (630, 665),
        "loose_ball_receptions": (680, 720),
        "pushing_on": (735, 775),
        "pushing_on_into_pressing": (790, 825),
        "possession_regains": (845, 880),
        "possession_interrupted": (895, 935),
    }
    for page_index, lines in enumerate(pages):
        if len(lines) < 2 or lines[0] != "Out of Possession":
            continue
        team = lines[1]
        for row in word_rows[page_index]:
            identity = _player_identity_from_metric_row(row)
            if identity is None:
                continue
            player_no, player_name = identity
            tackles_made, tackles_won = _parse_tackle_cell(_row_text_between(row, 190, 240))
            values = {
                name: _parse_int_cell(_row_text_between(row, *bounds))
                for name, bounds in columns.items()
            }
            rows.append(
                PlayerDefensiveActionStat(
                    match_key=match.match_key,
                    team=team,
                    player_no=player_no,
                    player_name=player_name,
                    source_id=source_id,
                    page_number=page_index + 1,
                    tackles_made=tackles_made,
                    tackles_won=tackles_won,
                    **values,
                )
            )
    return rows


def _lineup_row_to_records(
    *,
    match: Match,
    source_id: str,
    team: str,
    opponent: str,
    page_number: int,
    row: dict[str, object],
) -> tuple[PlayerAppearance, list[PlayerEventMarker]]:
    player_no = int(row["player_no"])
    player_name = str(row["player_name"])
    appearance = PlayerAppearance(
        match_key=match.match_key,
        team=team,
        opponent=opponent,
        player_no=player_no,
        player_name=player_name,
        position=str(row["position"]),
        roster_status=str(row["roster_status"]),
        started=bool(row["started"]),
        source_id=source_id,
    )
    markers: list[PlayerEventMarker] = []
    for index, marker in enumerate(row["event_markers"]):  # type: ignore[index]
        markers.append(
            PlayerEventMarker(
                match_key=match.match_key,
                team=team,
                player_no=player_no,
                player_name=player_name,
                marker_index=index + 1,
                raw_marker=str(marker),
                minute=_minute_from_marker(str(marker)),
                source_id=source_id,
                page_number=page_number,
            )
        )
    return appearance, markers


def _parse_left_lineup_row(
    row: WordRow,
    substitutes_y: float | None,
    rows: list[WordRow] | None = None,
    row_index: int | None = None,
) -> dict[str, object] | None:
    number_tokens = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 45 <= x0 <= 58 and _is_int(text)
    ]
    position_tokens = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 62 <= x0 <= 78 and text in {"GK", "DF", "MF", "FW"}
    ]
    if not number_tokens or not position_tokens:
        return None
    name_tokens = _left_lineup_name_tokens(row, rows, row_index)
    if not name_tokens:
        return None
    event_markers = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 140 <= x0 <= 235 and _is_minute_marker(text)
    ]
    row_y = _row_y(row)
    started = substitutes_y is not None and row_y < substitutes_y
    return {
        "player_no": int(number_tokens[0]),
        "position": position_tokens[0],
        "player_name": " ".join(name_tokens),
        "roster_status": "starting" if started else "substitute",
        "started": started,
        "event_markers": event_markers,
    }


def _parse_right_lineup_row(row: WordRow, substitutes_y: float | None) -> dict[str, object] | None:
    position: str | None = None
    player_no: int | None = None
    for x0, _y0, _x1, _y1, text in row:
        if not 875 <= x0 <= 910:
            continue
        match = re.fullmatch(r"(GK|DF|MF|FW)(\d+)?", text)
        if match:
            position = match.group(1)
            if match.group(2):
                player_no = int(match.group(2))
            break
    if position is None:
        return None
    if player_no is None:
        number_tokens = [
            text
            for x0, _y0, _x1, _y1, text in row
            if 895 <= x0 <= 910 and _is_int(text)
        ]
        if not number_tokens:
            return None
        player_no = int(number_tokens[0])
    name_tokens = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 760 <= x0 < 875
        and not _is_minute_marker(text)
        and not re.fullmatch(r"(GK|DF|MF|FW)\d*", text)
        and not _is_int(text)
    ]
    if not name_tokens:
        return None
    event_markers = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 720 <= x0 < 785 and _is_minute_marker(text)
    ]
    row_y = _row_y(row)
    started = substitutes_y is not None and row_y < substitutes_y
    return {
        "player_no": player_no,
        "position": position,
        "player_name": " ".join(name_tokens),
        "roster_status": "starting" if started else "substitute",
        "started": started,
        "event_markers": event_markers,
    }


def _word_rows(page: fitz.Page) -> list[WordRow]:
    words: list[Word] = [
        (float(x0), float(y0), float(x1), float(y1), str(text))
        for x0, y0, x1, y1, text, *_ in page.get_text("words")
    ]
    rows: list[WordRow] = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        if not rows or abs(_row_y(rows[-1]) - word[1]) > 3.0:
            rows.append([word])
        else:
            rows[-1].append(word)
    return [sorted(row, key=lambda item: item[0]) for row in rows]


def _left_lineup_name_tokens(
    row: WordRow,
    rows: list[WordRow] | None,
    row_index: int | None,
) -> list[str]:
    if rows is None or row_index is None:
        return _name_tokens_between(row, 82, 180)
    base_y = _row_y(row)
    tokens: list[str] = []
    for candidate in rows[max(0, row_index - 2) : row_index + 3]:
        if abs(_row_y(candidate) - base_y) > 12:
            continue
        if candidate is not row and _has_left_lineup_anchor(candidate):
            continue
        tokens.extend(_name_tokens_between(candidate, 82, 180))
    return tokens


def _name_tokens_between(row: WordRow, x_min: float, x_max: float) -> list[str]:
    return [
        text
        for x0, _y0, _x1, _y1, text in row
        if x_min <= x0 <= x_max
        and not _is_number(text)
        and not _is_minute_marker(text)
        and not re.fullmatch(r"(GK|DF|MF|FW)\d*", text)
    ]


def _has_left_lineup_anchor(row: WordRow) -> bool:
    has_number = any(45 <= x0 <= 58 and _is_int(text) for x0, _y0, _x1, _y1, text in row)
    has_position = any(
        62 <= x0 <= 78 and text in {"GK", "DF", "MF", "FW"}
        for x0, _y0, _x1, _y1, text in row
    )
    return has_number and has_position


def _section_y(rows: list[WordRow], text: str, x_min: float, x_max: float) -> float | None:
    for row in rows:
        if any(x_min <= word[0] <= x_max and word[4] == text for word in row):
            return _row_y(row)
    return None


def _player_identity_from_metric_row(row: WordRow) -> tuple[int, str] | None:
    number_tokens = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 15 <= x0 <= 35 and _is_int(text)
    ]
    if not number_tokens:
        return None
    name_tokens = [
        text
        for x0, _y0, _x1, _y1, text in row
        if 38 <= x0 < 185 and not _is_number(text) and not _is_minute_marker(text)
    ]
    if not name_tokens:
        return None
    return int(number_tokens[0]), " ".join(name_tokens)


def _row_text_between(row: WordRow, x_min: float, x_max: float) -> str:
    return " ".join(
        text
        for x0, _y0, _x1, _y1, text in row
        if x_min <= x0 <= x_max
    ).strip()


def _row_y(row: WordRow) -> float:
    return sum(word[1] for word in row) / len(row)


def _parse_int_cell(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_percent_cell(value: str) -> float | None:
    if value == "":
        return None
    try:
        return _parse_percent(value)
    except ValueError:
        return None


def _parse_tackle_cell(value: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d+)\s*/\s*(\d+)", value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _minute_from_marker(value: str) -> int | None:
    match = re.match(r"(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _is_minute_marker(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}'(?:\+\d+)?", value))


def _parse_attempts(value: str) -> tuple[int, int | None]:
    match = re.match(r"(\d+)\s+\((\d+)\)", value)
    if match:
        return int(match.group(1)), int(match.group(2))
    return int(value), None


def _parse_percent(value: str) -> float:
    return float(value.replace("%", "").strip())


def _parse_km(value: str) -> float:
    return float(value.replace("km", "").strip())


def _parse_float(value: str) -> float:
    return float(value.strip())


def _parse_int(value: str) -> int:
    return int(value.strip())


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _is_int(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))
