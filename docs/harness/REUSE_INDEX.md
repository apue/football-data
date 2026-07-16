# Reuse Index

- Extend `build_match_flows` and `player_flow_impacts`; do not add a second event-state reconstruction path.
- Extend `score_player`; preserve versioned JSON scoring configs.
- Extend `build_selection_review_payload` and `validate_selection_review`; preserve bounded review artifacts.
- Reuse `bounded_editorial_loop_v2` dynamic card-count rules and promote them after regression validation.
- Reuse the existing candidate pool; no new public role award types.
