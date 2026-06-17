# FIFA PMSR Data

Daily-refreshable SQLite data and reproducible examples extracted from publicly available FIFA Training Centre Post Match Summary Report (PMSR) PDFs.

## What This Is

This project turns FIFA Training Centre PMSR reports into a structured SQLite database for football analysis. The goal is to make cross-game analysis easy: fastest players, longest-running players, shot lists, team comparison funnels, and hidden contribution candidates.

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

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/update_dataset.py
sqlite3 data/latest.sqlite < examples/top_fastest_players.sql
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
- Which players may be hidden progression or workload candidates as more matches are added?

## Limitations

PMSR PDFs are presentation reports, not complete event or tracking feeds. The first implementation focuses on reliable text/table extraction: match metadata, team key stats, shots, and player physical data. Some pitch maps can be enriched later using PDF text objects and vector drawing objects.
