# Changelog

## 2026-06-18 - Editor's Choices Workflow

Added the first editorial publishing workflow:

- Added repo-scoped Codex skill `.agents/skills/publish-editors-choices`.
- Added configurable scoring weights in `config/scoring/v0.1.json`.
- Added `scripts/generate_editorial.py` to generate JSON, HTML, Markdown, and homepage cards.
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
