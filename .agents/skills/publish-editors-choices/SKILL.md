---
name: publish-editors-choices
description: Use when the user asks to publish, generate, review, check, or update football-data Editor's Choices, daily picks, 每日精选, Player of the Day, hidden gems, or match-day editorial reports.
---

# Publish Editor's Choices

Use this repository workflow to turn structured PMSR evidence into bilingual, data-informed editorial picks.

## Required References

Read these before acting:

- `references/workflow.md` for the operational sequence and commands.
- `references/narrative-style.md` before writing or revising English/Chinese copy.
- `references/pr-policy.md` before pushing or opening a PR.

## Core Rules

- Treat `scripts/run_editorial_queue.py` as the default publication entrypoint.
- Use `scripts/run_editorial_queue.py --date YYYY-MM-DD` for targeted local backfills.
- Use `scripts/run_editorial_v2.py --date YYYY-MM-DD` only for low-level local debugging.
- Treat `reports/editorial/YYYY-MM-DD.md` as the human-readable generated report.
- Treat `agent-runs/YYYY-MM-DD/` as the primary run audit directory.
- The production experiment is `ai_rerank_selection_v1`: deterministic scoring builds the candidate pool, an AI selection editor reranks only that pool, validation enforces pool membership and skipped-higher-ranked explanations, and separate English/Chinese copy editor calls write final cards.
- LLM working nodes use the OpenAI Agents SDK with structured outputs. Keep scoring, candidate-pool construction, selection validation, artifact writing, and publishing deterministic in Python.
- Let Codex repair code, scoring, registry config, prompts, or copy profiles when output fails review; do not hand-edit compiled JSON.
- Generate both English and Chinese copy from the same selected candidate evidence packet. They should express the same judgment but do not need to be literal translations.
- Run the workflow validation gates before accepting output: `selection_validation.json`, copy warnings, and homepage/site artifacts.
- Run the POTM calibration gate with `calibrate-potm-labels` when labels or external evidence are available for the date.
- Use local match dates from `matches.match_date`, not Beijing date or workflow run time.
- Prefer a short, human editorial note over metric dumping.
- Do not push directly to `main` for editorial content unless the user explicitly asks.
