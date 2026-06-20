# Changelog

## 2026-06-20 - Editorial Path Cleanup

Removed obsolete editorial code paths after the agent workflow became the single publication path:

- Removed the placeholder `editorial_loop` layer and its CLI/tests.
- Removed manual `generate_editorial` and `render_editorial` CLI wrappers.
- Removed `brief.zh.json` generation and legacy Chinese draft helpers; Chinese generation now uses `fact_bank.zh.json`.
- Removed early `v0.1`/`v0.2` scoring configs and tightened runtime scoring to the current `v0.3` config.
- Removed root-level raw-PDF fallback logic so active sources use competition-scoped raw cache paths.

## 2026-06-19 - Autonomous Editorial Workflow

Added CI automation for Editor's Choices after dataset updates:

- Added `.github/workflows/editorial.yml`, triggered by the successful `Update Dataset` workflow and by manual dispatch.
- Added `scripts/run_editorial_queue.py` and `football_data.editorial_queue_runner` to process pending editorial dates.
- Added `editorial_input_hash` to editorial artifacts so source/PMSR/scoring changes can trigger reruns.
- Added `manifests/editorial-queue.json` and `manifests/editorial-run.json` status outputs.
- Added `.env.example` with blank OpenAI, model, and Firecrawl/Keypool placeholders.
- Updated agent config loading so GitHub Actions repository secrets work through process environment variables.

## 2026-06-19 - Editorial Loop and Detailed Line Breaks

Added a review-repair-validate loop for daily Editor's Choices and expanded player progression data:

- Bumped SQLite schema to version 4.
- Added `player_line_breaks` with detailed player line-break splits by unit line, direction, and distribution type.
- Added progression and hidden-gem benchmark helpers so pass-only line-break volume is not overvalued against pressure-breaking or attacking-third actions.
- Added `scripts/run_editorial_loop.py` and `football_data.editorial_loop` to write explicit loop audit artifacts under `agent-runs/`.
- Updated the 2026-06-18 selection guard so heavy-loss defensive picks and duplicate-team hidden gems are repaired before publication.
- Updated the repo-scoped Editor's Choices skill and docs to use the loop as the default publication path.

## 2026-06-19 - Impact-Aware Editorial Scoring

Improved the editorial scoring layer for decisive match actions:

- Added `config/scoring/v0.2.json` as the default Editor's Choices scoring config.
- Added structured impact features for opening, equalizing, go-ahead, match-winning, late, stoppage-time, and late match-winning goals.
- Updated editorial evidence chips and draft facts so decisive goals can surface without turning the copy into a metric list.
- Updated 2026-06-17 Editor's Choices output to surface Caleb YIRENKYI and Luis DIAZ as Player of the Day candidates.
- Updated POTM calibration defaults and tests while preserving `v0.1` as a historical pre-impact comparison point.

## 2026-06-18 - Editor's Choices Workflow

Added the first editorial publishing workflow:

- Added repo-scoped Codex skill `.agents/skills/publish-editors-choices`.
- Added configurable scoring weights in `config/scoring/v0.1.json`.
- Added `scripts/generate_editorial.py` to generate JSON, HTML, Markdown, and homepage cards.
- Added `scripts/render_editorial.py` so human-readable Markdown can be compiled into frontend JSON/HTML.
- Added bilingual English/Chinese editorial narratives based on structured PMSR evidence.
- Added tests for editorial report generation, artifacts, homepage integration, and project skill presence.

## 2026-06-17 - Player Insight Tables

Expanded the player-level dataset:

- Bumped SQLite schema to version 3.
- Added lineup-derived `player_appearances` and raw `player_event_markers`.
- Added individual in-possession distributions, offers/receptions, and out-of-possession action tables.
- Switched wide player-table extraction to PDF text object coordinates so zero-valued cells stay aligned.
- Added role-style demo leaderboards for attacking threats, progressors, off-ball receivers, and defensive contributors.
- Expanded the current generated dataset to 20 active PMSR sources from the FIFA hub.

## 2026-06-17 - Hub Discovery

Hub-driven dataset update:

- Replaced hard-coded PMSR URLs with FIFA Match Report Hub discovery.
- Added version-aware source manifests for active and superseded PMSR links.
- Bumped SQLite schema to version 2 with source/version provenance and row-level `source_id`.
- Added structured update events, failure codes, and status checking.
- Expanded the current generated dataset from 3 to the active hub coverage when the workflow runs.

## 2026-06-17 - Initial Scaffold

Initial dataset scaffold:

- Added parser and SQLite loader for local FIFA PMSR PDF cache.
- Added three source matches from local raw cache:
  - M01 Mexico 2-0 South Africa
  - M02 Korea Republic 2-1 Czechia
  - M07 Brazil 1-1 Morocco
- Added SQL examples and static demo generation.
