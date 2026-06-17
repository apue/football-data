from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceDocument:
    source_url: str | None
    file_name: str
    sha256: str
    file_size: int


@dataclass(frozen=True)
class Match:
    match_key: str
    match_no: int
    group_name: str
    match_date: str
    kickoff_time: str
    stadium: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int


@dataclass(frozen=True)
class TeamMatchStat:
    match_key: str
    team: str
    opponent: str
    possession_pct: float | None = None
    goals: int | None = None
    xg: float | None = None
    attempts_total: int | None = None
    attempts_on_target: int | None = None
    passes_total: int | None = None
    passes_complete: int | None = None
    pass_completion_pct: float | None = None
    completed_line_breaks: int | None = None
    defensive_line_breaks: int | None = None
    receptions_final_third: int | None = None
    crosses: int | None = None
    ball_progressions: int | None = None
    defensive_pressures: int | None = None
    direct_pressures: int | None = None
    forced_turnovers: int | None = None
    second_balls: int | None = None
    total_distance_km: float | None = None
    zone4_low_speed_sprinting_km: float | None = None


@dataclass(frozen=True)
class Shot:
    match_key: str
    team: str
    shot_no: int
    minute: int
    player_name: str
    outcome: str
    body_part: str
    delivery_type: str
    is_goal: bool
    is_on_target: bool


@dataclass(frozen=True)
class PlayerPhysicalStat:
    match_key: str
    team: str
    player_no: int
    player_name: str
    total_distance_m: float | None = None
    zone1_m: float | None = None
    zone2_m: float | None = None
    zone3_m: float | None = None
    zone4_m: float | None = None
    zone5_m: float | None = None
    high_speed_runs: float | None = None
    sprints: float | None = None
    top_speed_kmh: float | None = None


@dataclass(frozen=True)
class ExtractedMatch:
    pdf_path: Path
    source: SourceDocument
    match: Match
    team_stats: list[TeamMatchStat] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    player_physical: list[PlayerPhysicalStat] = field(default_factory=list)

