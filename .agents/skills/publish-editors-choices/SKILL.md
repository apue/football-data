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

- Treat `scripts/run_editorial_loop.py` as the default publication entrypoint.
- Treat `scripts/generate_editorial.py` as the deterministic evidence-and-draft generator underneath the loop.
- Treat `reports/editorial/YYYY-MM-DD.md` as the human-readable editorial source.
- Treat generated Markdown as a draft brief, not publishable copy.
- Let Codex revise Markdown from generated evidence; do not invent facts outside `evidence.json`/SQLite.
- Rewrite Chinese and English independently from the same evidence.
- Use `fact_bank.zh.json` as the primary Chinese input. Use `brief.zh.json` only for legacy diagnostics, not as the Chinese writing base.
- Write Chinese as a from-scratch Chinese sports editor from facts, then review it with a strict `qu-ai-wei` style pass; use `humanizer-zh` style repair only for cards that fail review.
- Use `brief.en.json` plus `evidence.json` for English copy; do not cross-feed language outputs.
- Generate 3-5 Chinese title candidates from the fact bank, reject translationese, then write the selected title/body.
- Run an editorial review pass before rendering: judge natural language, distinct angles, evidence support, and no implied video review.
- Keep the explicit Review -> Repair -> Validate audit trail under `agent-runs/`.
- Run the POTM calibration gate with `calibrate-potm-labels` when labels or external evidence are available for the date.
- Run `scripts/render_editorial.py` after Markdown edits to compile frontend JSON/HTML.
- Use local match dates from `matches.match_date`, not Beijing date or workflow run time.
- Generate both English and Chinese copy. They should express the same judgment but do not need to be literal translations.
- Prefer a short, human editorial note over metric dumping.
- Do not push directly to `main` for editorial content unless the user explicitly asks.
