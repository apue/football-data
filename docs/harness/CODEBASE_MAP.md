# Codebase Map

- `football_data/match_flow.py`: deterministic score-state reconstruction and player flow impacts.
- `football_data/editorial_scoring.py`: configurable player role and headline scores.
- `football_data/editorial_rankings.py`: ranked public player surfaces.
- `football_data/editorial_candidates.py`: selectable and audit-only candidate pools.
- `football_data/editorial_loop.py`: selection/copy review payloads and validators.
- `config/scoring/`: versioned deterministic score definitions.
- `config/editorial/experiments/`: workflow and card-count variants.
- `config/editorial/selector_profiles/`: local selection policy.
- `config/editorial/selection_review_profiles/`: required red-team review contract.
- `tests/test_match_flow.py`, `tests/test_editorial_v2.py`, `tests/test_editorial_loop.py`: public behavioral seams.
