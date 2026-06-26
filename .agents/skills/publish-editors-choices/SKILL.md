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
- Immediately run `scripts/inspect_editorial_day.py --date YYYY-MM-DD` after preparing the packet. Use `editorial_fact_pack.json` / `.md` for goal timelines, own goals, assists, team pressure, goalkeeper checks, and metric-led candidate traps before writing selection/copy/review.
- Let local Codex write `agent-runs/YYYY-MM-DD/selection_decision.json`, `agent-runs/YYYY-MM-DD/copy.json`, and `agent-runs/YYYY-MM-DD/editorial_review.json`, then publish with `scripts/compile_local_editorial.py --date YYYY-MM-DD`.
- Treat `reports/editorial/YYYY-MM-DD.md` as the human-readable generated report.
- Treat `agent-runs/YYYY-MM-DD/` as the primary run audit directory.
- The production experiment is `ai_rerank_reader_loop_v5`, using the `ai_rerank_selection_v1` workflow variant: deterministic scoring builds the candidate pool, local Codex reranks only that pool, validation enforces pool membership, a 3-6 public-card count range, award limits, slate balance, and skipped-higher-ranked explanations, local English/Chinese copy is written from selected evidence packets, and the `reader_intuition_loop_v2` critic/revision review must pass before publishing.
- Keep scoring, candidate-pool construction, selection validation, artifact writing, and publishing deterministic in Python. The retired cloud editorial queue must not be used for daily publication.
- Let Codex repair code, scoring, registry config, prompts, copy profiles, or local selection/copy files when output fails review; do not hand-edit compiled frontend JSON.
- Generate both English and Chinese copy from the same selected candidate evidence packet. They should express the same judgment but do not need to be literal translations.
- Treat `config/editorial/style_calibration/zh.jsonl` as the durable store for recurring Chinese copy taste feedback. Add curated bad/better examples there instead of relying on chat memory or turning every dislike into a banned term.
- Run the workflow validation gates before accepting output: `selection_validation.json`, `copy_validation.json`, `editorial_review_validation.json`, copy warnings, and homepage/site artifacts.
- Use local match dates from `matches.match_date`, not Beijing date or workflow run time.
- Do not start with ad hoc SQL for editorial review. If the fact pack is missing a recurring fact, improve `scripts/inspect_editorial_day.py` instead.
- Prefer a short, human editorial note over metric dumping.
- Do not push directly to `main` for editorial content unless the user explicitly asks.
