# Editorial API Agent Spec

Status: draft, implementation hold

This spec defines a future API-backed execution mode for the bounded editorial
loop. The repository remains responsible for deterministic data preparation,
validation, promotion, compilation, and static publishing.

## Goals

- Keep FIFA PMSR and FIFA timeline data as the only source evidence.
- Keep deterministic packet generation, scoring, candidate-pool construction,
  validation, loop promotion, artifact compilation, and homepage generation in
  Python scripts.
- Let an API agent write auditable selection and copy rounds from the same
  packet that local Codex sees.
- Let local Codex run as a shadow critic or full shadow loop before API output
  can be promoted.
- Make human arbitration explicit and durable through structured comparison and
  promotion artifacts.
- Turn recurring human feedback into experiment changes, eval cases, validator
  changes, or prompt/profile revisions.
- Keep publication manual-first until the API line has earned promotion across
  repeated match days.

## Non-Goals

- Do not enable automatic API publication by default.
- Do not select a production API model in this spec.
- Do not replace `scripts/prepare_editorial_packet.py`,
  `scripts/promote_editorial_loop.py`, or `scripts/compile_local_editorial.py`.
- Do not let any agent query arbitrary repository files, mutate compiled site
  JSON directly, fetch private data, or select players outside the candidate
  pool.
- Do not rebuild SDK/runtime orchestration features inside this repository.
  Repository code should define contracts, artifacts, registry config,
  validators, and comparison reports; the chosen API runtime should handle
  model calls, retries, tracing, and orchestration.
- Do not treat either API output or Codex output as ground truth.

## Stable Mainline

These parts remain stable regardless of execution mode:

- Source documents, source URLs, hashes, parser versions, and timestamps remain
  traceable.
- SQLite and generated site files remain rebuildable artifacts.
- `scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json` remains the
  deterministic handoff entrypoint.
- `scripts/promote_editorial_loop.py --date YYYY-MM-DD --json` remains the
  canonical promotion gate.
- `scripts/compile_local_editorial.py --date YYYY-MM-DD --json` compiles only
  promoted canonical artifacts.
- Scoring config, candidate-pool config, selector profile, copy profiles,
  selection review profile, copy review profile, and execution mode remain
  experiment registry concerns.
- Public-card count rules, award limits, slate-balance constraints,
  display-name config, and banned public terms remain deterministic inputs.
- Validation gates remain deterministic Python checks:
  selection validation, selection review validation, copy validation, copy
  review validation, and promoted loop validation.
- Public output remains static HTML/JSON under `site/editorial/` and
  `site/index.html`.

## Runtime Topology

The target daily flow is:

1. GitHub Actions refreshes the dataset and static data artifacts.
2. A local or CI command prepares the deterministic editorial packet and fact
   pack.
3. The API editorial line writes isolated selection rounds and copy rounds.
4. The Codex shadow line writes either a full bounded loop or critic-only
   review of the API line.
5. Deterministic validators check each line against the same packet and schemas.
6. A comparison report explains material differences and unresolved objections.
7. A human reviewer accepts one line, mixes specific cards, rejects both, or
   requests a rerun.
8. Only the human-approved output is promoted into the canonical local artifact
   paths expected by `compile_local_editorial.py`.
9. The canonical artifacts are compiled, opened as a PR, and merged only after
   approval.

The API line may be the first editorial candidate, but it is not the publisher.
The publisher remains the deterministic compiler plus human-approved canonical
artifacts.

## Current Local Mode

The implemented local mode is:

1. Prepare the deterministic packet.
2. Build the deterministic fact pack.
3. Local Codex writes `selection_rounds/round_N/selection_decision.json` and
   `selection_review.json`, revising until the selection loop passes or three
   rounds are exhausted.
4. Local Codex writes `copy_rounds/round_N/copy.json` and `copy_review.json`,
   revising until the copy loop passes or three rounds are exhausted.
5. `scripts/promote_editorial_loop.py` validates round artifacts and writes:
   - `final_selection_decision.json`
   - `final_copy.json`
   - canonical `selection_decision.json`
   - canonical `copy.json`
   - `editorial_loop_summary.json`
6. `scripts/compile_local_editorial.py` validates the promoted loop and writes
   public artifacts.
7. Human review decides whether to publish.

## API Editorial With Codex Shadow

The API line writes isolated artifacts:

- `agent-runs/YYYY-MM-DD/api-editorial/selection_rounds/round_N/selection_decision.json`
- `agent-runs/YYYY-MM-DD/api-editorial/selection_rounds/round_N/selection_review.json`
- `agent-runs/YYYY-MM-DD/api-editorial/copy_rounds/round_N/copy.json`
- `agent-runs/YYYY-MM-DD/api-editorial/copy_rounds/round_N/copy_review.json`
- `agent-runs/YYYY-MM-DD/api-editorial/editorial_loop_summary.json`
- `agent-runs/YYYY-MM-DD/api-editorial/run.json`

The Codex shadow line writes one of two supported shapes:

- Full shadow bounded loop under `agent-runs/YYYY-MM-DD/codex-shadow/`.
- Critic-only shadow under `agent-runs/YYYY-MM-DD/codex-shadow/shadow_review.json`.

Full shadow is better for measuring API quality against an independent editor.
Critic-only shadow is cheaper and may be enough when the API line is mature.

## Agent Contracts

### Selection Round

`selection_rounds/round_N/selection_decision.json` contains selected players
from the candidate pool only, award type, selection reason, evidence used,
public angle, skipped higher-ranked candidates, skipped notable candidates, and
card-count rationale.

`selection_rounds/round_N/selection_review.json` contains status, reviewed
dimensions, selected-player reviews, reader objections, alternative slate
comparison, weakest selected card, strongest omitted card, drop/replace
verdicts, preferred card count, blocking findings, resolved objections,
unresolved objections, and revision summary.

### Copy Round

`copy_rounds/round_N/copy.json` contains one English title/body and one Chinese
title/body per selected card.

`copy_rounds/round_N/copy_review.json` contains status, reviewed dimensions,
item-level reviews by language, fact-support findings, style findings,
blocking findings, resolved comments, unresolved comments, and revision summary.

## Bounded Revision

Each execution line runs a bounded loop:

1. Generate selection round.
2. Validate selection and selection review.
3. If blocked, revise selection and repeat until the configured maximum rounds.
4. Generate copy round from the approved selection.
5. Validate copy and copy review.
6. If blocked, revise copy and repeat until the configured maximum rounds.
7. If both loops pass, promote final artifacts.
8. If either loop exceeds the maximum rounds, write `needs_human_review` in
   `run.json` and do not promote without explicit human approval.

## Promotion

Neither `api-editorial/` nor `codex-shadow/` is canonical. A promotion step
writes the human-approved artifacts to the existing canonical paths under
`agent-runs/YYYY-MM-DD/`.

The promotion step must also write:

- `comparison.json`
- `human_decision.json`
- `promotion.json`

`compile_local_editorial.py` should continue to compile only from canonical
paths. This keeps the public build independent of which execution line produced
the accepted draft.
