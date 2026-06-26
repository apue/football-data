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

6. Write the local editor outputs:

- `agent-runs/YYYY-MM-DD/selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `agent-runs/YYYY-MM-DD/copy.json`: final English and Chinese card copy generated from the selected candidate evidence packets.
- `agent-runs/YYYY-MM-DD/editorial_review.json`: local reader-intuition review of the final slate and copy.

Do not edit compiled frontend JSON directly. If the output is wrong, change selection/copy/review, scoring config, candidate-pool config, prompts/profiles, or deterministic validation, then prepare/compile again. The active slate is overall-first: pick the strongest 3-6 public cards when evidence supports them, then use award types as editorial angles rather than fixed quotas. Use the match-count recommendation as guidance, not a quota; a shorter slate is correct when the remaining cases are thin. Progression, defensive, goalkeeper, impact, and hidden-gem labels are optional; do not fill them with weaker candidates just for variety. The slate normally allows at most two public cards from the same match, but a dominant result with multiple top-ranked, independently strong candidates can justify a third.

7. Compile and publish the local result:

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
- `agent-runs/YYYY-MM-DD/selection_decision.json`
- `agent-runs/YYYY-MM-DD/selection_validation.json`
- `agent-runs/YYYY-MM-DD/copy_validation.json`
- `agent-runs/YYYY-MM-DD/editorial_review_payload.json`
- `agent-runs/YYYY-MM-DD/editorial_review.json`
- `agent-runs/YYYY-MM-DD/editorial_review_validation.json`
- `agent-runs/YYYY-MM-DD/run.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html`

The active production experiment is `ai_rerank_reader_loop_v5`, using the `ai_rerank_selection_v1` workflow variant:

```text
load active experiment registry
  -> deterministic ranking and rich candidate-pool build
  -> deterministic editorial fact-pack build
  -> local Codex reranks only candidate_pool.selectable_candidates
  -> deterministic selection validation
  -> English and Chinese copy from selected evidence packets
  -> deterministic copy validation
  -> local reader-intuition loop review with slate coverage, reader questions, alternative slate comparison, weakest selected, strongest omitted, and deterministic review validation
  -> compile public editorial artifacts
  -> rebuild homepage
```

The GitHub `Update Dataset` workflow should fetch and rebuild data and deploy the static site. Editorial publication is local-first: prepare the packet, write the local editor artifacts, compile them, and publish through a PR. Future API editor agents should follow `docs/editorial-api-agent-spec.md` and run in shadow mode before replacing local Codex output.

8. Review local audit files:

- `candidate_pool.json`: Top 8 selectable candidates, near misses, rank lookup, and candidate-pool reasons.
- `selector_input.json`: what local Codex should consider, usually name-sorted so it is not anchored to score order.
- `editorial_fact_pack.json` / `.md`: fixed fact review for matches, goals, assists, own goals, team pressure, goalkeeper checks, direct-impact candidates, metric-led candidates, and reader traps.
- `selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `selection_validation.json`: deterministic checks for pool membership, the 3-6 public-card count range, award limits, slate balance, and skipped-higher-ranked explanations.
- `copy_validation.json`: deterministic checks for banned public Chinese abstract terms and other copy-profile gates.
- `editorial_review_payload.json`: compact review packet covering selected players, required top-ranked unselected candidates, slate counts, validation status, and copy.
- `editorial_review_payload.json` also includes `style_calibration` examples loaded from `config/editorial/style_calibration/` when the active review profile requests them.
- `editorial_review.json`: local Codex reader-intuition review for obvious omissions, slate balance, metric misuse, copy style, style calibration, and display-name register.
- `editorial_review_validation.json`: deterministic check that the review covered required dimensions, selected players, required unselected candidates, and has no blocking findings.
- `reports/editorial/YYYY-MM-DD.md`: human-readable generated report.

If output is poor, repair the source of the problem: scoring config, candidate-pool profile, selector profile, copy profile, prompts, or deterministic validation. Avoid hand-editing compiled frontend JSON.

9. Review gates before accepting output:

- Does `selection_validation.json` pass?
- Did local Codex explain selected players and skipped higher-ranked candidates?
- Did local Codex inspect `editorial_fact_pack` before making selection/copy claims?
- Is every selected player present in the candidate pool?
- Does the whole slate avoid overconcentrating one match unless the extra card has an extraordinary independent reason?
- Does the slate avoid picking a weaker Progression Engine, Defensive Pick, Goalkeeper Watch, Hidden Gem, or Impact Pick just to fill an angle?
- Does each card have a distinct football angle?
- Are there at most two or three key facts per body?
- Does `copy_validation.json` pass?
- Does `editorial_review_validation.json` pass?
- Did review cover obvious omissions, slate balance, metric misuse, copy style, and display names?
- Did review use the active style calibration examples, especially for generic Chinese closing evaluations and AI-ish abstraction?
- Does the copy avoid implying video review, media ratings, or unsupported tactical observation?
- Does the homepage show the latest generated cards?

For ad hoc wording audits, use `rg -n "<terms>" site/editorial/YYYY-MM-DD site/index.html` against generated artifacts. Do not turn broad phrase scans over docs or source files into unit tests.

10. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

11. Follow `pr-policy.md` for publication.
