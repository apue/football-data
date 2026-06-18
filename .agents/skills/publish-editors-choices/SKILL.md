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

- Treat `scripts/generate_editorial.py` as the deterministic evidence generator.
- Let Codex revise the narrative from the generated evidence; do not invent facts outside the JSON/SQLite evidence.
- Use local match dates from `matches.match_date`, not Beijing date or workflow run time.
- Generate both English and Chinese copy. They should express the same judgment but do not need to be literal translations.
- Prefer a short, human editorial note over metric dumping.
- Do not push directly to `main` for editorial content unless the user explicitly asks.
