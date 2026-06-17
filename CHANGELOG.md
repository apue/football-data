# Changelog

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
