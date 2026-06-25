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

- Treat `scripts/prepare_editorial_packet.py --date YYYY-MM-DD` as the default local handoff entrypoint.
- Let local Codex write `agent-runs/YYYY-MM-DD/selection_decision.json`, `agent-runs/YYYY-MM-DD/copy.json`, and `agent-runs/YYYY-MM-DD/editorial_review.json`, then publish with `scripts/compile_local_editorial.py --date YYYY-MM-DD`.
- Use `scripts/run_editorial_queue.py --date YYYY-MM-DD --fake --no-research --json` only for deterministic smoke tests or legacy queue checks.
- Use `scripts/run_editorial_v2.py --date YYYY-MM-DD` only for low-level local debugging.
- Treat `reports/editorial/YYYY-MM-DD.md` as the human-readable generated report.
- Treat `agent-runs/YYYY-MM-DD/` as the primary run audit directory.
- The production experiment is `ai_rerank_slate_self_review_v4`, using the `ai_rerank_selection_v1` workflow variant: deterministic scoring builds the candidate pool, local Codex reranks only that pool, validation enforces pool membership, a 3-6 public-card count range, award limits, slate balance, and skipped-higher-ranked explanations, local English/Chinese copy is written from selected evidence packets, and reader-intuition review must pass before publishing.
- Do not reimplement OpenAI Agents SDK capabilities in this local path. Keep scoring, candidate-pool construction, selection validation, artifact writing, and publishing deterministic in Python; keep the OpenAI Agents SDK queue as a manual/legacy runtime.
- Let Codex repair code, scoring, registry config, prompts, copy profiles, or local selection/copy files when output fails review; do not hand-edit compiled frontend JSON.
- Generate both English and Chinese copy from the same selected candidate evidence packet. They should express the same judgment but do not need to be literal translations.
- Run the workflow validation gates before accepting output: `selection_validation.json`, `copy_validation.json`, `editorial_review_validation.json`, copy warnings, and homepage/site artifacts.
- Run the POTM calibration gate with `calibrate-potm-labels` when labels or external evidence are available for the date.
- Use local match dates from `matches.match_date`, not Beijing date or workflow run time.
- Prefer a short, human editorial note over metric dumping.
- Do not push directly to `main` for editorial content unless the user explicitly asks.
