# FIFA PMSR Data

Daily-refreshable SQLite data and reproducible examples extracted from publicly available FIFA Training Centre Post Match Summary Report (PMSR) PDFs.

## What This Is

This project turns FIFA Training Centre PMSR reports into a structured SQLite database for football analysis. The goal is to make cross-game analysis easy: fastest players, longest-running players, shot lists, team comparison funnels, and hidden contribution candidates.

## Data Source and Attribution

Original PMSR reports are publicly available from FIFA Training Centre. The source documents remain the property of FIFA and the relevant rights holders. This repository provides extracted, attributed, structured data for research and analysis.

Each extracted record is traceable through source metadata stored in SQLite and in `manifests/`:

- source URL
- source filename
- document SHA-256
- discovered/fetched timestamp
- parser version

By default this repository does not redistribute original PDF files. Local PDF caches under `raw/*.pdf` are ignored by git.

## Outputs

- `data/latest.sqlite` - latest generated SQLite database
- `manifests/latest-run.json` - latest update status
- `manifests/sources.json` - source document manifest
- `examples/*.sql` - reusable SQL examples
- `notebooks/*.ipynb` - notebook-style demo examples
- GitHub Pages demo generated from the latest SQLite database

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/update_dataset.py
sqlite3 data/latest.sqlite < examples/top_fastest_players.sql
```

## Update Policy

The intended automated update schedule is daily around 12:00 Asia/Shanghai. The update pipeline:

1. discovers known/public PMSR source documents,
2. downloads only missing or changed documents,
3. extracts structured records,
4. rebuilds `data/latest.sqlite`,
5. validates outputs,
6. regenerates demo pages and update status.

Failures are reported in `manifests/latest-run.json` and GitHub Actions logs. A Codex/agent-assisted recovery flow can inspect failures, update source manifests or parsers, and push a corrective change.

## Example Questions

- Who are the top 5 fastest players?
- Who covered the most total distance?
- Which teams generated the most xG?
- Which shots were goals or on target?
- Which players may be hidden progression or workload candidates as more matches are added?

## Limitations

PMSR PDFs are presentation reports, not complete event or tracking feeds. The first implementation focuses on reliable text/table extraction: match metadata, team key stats, shots, and player physical data. Some pitch maps can be enriched later using PDF text objects and vector drawing objects.

