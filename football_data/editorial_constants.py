from __future__ import annotations

from pathlib import Path


DEFAULT_SCORING_CONFIG = Path("config/scoring/v0.4.json")


AWARD_LABELS = {
    "player_of_the_day": {"en": "Player of the Day", "zh": "每日最佳球员"},
    "impact_pick": {"en": "Impact Pick", "zh": "影响力精选"},
    "progression_pick": {"en": "Progression Engine", "zh": "进攻发动机"},
    "defensive_pick": {"en": "Defensive Pick", "zh": "防守精选"},
    "goalkeeper_watch": {"en": "Goalkeeper Watch", "zh": "门将关注"},
    "hidden_gem": {"en": "Hidden Gem", "zh": "隐藏亮点"},
}


AWARD_DISPLAY_ORDER = [
    "player_of_the_day",
    "impact_pick",
    "progression_pick",
    "defensive_pick",
    "goalkeeper_watch",
    "hidden_gem",
]


AWARD_DISPLAY_PRIORITY = {
    award_type: index
    for index, award_type in enumerate(AWARD_DISPLAY_ORDER)
}
