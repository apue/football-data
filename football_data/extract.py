from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz

from football_data import __version__
from football_data.model import (
    ExtractedMatch,
    Match,
    PlayerPhysicalStat,
    Shot,
    SourceDocument,
    TeamMatchStat,
)


TEAM_CODES = {
    "Brazil": "BRA",
    "Morocco": "MAR",
    "Mexico": "MEX",
    "South Africa": "RSA",
    "Korea Republic": "KOR",
    "Czechia": "CZE",
}

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

SOURCE_URLS = {
    "PMSR-M01 MEX V RSA.pdf": "https://www.fifatrainingcentre.com/media/native/tournaments/fifa-world-cup/2026/PMSR-M01%20MEX%20V%20RSA.pdf",
    "PMSR-M02 KOR V CZE .pdf": "https://www.fifatrainingcentre.com/media/native/tournaments/fifa-world-cup/2026/PMSR-M02%20KOR%20V%20CZE%20.pdf",
    "PMSR-M07-BRA-V-MAR.pdf": "https://www.fifatrainingcentre.com/media/native/tournaments/fifa-world-cup/2026/PMSR-M07-BRA-V-MAR.pdf",
}


def extract_pdf(path: str | Path) -> ExtractedMatch:
    pdf_path = Path(path)
    doc = fitz.open(pdf_path)
    pages = [_clean_lines(page.get_text()) for page in doc]
    match = _parse_match(pages[0])
    source = SourceDocument(
        source_url=SOURCE_URLS.get(pdf_path.name),
        file_name=pdf_path.name,
        sha256=_sha256(pdf_path),
        file_size=pdf_path.stat().st_size,
    )
    return ExtractedMatch(
        pdf_path=pdf_path,
        source=source,
        match=match,
        team_stats=_parse_team_stats(match, pages[2]),
        shots=_parse_shots(match, pages[14], pages[16]),
        player_physical=_parse_physical(match, pages[49], pages[50]),
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


def _parse_match(lines: list[str]) -> Match:
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
    home_code = TEAM_CODES.get(home_team, _fallback_team_code(home_team))
    away_code = TEAM_CODES.get(away_team, _fallback_team_code(away_team))
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


def _parse_team_stats(match: Match, lines: list[str]) -> list[TeamMatchStat]:
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
            **home_values,
        ),
        TeamMatchStat(
            match_key=match.match_key,
            team=match.away_team,
            opponent=match.home_team,
            **away_values,
        ),
    ]


def _parse_shots(match: Match, *pages: list[str]) -> list[Shot]:
    shots: list[Shot] = []
    shot_no_by_team: dict[str, int] = {}
    for lines in pages:
        if len(lines) < 8 or lines[0] != "Attempts at Goal":
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
                    is_goal="Goal" in outcome,
                    is_on_target=("On Target" in outcome) or ("Goal" in outcome),
                )
            )
            idx += 5
        shot_no_by_team[team] = shot_no
    return shots


def _parse_physical(match: Match, *pages: list[str]) -> list[PlayerPhysicalStat]:
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

