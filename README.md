# FIFA PMSR Data

Daily-refreshable SQLite data and reproducible examples extracted from publicly available FIFA Training Centre Post Match Summary Report (PMSR) PDFs.

## What This Is

This project turns FIFA Training Centre PMSR reports into a structured SQLite database for football analysis. The goal is to make cross-game analysis easy: fastest players, longest-running players, shot lists, team comparison funnels, and hidden contribution candidates such as off-ball receivers, line-breaking progressors, attacking threats, and defensive contributors. FIFA public match timeline data is used as a supplemental official source for event-level goals and assists that are not present in the PMSR PDFs.

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

Assists are not available as structured fields in the PMSR PDFs. The pipeline supplements them from FIFA's public match timeline API and stores the raw event provenance separately from PMSR-derived tables.

## Outputs

- `data/latest.sqlite` - latest generated SQLite database
- `manifests/latest-run.json` - latest update status
- `manifests/sources.json` - source document manifest
- `manifests/discovered-sources.json` - current FIFA hub discovery result
- `manifests/update-events.json` - new matches, version updates, downloads, and failures
- `manifests/editorial-queue.json` - pending Editor's Choices dates after data updates
- `manifests/editorial-run.json` - latest autonomous editorial workflow status
- `examples/*.sql` - reusable SQL examples
- `notebooks/*.ipynb` - notebook-style demo examples
- `reports/editorial/*.md` - human-readable Editor's Choices reports when published
- `agent-runs/*.json` - editor agent run audits
- `calibration/potm-labels.json` - optional weak labels for Player of the Match calibration
- `calibration/reports/*.md` - POTM/model rank-diff reports when calibration is run
- `calibration/evaluation/*.md` - POTM evidence quality and calibration-readiness reports
- `site/editorial/` - rendered Editor's Choices JSON/HTML for the demo site
- `site/editorial/*/fact_bank.zh.json` - raw Chinese fact bank for from-scratch Chinese sports-editor copy
- `site/editorial/*/brief.en.json` - English editorial input
- `.agents/skills/publish-editors-choices/` - repo-scoped Codex skill for the editorial publishing workflow
- `.agents/skills/calibrate-potm-labels/` - repo-scoped Codex skill for Firecrawl-assisted scoring calibration
- `.agents/skills/evaluate-potm-workflow/` - repo-scoped Codex skill for POTM workflow evaluation
- `.env.example` - blank local/GitHub secret template for editorial agent and Firecrawl settings
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
python scripts/run_editorial_queue.py --fake --no-research --max-dates 1
python scripts/check_status.py
```

## Editor's Choices

Editor's Choices are data-informed editorial picks generated from structured PMSR evidence. They are not official FIFA awards. The autonomous path selects candidates from the SQLite database, then runs a lightweight editorial state graph: build evidence, optional research, writer draft, draft fact check, final editor, final validation, frontend compile, and homepage rebuild. LLM working nodes run through the OpenAI Agents SDK with structured outputs; deterministic Python nodes keep scoring, evidence, validation, and publishing reproducible. Chinese copy is generated from `fact_bank.zh.json` as fresh Chinese sports copy. English copy is generated separately from `brief.en.json` plus `evidence.json`. The two languages should make the same judgment, but neither should be a translation of the other.

The default scoring config is `config/scoring/v0.4.json`. It keeps the role-style performance scores and adds a structured impact layer for goals that change the match state and match story: opening goals, equalisers, go-ahead goals, match-winning goals, late goals, stoppage-time goals, late match-winning goals, comeback equalisers, comeback winners, only-goal winners, braces, hat-tricks, and substitute scoring bursts. These features are derived from the PMSR shot table, lineup status, final scoreline, and deterministic match-flow reconstruction. POTM labels and media opinions are not scoring inputs.

Run the autonomous queue used by GitHub Actions:

```bash
python scripts/run_editorial_queue.py
```

For a targeted local run on one match date:

```bash
python scripts/run_editorial_agent.py --date YYYY-MM-DD
```

For a deterministic smoke test without credentials:

```bash
python scripts/run_editorial_queue.py --fake --no-research --max-dates 1
```

The compiled frontend artifacts are written to `site/editorial/`, and the homepage is rebuilt with the latest cards.

## Editorial Automation

`.github/workflows/editorial.yml` runs after the `Update Dataset` workflow succeeds and can also be started manually. It checks `manifests/editorial-queue.json`, runs the Agents SDK-backed editorial state graph for pending match dates, commits published editorial outputs with `[skip ci]`, and deploys GitHub Pages.

Configure repository secrets with these names when you want the cloud workflow to publish new editorial copy:

```text
OPENAI_API_KEY
KEYPOOL_KEY
```

The default OpenAI-compatible base URL is `https://api.siliconflow.cn/v1`, and default model routing is listed in `.env.example`. Add repository variables only when you want to override those defaults:

```text
OPENAI_BASE_URL
EDITORIAL_ZH_WRITER_MODEL
EDITORIAL_ZH_EDITOR_MODEL
EDITORIAL_EN_WRITER_MODEL
EDITORIAL_EN_EDITOR_MODEL
EDITORIAL_FACT_CHECK_MODEL
EDITORIAL_AGENT_TIMEOUT_SECONDS
EDITORIAL_AGENT_MAX_CONCURRENCY
EDITORIAL_AGENT_MAX_ATTEMPTS
KEYPOOL_URL
```

Missing OpenAI credentials do not publish drafts; the workflow writes `manifests/editorial-run.json` with `needs_credentials` and exits cleanly so the data update pipeline stays healthy. Per-card writer/editor calls retry with `EDITORIAL_AGENT_MAX_ATTEMPTS`; if a single card still fails, the workflow records a warning and falls back to the latest available draft for that card instead of blocking the whole match day. `KEYPOOL_URL` is your KeyPool base URL and is required only for Firecrawl-backed evidence discovery; missing Firecrawl configuration does not block PMSR-only publishing.

## POTM Calibration

POTM calibration compares external Player of the Match labels with this project's per-match model ranking. It is a weak-label sanity check, not an official scoring input. If a confirmed POTM is outside the model Top 3, the report flags the miss so the scoring weights can be reviewed for patterns such as late winners, decisive goal involvements, defensive performances, or extraction/name-matching issues. Current calibration defaults to `config/scoring/v0.4.json`.

Optional Firecrawl search is supported through Keypool for evidence discovery:

```bash
python scripts/discover_potm_evidence.py --date YYYY-MM-DD
python scripts/evaluate_potm_workflow.py --date YYYY-MM-DD
python scripts/search_potm_evidence.py "FIFA 2026 Match 21 Ghana Panama Player of the Match" --limit 5
python scripts/calibrate_potm.py --date YYYY-MM-DD
```

Keep `OPENAI_API_KEY`, `KEYPOOL_KEY`, and `KEYPOOL_URL` in local `.env.local`. Do not commit secrets or use external pages as a direct replacement for structured PMSR evidence.

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
10. triggers the editorial workflow after the update workflow succeeds.

Failures are reported in `manifests/latest-run.json`, `manifests/update-events.json`, `manifests/editorial-run.json`, and GitHub Actions logs. A Codex/agent-assisted recovery flow can inspect failures, use browser diagnostics when static discovery breaks, update discovery/parser code, and push a corrective change.

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
