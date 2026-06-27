# Workflow

Use this sequence when asked to publish or check Editor's Choices.

1. Inspect repository state:

```bash
git status --short
python scripts/check_status.py
```

2. Refresh data if the user asks for the latest available match day:

```bash
python scripts/update_dataset.py
```

3. Find available local match dates:

```bash
sqlite3 data/latest.sqlite \
  "select match_date, count(*) from matches group by match_date order by match_date;"
```

4. Prepare the local editorial handoff packet:

```bash
python scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json
```

This step is deterministic and does not publish site artifacts. It writes the evidence packet that local Codex should inspect:

- `agent-runs/YYYY-MM-DD/rankings.json`
- `agent-runs/YYYY-MM-DD/candidate_pool.json`
- `agent-runs/YYYY-MM-DD/selector_input.json`
- `agent-runs/YYYY-MM-DD/run.json`
- `manifests/editorial-v2-run.json`

5. Build the deterministic editorial fact pack:

```bash
python scripts/inspect_editorial_day.py --date YYYY-MM-DD --json
```

This writes:

- `agent-runs/YYYY-MM-DD/editorial_fact_pack.json`
- `agent-runs/YYYY-MM-DD/editorial_fact_pack.md`

Read the fact pack before writing local editor outputs. It is the default source for goal timelines, own goals, official assists, team xG/shot pressure, goalkeeper checks, direct-impact candidates, high-ranked metric-led candidates, and reader traps such as "this goal was not the match-winner." Do not start editorial review with ad hoc SQL. If a recurring fact is missing, improve `scripts/inspect_editorial_day.py` instead of relying on one-off queries.

6. Write the bounded selection loop outputs:

For each round, write:

- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_review.json`: selection-only review covering whether the 3-6 card slate is convincing, the weakest selected card, strongest omitted candidate, reader objections, alternative slate comparison, and the revision decision.

If selection review blocks, revise by writing the next round. Stop when review passes or after three selection rounds. If selection still does not pass, mark the run `needs_human_review` instead of forcing a slate through.

7. Write the bounded copy loop outputs:

For each round, write:

- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy.json`: English and Chinese copy generated from the approved selected evidence packets.
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy_review.json`: copy-only review covering fact support, English flow, Chinese style, title core fact, display-name register, and unsupported claims.

If copy review blocks, revise by writing the next round. Stop when review passes or after three copy rounds. If copy still does not pass, mark the run `needs_human_review` instead of publishing weak prose.

8. Promote the passing loop:

```bash
python scripts/promote_editorial_loop.py --date YYYY-MM-DD --json
```

Promotion validates round-level selection/copy artifacts, writes review payloads and validations for each round, then writes:

- `agent-runs/YYYY-MM-DD/final_selection_decision.json`
- `agent-runs/YYYY-MM-DD/final_copy.json`
- canonical `agent-runs/YYYY-MM-DD/selection_decision.json`
- canonical `agent-runs/YYYY-MM-DD/copy.json`
- `agent-runs/YYYY-MM-DD/editorial_loop_summary.json`

Do not edit compiled frontend JSON directly. If the output is wrong, change selection/copy/review, scoring config, candidate-pool config, prompts/profiles, or deterministic validation, then prepare/compile again. The active slate is overall-first: pick the strongest 3-6 public cards when evidence supports them. Public award types are Player of the Day and Impact Pick only. The upper bound is capacity, not a target; a shorter slate is correct when the next card is materially weaker. Progression, defensive, goalkeeper, and hidden-gem metrics may appear in audit packets or as supporting evidence, but must not be standalone public labels. The slate normally allows at most two public cards from the same match, but a dominant result with multiple top-ranked, independently strong candidates can justify a third.

9. Compile and publish the promoted local result:

```bash
python scripts/compile_local_editorial.py --date YYYY-MM-DD --json
```

This validates local selection, writes public editorial artifacts, and rebuilds the homepage.

Outputs:

- `manifests/editorial-v2-run.json`
- `reports/editorial/YYYY-MM-DD.md`
- `agent-runs/YYYY-MM-DD/rankings.json`
- `agent-runs/YYYY-MM-DD/candidate_pool.json`
- `agent-runs/YYYY-MM-DD/selector_input.json`
- `agent-runs/YYYY-MM-DD/editorial_fact_pack.json`
- `agent-runs/YYYY-MM-DD/editorial_fact_pack.md`
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_decision.json`
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_validation.json`
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_review_payload.json`
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_review.json`
- `agent-runs/YYYY-MM-DD/selection_rounds/round_N/selection_review_validation.json`
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy.json`
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy_validation.json`
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy_review_payload.json`
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy_review.json`
- `agent-runs/YYYY-MM-DD/copy_rounds/round_N/copy_review_validation.json`
- `agent-runs/YYYY-MM-DD/final_selection_decision.json`
- `agent-runs/YYYY-MM-DD/final_copy.json`
- `agent-runs/YYYY-MM-DD/selection_decision.json`
- `agent-runs/YYYY-MM-DD/selection_validation.json`
- `agent-runs/YYYY-MM-DD/copy_validation.json`
- `agent-runs/YYYY-MM-DD/editorial_loop_summary.json`
- `agent-runs/YYYY-MM-DD/editorial_loop_validation.json`
- `agent-runs/YYYY-MM-DD/run.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html`

The active production experiment is `bounded_editorial_loop_v1`, using the `bounded_selection_copy_loop_v1` workflow variant:

```text
load active experiment registry
  -> deterministic ranking and public/audit candidate-pool build
  -> deterministic editorial fact-pack build
  -> local Codex writes selection round 1 from candidate_pool.selectable_candidates
  -> deterministic selection validation and selection-only review
  -> revise selection until review passes or three rounds are exhausted
  -> local Codex writes copy round 1 from the approved selection and fact packet
  -> deterministic copy validation and copy-only review
  -> revise copy until review passes or three rounds are exhausted
  -> promote final selection/copy and write editorial_loop_summary
  -> deterministic loop validation
  -> compile public editorial artifacts
  -> rebuild homepage
```

The GitHub `Update Dataset` workflow should fetch and rebuild data and deploy the static site. Editorial publication is local-first: prepare the packet, write the local editor artifacts, compile them, and publish through a PR. Future API editor agents should follow `docs/editorial-api-agent-spec.md` and run in shadow mode before replacing local Codex output.

10. Review local audit files:

- `candidate_pool.json`: public `selectable_candidates`, audit-only role/coverage `audit_candidates`, near misses, rank lookup, and candidate-pool reasons.
- `selector_input.json`: what local Codex should consider, usually name-sorted so it is not anchored to score order.
- `editorial_fact_pack.json` / `.md`: fixed fact review for matches, goals, assists, own goals, team pressure, goalkeeper checks, direct-impact candidates, metric-led candidates, and reader traps.
- `selection_rounds/round_N/selection_decision.json`: round-specific selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `selection_rounds/round_N/selection_review.json`: round-specific selection critique and revision decision.
- `final_selection_decision.json`: promoted selection after passing the selection loop.
- `copy_rounds/round_N/copy.json`: round-specific copy draft.
- `copy_rounds/round_N/copy_review.json`: round-specific copy critique and revision decision.
- `final_copy.json`: promoted copy after passing the copy loop.
- `selection_decision.json`: canonical promoted selection consumed by compile.
- `selection_validation.json`: deterministic checks for pool membership, the 3-6 public-card count range, award limits, slate balance, and skipped-higher-ranked explanations.
- `copy_validation.json`: deterministic checks for banned public Chinese abstract terms and other copy-profile gates.
- `editorial_loop_summary.json`: promoted loop status, selected rounds, stop reasons, and selected player ids.
- `editorial_loop_validation.json`: deterministic check that promoted loop artifacts are coherent.
- `reports/editorial/YYYY-MM-DD.md`: human-readable generated report.

If output is poor, repair the source of the problem: scoring config, candidate-pool profile, selector profile, copy profile, prompts, or deterministic validation. Avoid hand-editing compiled frontend JSON.

11. Review gates before accepting output:

- Did each attempted selection round write selection, review payload, review, and review validation?
- Does the promoted selection round's `selection_validation.json` pass?
- Did local Codex explain selected players and skipped higher-ranked candidates inside the selected round?
- Did local Codex inspect `editorial_fact_pack` before making selection/copy claims?
- Is every selected player present in the candidate pool?
- Does the whole slate avoid overconcentrating one match unless the extra card has an extraordinary independent reason?
- Does the slate avoid picking a weaker card just to fill match coverage, and does it reject standalone progression, defensive, goalkeeper, or hidden-gem public labels?
- Does each card have a distinct football angle?
- Are there at most two or three key facts per body?
- Did each attempted copy round write copy, review payload, review, and review validation?
- Does the promoted copy round's `copy_validation.json` pass?
- Does `editorial_loop_validation.json` pass?
- Did selection review cover obvious omissions, weakest selected, strongest omitted, reader objections, and alternative slates?
- Did copy review cover fact support, English flow, Chinese style, title core fact, and unsupported claims?
- Did copy review use the active style calibration examples, especially for generic Chinese closing evaluations and AI-ish abstraction?
- Does the copy avoid implying video review, media ratings, or unsupported tactical observation?
- Does the homepage show the latest generated cards?

For ad hoc wording audits, use `rg -n "<terms>" site/editorial/YYYY-MM-DD site/index.html` against generated artifacts. Do not turn broad phrase scans over docs or source files into unit tests.

12. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

13. Follow `pr-policy.md` for publication.
