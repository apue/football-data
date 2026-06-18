# POTM Workflow Evaluation

Run this when the user asks to evaluate POTM calibration, evidence quality, Firecrawl search quality, or whether the current weak-label workflow is ready for editorial use.

## Inputs

- SQLite database: `data/latest.sqlite`
- Candidate evidence: `calibration/evidence/YYYY-MM-DD.json`
- Label store: `calibration/potm-labels.json`
- Evaluation output: `calibration/evaluation/YYYY-MM-DD.json`
- Human-readable report: `calibration/evaluation/YYYY-MM-DD.md`
- Optional Firecrawl/Keypool env: `.env.local` with `KEYPOOL_URL` and `KEYPOOL_KEY`

## Commands

Evaluate existing candidates:

```bash
python scripts/evaluate_potm_workflow.py --date YYYY-MM-DD
```

Fetch candidates first, then evaluate:

```bash
python scripts/evaluate_potm_workflow.py --date YYYY-MM-DD --discover --limit 3
```

Use targeted discovery only when the default candidates are weak:

```bash
python scripts/discover_potm_evidence.py --date YYYY-MM-DD --limit 3
python scripts/search_potm_evidence.py "FIFA World Cup 2026 Match 21 Ghana Panama Player of the Match" --limit 5
```

## Rubric

The deterministic rubric reports:

- `match_coverage`: share of matches with at least one candidate.
- `source_quality`: average best candidate score per match.
- `potm_signal_coverage`: share of matches with a candidate that actually mentions POTM or Player of the Match in result content.
- `noise_ratio`: share of video, social, live, replay, interview, or highlights noise. Lower is better.
- `query_quality`: share of matches with official-site and exact POTM query coverage.
- `calibration_alignment`: Top 3 hit rate when confirmed labels exist; omitted when labels are absent.

POTM is a weak label. Use findings to decide whether Codex should keep searching, ask for manual confirmation, or open a scoring-weight experiment.

## Interpretation

- `ready_for_review`: evidence is good enough for human/Codex label confirmation.
- `needs_more_evidence`: run targeted searches or inspect sources before writing labels.
- `weak`: do not write labels or tune weights yet.

Do not change scoring weights from one evaluation. Repeated `missing_potm_signal`, `weak_best_source`, or alignment misses across several days are the trigger for a scoring experiment.
