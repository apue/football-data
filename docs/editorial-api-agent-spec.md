# Editorial Dual-Line Agent Spec

Status: draft, implementation hold

This spec defines a future dual-line editorial workflow where a cloud API agent
produces the primary editorial candidate, local Codex runs as a shadow editor
and reference critic, and a human reviewer decides what becomes the canonical
published output. It keeps deterministic data, validation, compilation, and
static publishing in repository scripts.

The current repository does not implement this runtime yet. This document is a
design target for later experimentation.

## Goals

- Keep FIFA PMSR and FIFA timeline data as the only source evidence.
- Keep deterministic packet generation, scoring, candidate-pool construction,
  validation, artifact compilation, and homepage generation in Python scripts.
- Let an API agent produce the first editorial candidate from the same packet
  that local Codex sees.
- Let local Codex produce a shadow result and/or critique that can challenge
  the API candidate before publication.
- Make human arbitration explicit and durable through a structured decision
  artifact.
- Turn recurring human feedback into experiment changes, eval cases, validator
  changes, or prompt/profile revisions.
- Keep publication manual-first until the API line has earned promotion across
  repeated match days.

## Non-Goals

- Do not enable automatic API publication by default.
- Do not select a production API model in this spec.
- Do not replace `scripts/prepare_editorial_packet.py` or
  `scripts/compile_local_editorial.py`.
- Do not let any agent query arbitrary repository files, mutate compiled site
  JSON directly, fetch private data, or select players outside the candidate
  pool.
- Do not rebuild SDK/runtime orchestration features inside this repository.
  Repository code should define contracts, artifacts, registry config,
  validators, and comparison reports; the chosen API runtime should handle
  model calls, retries, tracing, and orchestration.
- Do not treat Codex output as ground truth. Codex is a shadow editor and critic,
  not an automatic judge.

## Stable Mainline

These parts remain stable regardless of execution mode:

- Source documents, source URLs, hashes, parser versions, and timestamps remain
  traceable.
- SQLite and generated site files remain rebuildable artifacts.
- `scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json` remains the
  deterministic handoff entrypoint.
- Scoring config, candidate-pool config, selector profile, copy profiles,
  review profile, comparison profile, and execution mode remain experiment
  registry concerns.
- Public-card count rules, award limits, slate-balance constraints, display-name
  config, and banned public terms remain deterministic inputs.
- Final public output still goes through
  `scripts/compile_local_editorial.py --date YYYY-MM-DD --json`.
- Validation gates remain deterministic Python checks:
  `selection_validation.json`, `copy_validation.json`, and
  `editorial_review_validation.json`.
- Public output remains static HTML/JSON under `site/editorial/` and
  `site/index.html`.

## Runtime Topology

The target daily flow is:

1. GitHub Actions refreshes the dataset and static data artifacts.
2. A local or CI command prepares the deterministic editorial packet.
3. The API editorial line writes an isolated primary candidate.
4. The Codex shadow line writes an isolated reference result, critique, or both.
5. Deterministic validators check each line against the same packet and schemas.
6. A comparison report explains material differences.
7. A human reviewer accepts one line, mixes specific cards, rejects both, or
   requests a rerun.
8. Only the human-approved output is promoted into the canonical local artifact
   paths expected by `compile_local_editorial.py`.
9. The canonical artifacts are compiled, reviewed, opened as a PR, and merged
   only after approval.

The API line may be the first editorial candidate, but it is not the publisher.
The publisher remains the deterministic compiler plus human-approved canonical
artifacts.

## Runtime Modes

### Local Codex Current Mode

This is the current implemented mode:

1. Prepare the deterministic packet.
2. Local Codex writes canonical `selection_decision.json`, `copy.json`, and
   `editorial_review.json`.
3. Deterministic compile and validation run.
4. Human review decides whether to publish.

This mode remains available as the fallback and historical baseline.

### API Editorial With Codex Shadow

This is the proposed next experimental mode.

The API line writes:

- `agent-runs/YYYY-MM-DD/api-editorial/selection_decision.json`
- `agent-runs/YYYY-MM-DD/api-editorial/copy.json`
- `agent-runs/YYYY-MM-DD/api-editorial/editorial_review.json`
- `agent-runs/YYYY-MM-DD/api-editorial/selection_validation.json`
- `agent-runs/YYYY-MM-DD/api-editorial/copy_validation.json`
- `agent-runs/YYYY-MM-DD/api-editorial/editorial_review_validation.json`
- `agent-runs/YYYY-MM-DD/api-editorial/run.json`

The Codex shadow line writes one of two supported shapes:

- Full shadow:
  - `agent-runs/YYYY-MM-DD/codex-shadow/selection_decision.json`
  - `agent-runs/YYYY-MM-DD/codex-shadow/copy.json`
  - `agent-runs/YYYY-MM-DD/codex-shadow/editorial_review.json`
  - `agent-runs/YYYY-MM-DD/codex-shadow/run.json`
- Critic-only shadow:
  - `agent-runs/YYYY-MM-DD/codex-shadow/shadow_review.json`
  - `agent-runs/YYYY-MM-DD/codex-shadow/run.json`

Full shadow is better for measuring API quality against an independent editor.
Critic-only shadow is cheaper and may be enough when the API line is mature.

### API Primary Promotion

API primary is a future policy state, not the initial implementation.

In API primary mode, the API line may generate the approved candidate first, but
publication still requires deterministic validation and human review unless a
separate publication policy explicitly relaxes that requirement.

Automatic publishing is out of scope for this spec.

## Canonical Promotion

Neither `api-editorial/` nor `codex-shadow/` is canonical.

After human arbitration, a promotion step writes the approved artifacts to the
existing canonical paths under `agent-runs/YYYY-MM-DD/`:

- `selection_decision.json`
- `copy.json`
- `editorial_review.json`

The promotion step must also write:

- `comparison.json`
- `human_decision.json`
- `promotion.json`

`compile_local_editorial.py` should continue to compile only from canonical
paths. This keeps the public build independent of which execution line produced
the accepted draft.

## Agent Contracts

All agent outputs are schema-constrained JSON. Human-readable prose can appear
inside fields, but the artifact shape must remain machine-checkable.

### Shared Inputs

Every agent step receives:

- active experiment id and profile ids
- execution mode
- match date and match count
- public-card count rules
- award limits and slate-balance constraints
- candidate pool identity and fingerprint
- source artifact paths and hashes
- day-level match list and scores
- official goal timeline and goal-involvement facts
- scoring component summaries, not only final scores
- display-name hints
- prior validation status when available

The score order is a coarse ranking, not the final editorial decision.

### Selector Output

Selector output is `selection_decision.json` with:

- selected players from the candidate pool only
- award type for each selected player
- selection reason
- evidence used
- public angle
- skipped higher-ranked candidates
- skipped notable candidates
- slate-balance rationale
- card-count rationale based on marginal quality inside the 3-6 public-card range
- warnings for uncertainty or weak evidence

The selector must choose only from public `selectable_candidates`. Progression,
defensive, goalkeeper, hidden-gem, and match-coverage profiles live in
`audit_candidates` and may explain a decision, but they are not selectable public
slots.

### Copy Output

Copy output is `copy.json` with:

- one English title and body per selected card
- one Chinese title and body per selected card
- locale-specific display-name choice when needed
- evidence-linked card metadata
- warnings for awkward, overly translated, or uncertain wording

Copy generation must not add new facts outside the selected evidence packet,
timeline facts, or display-name config. Chinese and English must express the
same editorial judgment, but they do not need to mirror sentence order, tone, or
metaphor.

### Editorial Review Output

Review output is `editorial_review.json` with:

- status
- reviewed dimensions
- slate assessment
- predicted reader questions
- alternative slate comparison
- weakest selected card
- strongest omitted card
- drop-weakest verdict
- replace-weakest verdict
- preferred card count
- metric-misuse findings
- copy-style findings
- display-name findings
- blocking findings
- revision decision

A blocking finding must target selection, copy, review coverage, or evidence
support. Generic quality complaints are not enough.

### Codex Shadow Review Output

Critic-only shadow output is `shadow_review.json` with:

- API candidate summary
- likely reader objections
- strongest API omissions
- weakest API selections
- fact-risk findings
- metric-misuse findings
- copy-style findings
- suggested card additions
- suggested card removals
- suggested copy repairs
- overall recommendation:
  `accept_api`, `accept_with_repairs`, `prefer_codex_full_shadow`,
  `needs_human_review`, or `reject_api`

Codex shadow review should cite candidate ids, match ids, ranks, and evidence
fields when possible.

## Revision Loop

The API runtime may run a bounded internal revision loop:

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

If blocking issues remain after the maximum rounds, the API run writes
`needs_human_review` in `run.json` and cannot be promoted without explicit human
approval.

Codex shadow may also recommend repairs, but it should not directly modify the
API line. Repairs should produce a new API run or a human-approved mixed
canonical output.

## Deterministic Gates

The following checks remain outside the model:

- selected players are in the candidate pool
- selected artifacts match the packet fingerprint
- public card count is within the active experiment range
- award limits are respected
- skipped higher-ranked candidates are explained
- slate concentration rules are respected or justified
- copy avoids banned public terms
- copy avoids unsupported facts
- review covers required dimensions
- review names required selected and unselected candidates
- review weakest/strongest/drop/replace fields reference valid candidate ids
- comparison report references valid candidate ids
- human decision references valid line outputs or explicit mixed-card choices
- homepage and editorial artifacts compile from canonical files only

## Comparison Report

`comparison.json` compares the API editorial line with Codex shadow and the
deterministic ranking context.

Required dimensions:

- selected-player overlap
- API-only selections
- Codex-only selections
- strongest omitted candidates by each line
- award-type differences
- card-count differences
- match-coverage questions
- direct-impact omission risk
- dominant-team underselection risk
- weak-candidate selection risk
- metric-misuse risk
- unsupported-claim risk
- display-name risk
- Chinese copy acceptance
- English copy acceptance
- Codex shadow recommendation
- human acceptance decision when available

The report should separate objective differences from editorial disagreements.
For example, an unsupported claim is a blocking risk; choosing four cards
instead of five may be a judgment call if the rationale is clear. Match coverage
is a reader question, not a quota or a blocking issue by itself.

## Human Decision Artifact

`human_decision.json` is the durable record of arbitration.

It should include:

- `decision`: `accept_api`, `accept_codex`, `mixed`, `reject_both`, or
  `needs_rerun`
- accepted card ids and source line for each card
- rejected card ids and reason tags
- required copy repairs
- required selection repairs
- issue tags
- free-form reviewer notes
- whether the output may be published
- whether any follow-up experiment, validator, or profile change is required

Initial issue tags:

- `fact_error`
- `unsupported_claim`
- `strong_candidate_omitted`
- `weak_candidate_selected`
- `metric_misuse`
- `slate_balance`
- `match_concentration`
- `display_name`
- `copy_ai_tone`
- `copy_translationese`
- `too_prompt_shaped`
- `needs_more_emotion`
- `human_judgment_call`

Human feedback should be stored as product evidence, not as a one-off chat
comment. The improvement loop depends on being able to replay and aggregate it.

## Improvement Loop

The dual-line system improves through evidence-backed harness changes, not
through vague prompt tuning.

For each review cycle:

1. Collect raw artifacts:
   - prepared packet
   - API artifacts and validation
   - Codex shadow artifacts
   - comparison report
   - human decision
   - final published artifacts, if any
2. Classify failures by likely owner:
   - data or evidence packet
   - scoring or candidate pool
   - selector profile
   - copy profile
   - review profile
   - comparison profile
   - deterministic validator
   - model/runtime choice
   - product expectation not yet specified
3. Convert recurring failures into replay cases.
4. Make one bounded harness change.
5. Replay historical match days that cover the failure pattern.
6. Promote, keep, or kill the experiment based on acceptance and regression
   results.

Useful replay sets should include:

- high-scoring match days
- low-scoring match days
- days with a dominant team
- days with a plausible goalkeeper or defender card
- days with famous players and less famous statistical standouts
- days where prior output had copy-style issues
- days where prior output had unsupported factual claims

## Experiment Registry

Execution mode is a variation point separate from scoring.

Future registry fields may include:

- `execution_mode`: `local_codex_current`, `api_editorial_codex_shadow`, or
  `api_primary_human_reviewed`
- `api_selector_model_key`
- `api_copy_model_key`
- `api_review_model_key`
- `codex_shadow_mode`: `full_shadow` or `critic_only`
- `selector_profile`
- `copy_profiles`
- `review_profile`
- `comparison_profile`
- `human_decision_schema_version`
- `max_revision_rounds`
- `input_contract_version`
- `output_schema_version`
- `shadow_baseline`
- `human_review_required`

Scoring, candidate-pool, selector-profile, copy-profile, review-profile,
comparison-profile, and execution-mode experiments remain separate variation
points.

## Experiment Lifecycle

Each experiment should have a written hypothesis before implementation:

- What behavior should improve?
- Which variation point changes?
- Which match days will be replayed?
- What counts as success?
- What blocks promotion?
- What should be killed if the result is worse?

Promote an experiment only when:

- deterministic validation passes
- human acceptance is repeated across multiple match days
- the experiment handles at least one high-scoring day, one low-scoring day, and
  one day with a plausible non-attacker card
- fact errors and unsupported claims do not increase
- human copy repairs decrease or remain acceptable
- the comparison report can explain material API/Codex differences

Kill or archive an experiment when:

- it repeatedly misses obvious headline candidates
- it selects weak metric-only candidates without a strong public angle
- it increases unsupported factual claims
- it increases Chinese copy rewrites
- it produces no clear advantage over local Codex current mode
- it adds cost or complexity without improving human acceptance

## Failure Handling

An agent line must fail closed when:

- output is invalid JSON
- selected players are outside the candidate pool
- output cannot be matched to the packet fingerprint
- a selected claim conflicts with timeline or candidate evidence
- required skipped-candidate explanations are missing
- reviewer marks a blocking issue unresolved
- deterministic validation fails after revision rounds

Failed output may be kept for audit, but it must not overwrite canonical
artifacts or public site artifacts.

## Publication Policy

Until explicitly changed, publication remains manual-first:

1. Generate or refresh deterministic data.
2. Prepare the editorial packet.
3. Produce API editorial candidate output.
4. Produce Codex shadow output.
5. Validate both lines.
6. Generate comparison report.
7. Record human decision.
8. Promote approved artifacts to canonical paths.
9. Compile only the approved canonical artifacts.
10. Open PR.
11. Merge after approval.

API primary mode does not imply automatic publishing. Automatic publishing is a
separate policy decision.

## Acceptance Criteria

The implementation is acceptable only when:

- current local Codex publication remains available as fallback
- API and Codex line outputs are isolated from canonical artifacts
- all agent outputs use schemas expected by validation and comparison
- deterministic validation can reject bad output
- comparison can explain material API/Codex differences
- human review can accept, mix, reject, or rerun without editing compiled
  frontend JSON
- human decisions can be aggregated into replay cases and experiment changes
- no raw PDFs or unauthorized source material are committed

## Initial Implementation Slice

When implementation is approved, the first slice should be limited to
non-publishing dual-line review:

1. Add execution-mode config to the experiment registry.
2. Add isolated `api-editorial/` and `codex-shadow/` artifact namespaces.
3. Add schema validation for line outputs.
4. Add a comparison report over existing prepared packets.
5. Add `human_decision.json` and a promotion step into canonical artifacts.
6. Keep compile/publish pointed at canonical artifacts only.
7. Keep automatic publication out of scope.

Promotion to API primary mode is out of scope for the first slice.
