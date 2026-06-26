# FIFA PMSR Data

Daily-refreshable SQLite data and reproducible examples extracted from publicly available FIFA Training Centre Post Match Summary Report (PMSR) PDFs.

## What This Is

This project turns FIFA Training Centre PMSR reports into a structured SQLite database for football analysis. The goal is to make cross-game analysis easy: fastest players, longest-running players, shot lists, team comparison funnels, and hidden contribution candidates such as off-ball receivers, line-breaking progressors, attacking threats, and defensive contributors. FIFA public match timeline data is used as a supplemental official source for event-level goals and assists that are not present in the PMSR PDFs.

## Data Source and Attribution

Original PMSR reports are publicly linked from the FIFA Training Centre Match Report Hub. The source documents remain the property of FIFA and the relevant rights holders. This repository provides extracted, attributed, structured data for research and analysis.

## Legal Notice

The update pipeline uses publicly accessible FIFA Training Centre match-report pages, PMSR PDF links, and public match timeline data. No private credentials, login, or special authorization is required to run the fetch workflow as implemented here.

This repository keeps attribution and source provenance in the generated data. It does not redistribute original PDF files by default; local PDF caches under `raw/**/*.pdf` are ignored by git. Users should follow the upstream source terms and should not bypass access controls, rate limits, or other technical restrictions.

Each extracted record is traceable through source metadata stored in SQLite and in `manifests/`:

- source URL
- source filename
- PMSR version, including `V2`/`V3` updates when present
- document SHA-256 and file size
- discovered/fetched timestamps
- parser version
- extraction timestamp

Assists are not available as structured fields in the PMSR PDFs. The pipeline supplements them from FIFA's public match timeline API and stores the raw event provenance separately from PMSR-derived tables.

## Outputs

- `data/latest.sqlite` - latest generated SQLite database
- `manifests/latest-run.json` - latest update status
- `manifests/sources.json` - source document manifest
- `manifests/discovered-sources.json` - current FIFA hub discovery result
- `manifests/update-events.json` - new matches, version updates, downloads, and failures
- `manifests/editorial-v2-run.json` - latest local editorial packet/compile status
- `examples/*.sql` - reusable SQL examples
- `notebooks/*.ipynb` - notebook-style demo examples
- `reports/editorial/*.md` - human-readable Editor's Choices reports when published
- `agent-runs/*/*.json` - local editor audit files, including rankings, candidate pools, selector input, decisions, and validation
- `config/editorial/` - active editorial experiment registry, selector profiles, candidate-pool profiles, and copy profiles
- `site/editorial/` - rendered Editor's Choices JSON/HTML for the demo site
- `.agents/skills/publish-editors-choices/` - repo-scoped Codex skill for the editorial publishing workflow
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
- detailed player line-break splits by unit line, direction, and distribution type
- player offers and receptions, including offer movement types
- player out-of-possession actions, including tackles, blocks, interceptions, pressing, duels, regains, and interruptions
- FIFA public match timeline mappings, raw events, and `goal_involvements` with scorer/assister pairs

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/update_dataset.py
python scripts/backfill_fifa_timelines.py
sqlite3 data/latest.sqlite < examples/top_fastest_players.sql
sqlite3 data/latest.sqlite < examples/top_attacking_threats.sql
sqlite3 data/latest.sqlite < examples/top_goal_involvements.sql
python scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json
python scripts/inspect_editorial_day.py --date YYYY-MM-DD --json
python scripts/check_status.py
```

## Editor's Choices

Editor's Choices are data-informed editorial picks generated from structured PMSR evidence. They are not official FIFA awards. The production path is local-first: deterministic scoring builds a rich candidate pool, local Codex acts as the editor, and deterministic validation compiles the approved `selection_decision.json`, `copy.json`, and `editorial_review.json` into static site artifacts.

The active experiment is resolved from `config/editorial/production.json`. Each experiment pins the scoring config, candidate-pool profile, selector profile, copy profiles, selection slots, and candidate ordering strategy. This keeps experimentation visible without inventing a generic workflow framework.

The default scoring config is `config/scoring/v0.4.json`. It keeps the role-style performance scores and adds a structured impact layer for goals and official assists that change the match state and match story: opening goals, equalisers, go-ahead goals, contextual match-winning goals, late goals, stoppage-time goals, late match-winning goals, comeback equalisers, comeback winners, only-goal winners, assists, goal involvements, braces, hat-tricks, and substitute scoring bursts. These features are derived from the PMSR shot table, lineup status, final scoreline, deterministic match-flow reconstruction, and FIFA public match timeline goal-involvement records. Media opinions are not scoring inputs.

Prepare the deterministic local handoff packet:

```bash
python scripts/prepare_editorial_packet.py --date YYYY-MM-DD --json
```

Build the deterministic editorial fact pack before local review:

```bash
python scripts/inspect_editorial_day.py --date YYYY-MM-DD --json
```

The fact pack is written under `agent-runs/YYYY-MM-DD/` as `editorial_fact_pack.json` and `editorial_fact_pack.md`. It captures match scores, goal timelines, own goals, official assists, team pressure, goalkeeper checks, direct-impact candidates, high-ranked metric-led candidates, and common reader traps. Use it before writing selection/copy/review; if a needed fact is missing, improve this script rather than relying on one-off SQL.

Then write these local editor artifacts under `agent-runs/YYYY-MM-DD/`:

- `selection_decision.json`
- `copy.json`
- `editorial_review.json`

Compile the approved local result:

```bash
python scripts/compile_local_editorial.py --date YYYY-MM-DD --json
```

The compiled frontend artifacts are written to `site/editorial/`, and the homepage is rebuilt with the latest cards. Audit files are written under `agent-runs/YYYY-MM-DD/`, including `rankings.json`, `candidate_pool.json`, `selector_input.json`, `editorial_fact_pack.json`, `editorial_fact_pack.md`, `selection_decision.json`, `selection_validation.json`, `copy_validation.json`, `editorial_review_payload.json`, `editorial_review.json`, `editorial_review_validation.json`, and `run.json`.

## Editorial Automation

GitHub Actions fetches and rebuilds the deterministic dataset, regenerates the homepage, and deploys GitHub Pages. Editorial publication is intentionally manual-first: generate the local packet, review the result locally, compile the approved static artifacts, then publish through a PR.

Future API editor agents should use `docs/editorial-api-agent-spec.md` and run in shadow mode before replacing local Codex output.

## Update Policy

The intended automated update schedule is daily around 12:00 Asia/Shanghai. The update pipeline:

1. fetches the FIFA Match Report Hub,
2. discovers all PMSR PDF links and resolves the active highest version per match,
3. blocks suspicious discovery regressions,
4. downloads only missing active documents,
5. extracts structured records,
6. rebuilds `data/latest.sqlite`,
7. backfills FIFA public match timeline events for goals and assists,
8. validates outputs,
9. regenerates demo pages and update status,
10. deploys the rebuilt static site to GitHub Pages.

Failures are reported in `manifests/latest-run.json`, `manifests/update-events.json`, and GitHub Actions logs. A Codex/agent-assisted recovery flow can inspect failures, use browser diagnostics when static discovery breaks, update discovery/parser code, and push a corrective change.

## Example Questions

- Who are the top 5 fastest players?
- Who covered the most total distance?
- Which teams generated the most xG?
- Which shots were goals or on target?
- Which players created the strongest combined attacking threat?
- Which players have the most goals plus assists?
- Which players were the best line-breaking progressors?
- Which players were the most active off-ball receivers?
- Which players made the strongest defensive contribution?
- Which players did the daily Editor's Choices select, and why?

## Limitations

PMSR PDFs are presentation reports, not complete event or tracking feeds. The parser focuses on reliable text/table extraction and uses PDF text object coordinates for wide player tables where plain text loses zero-valued cells. Raw minute markers from the match summary page are preserved, but icon semantics such as whether a marker is a goal, card, or substitution are not inferred unless a table makes that explicit.
