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
python scripts/check_status.py
```

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

## Limitations

PMSR PDFs are presentation reports, not complete event or tracking feeds. The parser focuses on reliable text/table extraction and uses PDF text object coordinates for wide player tables where plain text loses zero-valued cells. Raw minute markers from the match summary page are preserved, but icon semantics such as whether a marker is a goal, card, or substitution are not inferred unless a table makes that explicit.
