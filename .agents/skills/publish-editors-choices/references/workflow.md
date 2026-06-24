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

5. Write the local editor outputs:

- `agent-runs/YYYY-MM-DD/selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `agent-runs/YYYY-MM-DD/copy.json`: final English and Chinese card copy generated from the selected candidate evidence packets.

Do not edit compiled frontend JSON directly. If the output is wrong, change selection/copy, scoring config, candidate-pool config, prompts/profiles, or deterministic validation, then prepare/compile again. The active slate profile normally allows at most two public cards from the same match, and secondary slots can be omitted when the story feels forced.

6. Compile and publish the local result:

```bash
python scripts/compile_local_editorial.py --date YYYY-MM-DD --json
```

This validates local selection, writes public editorial artifacts, and rebuilds the homepage.

For deterministic smoke testing without OpenAI credentials:

```bash
python scripts/run_editorial_queue.py --date YYYY-MM-DD --fake --no-research --json
```

For low-level v2 debugging:

```bash
python scripts/run_editorial_v2.py --date YYYY-MM-DD --fake --no-research --json
```

Outputs:

- `manifests/editorial-v2-run.json`
- `reports/editorial/YYYY-MM-DD.md`
- `agent-runs/YYYY-MM-DD/rankings.json`
- `agent-runs/YYYY-MM-DD/candidate_pool.json`
- `agent-runs/YYYY-MM-DD/selector_input.json`
- `agent-runs/YYYY-MM-DD/selection_decision.json`
- `agent-runs/YYYY-MM-DD/selection_validation.json`
- `agent-runs/YYYY-MM-DD/copy_validation.json`
- `agent-runs/YYYY-MM-DD/run.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html`

The active production experiment is `ai_rerank_slate_copy_v3`, using the `ai_rerank_selection_v1` workflow variant:

```text
load active experiment registry
  -> deterministic ranking and rich candidate-pool build
  -> local Codex reranks only candidate_pool.selectable_candidates
  -> deterministic selection validation
  -> English and Chinese copy from selected evidence packets
  -> deterministic copy validation
  -> compile public editorial artifacts
  -> rebuild homepage
```

The GitHub `Update Dataset` workflow should fetch and rebuild data. The GitHub `Editorial` workflow is manual-only and defaults to fake mode for smoke testing; do not rely on it for final daily publication unless the user explicitly asks for an OpenAI Agents SDK run.

7. Review local audit files:

- `candidate_pool.json`: Top 8 selectable candidates, near misses, rank lookup, and candidate-pool reasons.
- `selector_input.json`: what local Codex should consider, usually name-sorted so it is not anchored to score order.
- `selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `selection_validation.json`: deterministic checks for pool membership, slot counts, and skipped-higher-ranked explanations.
- `copy_validation.json`: deterministic checks for banned public Chinese abstract terms and other copy-profile gates.
- `reports/editorial/YYYY-MM-DD.md`: human-readable generated report.

Before changing scoring weights, run the POTM calibration gate when labels exist or when Firecrawl can find credible match recognition for the date:

```bash
python scripts/calibrate_potm.py --date YYYY-MM-DD
```

If labels are missing, use the `calibrate-potm-labels` skill and `scripts/discover_potm_evidence.py --date YYYY-MM-DD` to find match-day candidate sources through Firecrawl/Keypool. Use `scripts/search_potm_evidence.py` only for targeted follow-up searches, then add only confirmed labels to `calibration/potm-labels.json`. POTM calibration is a sanity check: if the POTM is outside the model Top 3, pause and explain whether this is a known model gap, a one-off narrative choice, or a data extraction issue. Do not silently bend Editor's Choices around POTM.

If output is poor, repair the source of the problem: scoring config, candidate-pool profile, selector profile, copy profile, prompts, or deterministic validation. Avoid hand-editing compiled frontend JSON.

8. Review gates before accepting output:

- Does `selection_validation.json` pass?
- Did local Codex explain selected players and skipped higher-ranked candidates?
- Is every selected player present in the candidate pool?
- Does the whole slate avoid overconcentrating one match unless the extra card has an extraordinary independent reason?
- Does each card have a distinct football angle?
- Are there at most two or three key facts per body?
- Does `copy_validation.json` pass?
- Does the copy avoid implying video review, media ratings, or unsupported tactical observation?
- Does the homepage show the latest generated cards?

For ad hoc wording audits, use `rg -n "<terms>" site/editorial/YYYY-MM-DD site/index.html` against generated artifacts. Do not turn broad phrase scans over docs or source files into unit tests.

9. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

10. Follow `pr-policy.md` for publication.
