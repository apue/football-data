# Editorial API Agent Spec

Status: draft, implementation hold

This spec defines how a future cloud API editor agent can replace the local
Codex editor step without changing the deterministic data, validation, or
static publishing architecture.

## Goals

- Keep the current local-first editorial workflow as the baseline.
- Allow an API agent to fill the same three local editor artifacts:
  `selection_decision.json`, `copy.json`, and `editorial_review.json`.
- Feed the API agent the same deterministic candidate pool, match context, and
  validation constraints that local Codex uses.
- Preserve deterministic scoring, packet construction, validation, artifact
  compilation, and homepage generation in repository scripts.
- Support shadow comparison between local Codex output and API agent output
  before any API mode becomes the default.
- Keep human review and PR-based publication as the default editorial release
  path.

## Non-Goals

- Do not enable cloud API publication by default.
- Do not pick a production API model in this spec.
- Do not replace `prepare_editorial_packet.py` or
  `compile_local_editorial.py`.
- Do not let the API agent query arbitrary repository files, mutate generated
  site JSON directly, or select players outside the candidate pool.
- Do not rebuild OpenAI Agents SDK runtime features inside this repository.
  Repository code should define contracts, artifacts, config, and validation;
  agent orchestration should use the chosen SDK/API runtime.

## Stable Mainline

These parts remain stable regardless of local or API execution mode:

- FIFA PMSR documents and FIFA timeline data remain the source evidence.
- SQLite and generated site files remain rebuildable artifacts.
- `scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json` remains the
  deterministic handoff entrypoint.
- Scoring config, candidate-pool config, selector profile, copy profiles, and
  review profile remain experiment registry concerns.
- Final publication still goes through
  `scripts/compile_local_editorial.py --date YYYY-MM-DD --json`.
- Validation gates remain deterministic Python checks:
  `selection_validation.json`, `copy_validation.json`, and
  `editorial_review_validation.json`.
- Public output remains static HTML/JSON under `site/editorial/` and
  `site/index.html`.

## Runtime Modes

### Local Codex Baseline

The current baseline remains:

1. Deterministic packet generation.
2. Local Codex writes `selection_decision.json`, `copy.json`, and
   `editorial_review.json`.
3. Deterministic compile and validation.
4. Human review.
5. PR and merge only after approval.

### API Shadow Mode

API shadow mode runs after the deterministic packet is prepared and before
publication.

It writes API outputs to a separate run namespace, for example:

- `agent-runs/YYYY-MM-DD/api-shadow/selection_decision.json`
- `agent-runs/YYYY-MM-DD/api-shadow/copy.json`
- `agent-runs/YYYY-MM-DD/api-shadow/editorial_review.json`
- `agent-runs/YYYY-MM-DD/api-shadow/run.json`

Shadow output must not overwrite the local baseline artifacts unless explicitly
promoted by a human reviewer.

### API Primary Mode

API primary mode is a future promotion target. It can write the canonical three
editor artifacts only after shadow evaluation shows acceptable quality across
multiple match days.

API primary mode must still pass the same deterministic compile and validation
gates before any public artifact is generated.

## Agent Contracts

The API agent does not need full repository access. It receives compact,
deterministic packets and returns schema-constrained JSON.

### Shared Inputs

Every API step receives:

- active experiment id and profile ids
- match date and match count
- public-card count rules
- award limits and slate-balance constraints
- candidate pool identity and fingerprint
- source artifact paths and hashes
- prior validation status when available

### Selector Input

Selector input must include:

- `selector_input.json`
- selected fields from `candidate_pool.json`
- day-level match list with scores
- official goal timeline and goal-involvement facts
- top headline candidates
- required top-ranked unselected candidates to consider
- near misses and ineligible-but-notable candidates
- rank lookup for query/debug use
- scoring component summaries, not only final scores
- display-name hints

The selector must treat score order as coarse ranking only.

### Selector Output

The selector returns `selection_decision.json` with:

- selected players from the candidate pool only
- award type for each selected player
- selection reason
- evidence used
- public angle
- skipped higher-ranked candidates
- skipped notable candidates
- slate-balance rationale
- card-count rationale when the count differs from match-count guidance
- warnings for uncertainty or weak evidence

The selector must not write public copy.

### Copy Input

Copy input includes:

- selected player evidence packets
- selection reasons
- display-name config for each selected player
- English and Chinese copy-profile instructions
- banned public terms and style constraints
- fact constraints from candidate evidence and SQLite-derived timeline facts

Copy generation must not add new facts outside the selected evidence packet.

### Copy Output

Copy output is `copy.json` with:

- one English title and body per selected card
- one Chinese title and body per selected card
- locale-specific display-name choice when needed
- evidence-linked card metadata
- warnings for any awkward or uncertain wording

Chinese and English must express the same editorial judgment but do not need to
be literal translations.

### Reviewer Input

Reviewer input includes:

- final selected slate
- final copy
- skipped higher-ranked and notable candidates
- day-level match list and score context
- validation statuses
- review profile requirements
- candidate-pool evidence for selected and required unselected candidates

### Reviewer Output

Reviewer output is `editorial_review.json` with:

- status
- reviewed dimensions
- slate assessment
- predicted reader questions
- alternative slate comparison
- weakest selected card
- strongest omitted card
- metric-misuse findings
- copy-style findings
- display-name findings
- blocking findings
- revision decision

A blocking finding must target either selection, copy, or review. Generic
quality complaints are not enough.

## Revision Loop

The API runtime may run a bounded revision loop:

1. Generate selection.
2. Generate copy.
3. Generate review.
4. Run deterministic validation.
5. If review or validation blocks:
   - selection issues return to selector
   - copy issues return to copy agent
   - review-coverage issues return to reviewer
   - unsupported facts fail the run unless they can be removed from copy
6. Stop after the configured maximum revision rounds.

If blocking issues remain after the maximum rounds, write `needs_human_review`
in the run artifact and do not publish.

## Deterministic Gates

The following checks remain outside the model:

- selected players are in the candidate pool
- public card count is within the active experiment range
- award limits are respected
- skipped higher-ranked candidates are explained
- slate concentration rules are respected or justified
- copy avoids banned public terms
- copy avoids unsupported facts
- review covers required dimensions
- review names required selected and unselected candidates
- homepage and editorial artifacts compile from canonical files only

## Shadow Evaluation

Shadow comparison should be stored as a dated audit artifact and should compare
API output against the local baseline.

Required comparison dimensions:

- selected-player overlap
- strongest omitted candidate differences
- award-type differences
- card-count differences
- match-coverage differences
- direct-impact omission risk
- metric-misuse risk
- unsupported-claim risk
- Chinese copy acceptance
- English copy acceptance
- human acceptance decision

Promotion from shadow to primary requires repeated human acceptance across
multiple match days, including at least one high-scoring day, one low-scoring
day, and one day with a plausible defensive or goalkeeper card.

## Experiment Registry

The registry should describe API mode as an execution variant, not as a new
scoring system.

Registry fields for a future API experiment should include:

- `execution_mode`: `local_codex`, `api_shadow`, or `api_primary`
- `selector_model_key`
- `copy_model_key`
- `review_model_key`
- `selector_profile`
- `copy_profiles`
- `review_profile`
- `max_revision_rounds`
- `input_contract_version`
- `output_schema_version`
- `shadow_baseline`
- `human_review_required`

Scoring, candidate-pool, selector-profile, copy-profile, and review-profile
experiments remain separate variation points.

## Failure Handling

The API run must fail closed when:

- the model output is invalid JSON
- selected players are outside the candidate pool
- a selected claim conflicts with timeline or candidate evidence
- required skipped-candidate explanations are missing
- reviewer marks a blocking issue unresolved
- deterministic validation fails after revision rounds
- API output cannot be matched to the packet fingerprint

Failed API output may be kept for audit, but it must not overwrite local
baseline artifacts or public site artifacts.

## Publication Policy

Until explicitly changed, publication remains manual-first:

1. Generate or refresh deterministic data.
2. Prepare the editorial packet.
3. Produce local baseline output.
4. Optionally produce API shadow output.
5. Review local and shadow comparison.
6. Compile only the approved canonical artifacts.
7. Open PR.
8. Merge after approval.

API primary mode does not imply automatic publishing. Automatic publishing is a
separate policy decision.

## Acceptance Criteria

The implementation is acceptable only when:

- local baseline behavior remains unchanged
- API shadow output is isolated from canonical local artifacts
- all API outputs use the same schemas expected by compile/validation
- deterministic validation can reject bad API output
- shadow comparison can explain material differences from the local baseline
- human review can promote or discard API output without hand-editing compiled
  frontend JSON
- no raw PDFs or unauthorized source material are committed

## Initial Implementation Slice

When implementation is approved, the first slice should be limited to API
shadow mode:

1. Add API run config to the experiment registry.
2. Add schema validation for API selector, copy, and review outputs.
3. Add a shadow run command that reads existing prepared packets.
4. Write API artifacts under `agent-runs/YYYY-MM-DD/api-shadow/`.
5. Add a shadow comparison report.
6. Keep compile/publish pointed at the local baseline.

Promotion to API primary mode is out of scope for the first slice.
