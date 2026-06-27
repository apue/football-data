from __future__ import annotations

from pathlib import Path


DEFAULT_SCORING_CONFIG = Path("config/scoring/v0.4.json")


PUBLIC_AWARD_TYPES = ("player_of_the_day", "impact_pick")

AWARD_LABELS = {
    "player_of_the_day": {"en": "Player of the Day", "zh": "每日最佳球员"},
    "impact_pick": {"en": "Impact Pick", "zh": "影响力精选"},
}

AUDIT_LABELS = {
    "progression_pick": {"en": "Progression Audit", "zh": "推进审计"},
    "defensive_pick": {"en": "Defensive Audit", "zh": "防守审计"},
    "goalkeeper_watch": {"en": "Goalkeeper Audit", "zh": "门将审计"},
    "hidden_gem": {"en": "Hidden-Gem Audit", "zh": "隐藏亮点审计"},
}

ALL_AWARD_LABELS = {
    **AWARD_LABELS,
    **AUDIT_LABELS,
}

AWARD_DISPLAY_ORDER = list(PUBLIC_AWARD_TYPES)


AWARD_DISPLAY_PRIORITY = {
    award_type: index
    for index, award_type in enumerate(AWARD_DISPLAY_ORDER)
}
