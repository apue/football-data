# Reuse and Cleanup Report

## Existing Capabilities

- `match_flow.py` already tags opening, equalising, winning, late, and comeback goals. Extend it with assister provenance and event-aware context values.
- `editorial_scoring.py` already supports versioned weights and separate role scores. Add v0.5 support instead of creating a new scorer.
- `bounded_editorial_loop_v2` already implements the desired one-match-day range.

## Deprecated or Removable Logic

- v0.4 additive goal-context scoring remains as a rollback path; remove only after v0.5 has sufficient production history.
- bounded loop v1 remains as rollback; it is no longer the active experiment after acceptance passes.

## Risks

- Overcorrecting against legitimate decisive goals.
- Assister names not matching PMSR appearances.
- Existing review fixtures assuming static three-card minimums.

## Decision

Extend existing flow, scoring, review, and v2 experiment boundaries. Add only versioned configs and regression tests.
