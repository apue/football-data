# FIFA PMSR Data

Daily-refreshable SQLite data and reproducible examples extracted from publicly available FIFA Training Centre Post Match Summary Report (PMSR) PDFs.

## What This Is

This project turns FIFA Training Centre PMSR reports into a structured SQLite database for football analysis. The goal is to make cross-game analysis easy: fastest players, longest-running players, shot lists, team comparison funnels, and hidden contribution candidates such as off-ball receivers, line-breaking progressors, attacking threats, and defensive contributors.

## Data Source and Attribution

Original PMSR reports are publicly linked from the FIFA Training Centre Match Report Hub. The source documents remain the property of FIFA and the relevant rights holders. This repository provides extracted, attributed, structured data for research and analysis.

Each extracted record is traceable through source metadata stored in SQLite and in `manifests/`:

- source URL
- source filename
- PMSR version, including `V2`/`V3` updates when present
- document SHA-256 and file size
- discovered/fetched timestamps
- parser version
- extraction timestamp

By default this repository does not redistribute original PDF files. Local PDF caches under `raw/**/*.pdf` are ignored by git.

## Outputs

- `data/latest.sqlite` - latest generated SQLite database
- `manifests/latest-run.json` - latest update status
- `manifests/sources.json` - source document manifest
- `manifests/discovered-sources.json` - current FIFA hub discovery result
- `manifests/update-events.json` - new matches, version updates, downloads, and failures
- `examples/*.sql` - reusable SQL examples
- `notebooks/*.ipynb` - notebook-style demo examples
- `reports/editorial/*.md` - human-readable Editor's Choices reports when published
- `calibration/potm-labels.json` - optional weak labels for Player of the Match calibration
- `calibration/reports/*.md` - POTM/model rank-diff reports when calibration is run
- `calibration/evaluation/*.md` - POTM evidence quality and calibration-readiness reports
- `site/editorial/` - rendered Editor's Choices JSON/HTML for the demo site
- `site/editorial/*/fact_bank.zh.json` - raw Chinese fact bank for from-scratch Chinese sports-editor copy
- `site/editorial/*/brief.zh.json` and `brief.en.json` - legacy Chinese draft brief plus English editorial input
- `.agents/skills/publish-editors-choices/` - repo-scoped Codex skill for the editorial publishing workflow
- `.agents/skills/calibrate-potm-labels/` - repo-scoped Codex skill for Firecrawl-assisted scoring calibration
- `.agents/skills/evaluate-potm-workflow/` - repo-scoped Codex skill for POTM workflow evaluation
- GitHub Pages demo generated from the latest SQLite database: https://apue.github.io/football-data/

## Current SQLite Coverage

The generated database currently includes:

- match metadata, source provenance, and extraction runs
- team-level key statistics
- shot detail tables
- player physical data
- player lineup appearances from the match summary page
- raw minute markers associated with lineup rows
- player in-possession distributions, including passes, line breaks, ball progressions, take-ons, step-ins, attempts, and goals
- player offers and receptions, including offer movement types
- player out-of-possession actions, including tackles, blocks, interceptions, pressing, duels, regains, and interruptions

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/update_dataset.py
sqlite3 data/latest.sqlite < examples/top_fastest_players.sql
sqlite3 data/latest.sqlite < examples/top_attacking_threats.sql
python scripts/generate_editorial.py --date 2026-06-16
python scripts/render_editorial.py --date 2026-06-16
python scripts/check_status.py
```

## Editor's Choices

Editor's Choices are data-informed editorial picks generated from structured PMSR evidence. They are not official FIFA awards. The generator selects candidates from the SQLite database, writes auditable evidence, and produces `fact_bank.zh.json`, `brief.zh.json`, `brief.en.json`, and an English/Chinese Markdown draft brief. Final Chinese copy should be written from `fact_bank.zh.json` as fresh Chinese sports copy, then reviewed for translationese and factual drift. Final English copy should be written separately from `brief.en.json` plus `evidence.json`. The two languages should make the same judgment, but neither should be a translation of the other.

Run:

```bash
python scripts/generate_editorial.py --date YYYY-MM-DD
```

Omit `--date` to use the latest available local match date in the database. Review and rewrite the human-readable output at `reports/editorial/YYYY-MM-DD.md`.

If the Markdown copy changes, compile it back to frontend JSON/HTML:

```bash
python scripts/render_editorial.py --date YYYY-MM-DD
```

The compiled frontend artifacts are written to `site/editorial/`, and the homepage is rebuilt with the latest cards.

## POTM Calibration

POTM calibration compares external Player of the Match labels with this project's per-match model ranking. It is a weak-label sanity check, not an official scoring input. If a confirmed POTM is outside the model Top 3, the report flags the miss so the scoring weights can be reviewed for patterns such as late winners, decisive goal involvements, defensive performances, or extraction/name-matching issues.

Optional Firecrawl search is supported through Keypool for evidence discovery:

```bash
python scripts/discover_potm_evidence.py --date YYYY-MM-DD
python scripts/evaluate_potm_workflow.py --date YYYY-MM-DD
python scripts/search_potm_evidence.py "FIFA 2026 Match 21 Ghana Panama Player of the Match" --limit 5
python scripts/calibrate_potm.py --date YYYY-MM-DD
```

Keep `KEYPOOL_KEY` and `KEYPOOL_URL` in local `.env.local`. Do not commit secrets or use external pages as a direct replacement for structured PMSR evidence.

## Update Policy

The intended automated update schedule is daily around 12:00 Asia/Shanghai. The update pipeline:

1. fetches the FIFA Match Report Hub,
2. discovers all PMSR PDF links and resolves the active highest version per match,
3. blocks suspicious discovery regressions,
4. downloads only missing active documents,
5. extracts structured records,
6. rebuilds `data/latest.sqlite`,
7. validates outputs,
8. regenerates demo pages and update status.

Failures are reported in `manifests/latest-run.json`, `manifests/update-events.json`, and GitHub Actions logs. A Codex/agent-assisted recovery flow can inspect failures, use browser diagnostics when static discovery breaks, update discovery/parser code, and push a corrective change.

## Example Questions

- Who are the top 5 fastest players?
- Who covered the most total distance?
- Which teams generated the most xG?
- Which shots were goals or on target?
- Which players created the strongest combined attacking threat?
- Which players were the best line-breaking progressors?
- Which players were the most active off-ball receivers?
- Which players made the strongest defensive contribution?
- Which players did the daily Editor's Choices select, and why?

## Limitations

PMSR PDFs are presentation reports, not complete event or tracking feeds. The parser focuses on reliable text/table extraction and uses PDF text object coordinates for wide player tables where plain text loses zero-valued cells. Raw minute markers from the match summary page are preserved, but icon semantics such as whether a marker is a goal, card, or substitution are not inferred unless a table makes that explicit.
