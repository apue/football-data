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

4. Run the autonomous queue:

```bash
python scripts/run_editorial_queue.py
```

For a targeted local backfill on one date:

```bash
python scripts/run_editorial_queue.py --date YYYY-MM-DD
```

For deterministic local smoke testing without OpenAI credentials:

```bash
python scripts/run_editorial_queue.py --date YYYY-MM-DD --fake --no-research --json
```

For low-level v2 debugging:

```bash
python scripts/run_editorial_v2.py --date YYYY-MM-DD --fake --no-research --json
```

Outputs:

- `manifests/editorial-queue.json`
- `manifests/editorial-run.json`
- `manifests/editorial-v2-run.json`
- `reports/editorial/YYYY-MM-DD.md`
- `agent-runs/YYYY-MM-DD/rankings.json`
- `agent-runs/YYYY-MM-DD/candidate_pool.json`
- `agent-runs/YYYY-MM-DD/selector_input.json`
- `agent-runs/YYYY-MM-DD/selection_decision.json`
- `agent-runs/YYYY-MM-DD/selection_validation.json`
- `agent-runs/YYYY-MM-DD/run.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html`

The active production mode is `ai_rerank_selection_v1`:

```text
load active experiment registry
  -> deterministic ranking and rich candidate-pool build
  -> AI selection editor reranks only candidate_pool.selectable_candidates
  -> deterministic selection validation
  -> English and Chinese copy editor calls from selected evidence packets
  -> compile public editorial artifacts
  -> rebuild homepage
```

The queue publishes only the latest data match date by default. Older `editorial_input_hash` changes are recorded as stale and should be backfilled explicitly with `--date`, so historical regeneration never blocks the newest match day. Missing OpenAI credentials should produce `needs_credentials` in `manifests/editorial-run.json`, not a draft publication.

5. Review local audit files:

- `candidate_pool.json`: Top 8 selectable candidates, near misses, rank lookup, and candidate-pool reasons.
- `selector_input.json`: what the AI saw, usually name-sorted so the model is not anchored to score order.
- `selection_decision.json`: selected players, editorial reasons, and reasons for skipping higher-ranked or notable candidates.
- `selection_validation.json`: deterministic checks for pool membership, slot counts, and skipped-higher-ranked explanations.
- `reports/editorial/YYYY-MM-DD.md`: human-readable generated report.

Before changing scoring weights, run the POTM calibration gate when labels exist or when Firecrawl can find credible match recognition for the date:

```bash
python scripts/calibrate_potm.py --date YYYY-MM-DD
```

If labels are missing, use the `calibrate-potm-labels` skill and `scripts/discover_potm_evidence.py --date YYYY-MM-DD` to find match-day candidate sources through Firecrawl/Keypool. Use `scripts/search_potm_evidence.py` only for targeted follow-up searches, then add only confirmed labels to `calibration/potm-labels.json`. POTM calibration is a sanity check: if the POTM is outside the model Top 3, pause and explain whether this is a known model gap, a one-off narrative choice, or a data extraction issue. Do not silently bend Editor's Choices around POTM.

If output is poor, repair the source of the problem: scoring config, candidate-pool profile, selector profile, copy profile, prompts, or deterministic validation. Avoid hand-editing compiled frontend JSON.

6. Review gates before accepting output:

- Does `selection_validation.json` pass?
- Did the AI explain selected players and skipped higher-ranked candidates?
- Is every selected player present in the candidate pool?
- Does each card have a distinct football angle?
- Are there at most two or three key facts per body?
- Does the copy avoid implying video review, media ratings, or unsupported tactical observation?
- Does the homepage show the latest generated cards?

7. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

8. Follow `pr-policy.md` for publication.
