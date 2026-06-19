from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DiscoveredSource:
    source_id: str
    competition: str
    report_type: str
    match_no: int
    home_code: str
    away_code: str
    version: int
    source_url: str
    file_name: str
    discovered_at: str
    active: bool = True
    status: str = "active"


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    competition: str
    report_type: str
    match_no: int
    home_code: str
    away_code: str
    version: int
    source_url: str | None
    file_name: str
    sha256: str
    file_size: int
    discovered_at: str | None = None
    fetched_at: str | None = None
    active: bool = True
    status: str = "active"


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
    source_id: str | None = None
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
    source_id: str | None = None


@dataclass(frozen=True)
class PlayerPhysicalStat:
    match_key: str
    team: str
    player_no: int
    player_name: str
    source_id: str | None = None
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
class PlayerAppearance:
    match_key: str
    team: str
    opponent: str
    player_no: int
    player_name: str
    position: str
    roster_status: str
    started: bool
    source_id: str | None = None


@dataclass(frozen=True)
class PlayerEventMarker:
    match_key: str
    team: str
    player_no: int
    player_name: str
    marker_index: int
    raw_marker: str
    minute: int | None
    source_id: str | None = None
    page_number: int | None = None


@dataclass(frozen=True)
class PlayerDistributionStat:
    match_key: str
    team: str
    player_no: int
    player_name: str
    source_id: str | None = None
    page_number: int | None = None
    passes_attempted: int | None = None
    passes_completed: int | None = None
    pass_completion_pct: float | None = None
    switches_of_play: int | None = None
    crosses_attempted: int | None = None
    crosses_completed: int | None = None
    line_breaks_attempted: int | None = None
    line_breaks_completed: int | None = None
    line_break_completion_pct: float | None = None
    ball_progressions: int | None = None
    take_ons: int | None = None
    step_ins: int | None = None
    attempts_at_goal: int | None = None
    goals: int | None = None


@dataclass(frozen=True)
class PlayerLineBreakStat:
    match_key: str
    team: str
    player_no: int
    player_name: str
    source_id: str | None = None
    page_number: int | None = None
    line_breaks_attempted: int | None = None
    line_breaks_completed: int | None = None
    line_break_completion_pct: float | None = None
    units_4_attacking_line: int | None = None
    units_4_attacking_midfield_line: int | None = None
    units_4_midfield_line: int | None = None
    units_4_defensive_line: int | None = None
    units_3_attacking_line: int | None = None
    units_3_midfield_line: int | None = None
    units_3_defensive_line: int | None = None
    units_2_midfield_line: int | None = None
    units_2_defensive_line: int | None = None
    direction_through: int | None = None
    direction_around: int | None = None
    direction_over: int | None = None
    distribution_pass: int | None = None
    distribution_cross: int | None = None
    distribution_ball_progression: int | None = None


@dataclass(frozen=True)
class PlayerOffersReceptions:
    match_key: str
    team: str
    player_no: int
    player_name: str
    source_id: str | None = None
    page_number: int | None = None
    total_offers: int | None = None
    in_front: int | None = None
    in_between: int | None = None
    out_to_in: int | None = None
    in_to_out: int | None = None
    in_behind: int | None = None
    no_movement: int | None = None
    offers_received: int | None = None


@dataclass(frozen=True)
class PlayerDefensiveActionStat:
    match_key: str
    team: str
    player_no: int
    player_name: str
    source_id: str | None = None
    page_number: int | None = None
    tackles_made: int | None = None
    tackles_won: int | None = None
    blocks: int | None = None
    interceptions: int | None = None
    pressing_direct: int | None = None
    pressing_indirect: int | None = None
    duels_won_aerial: int | None = None
    duels_won_physical: int | None = None
    possession_contests_won: int | None = None
    clearances: int | None = None
    loose_ball_receptions: int | None = None
    pushing_on: int | None = None
    pushing_on_into_pressing: int | None = None
    possession_regains: int | None = None
    possession_interrupted: int | None = None


@dataclass(frozen=True)
class ExtractedMatch:
    pdf_path: Path
    source: SourceDocument
    match: Match
    team_stats: list[TeamMatchStat] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    player_physical: list[PlayerPhysicalStat] = field(default_factory=list)
    player_appearances: list[PlayerAppearance] = field(default_factory=list)
    player_event_markers: list[PlayerEventMarker] = field(default_factory=list)
    player_distributions: list[PlayerDistributionStat] = field(default_factory=list)
    player_line_breaks: list[PlayerLineBreakStat] = field(default_factory=list)
    player_offers: list[PlayerOffersReceptions] = field(default_factory=list)
    player_defensive_actions: list[PlayerDefensiveActionStat] = field(default_factory=list)
