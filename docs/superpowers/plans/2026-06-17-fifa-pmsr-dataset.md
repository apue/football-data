# FIFA PMSR Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public, daily-refreshable SQLite dataset and demo site from publicly available FIFA Training Centre PMSR PDF reports.

**Architecture:** A small Python package owns PDF discovery/fetching, extraction, SQLite loading, validation, and demo generation. GitHub Actions runs the same deterministic pipeline on push, schedule, and manual dispatch, then publishes generated HTML demos to GitHub Pages.

**Tech Stack:** Python 3.11+, PyMuPDF, pytest, SQLite, GitHub Actions, GitHub Pages.

---

### Task 1: Project Scaffold

**Files:**
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `raw/README.md`

- [ ] Add public project documentation, attribution policy, local setup, and agent operating rules.
- [ ] Ignore raw FIFA PDF files by default while keeping `raw/` available for local cache.
- [ ] Define Python package metadata and runtime/test dependencies.
- [ ] Run `python -m pytest` and confirm tests are still the only failing work.

### Task 2: Core Extraction Tests and Implementation

**Files:**
- Create: `tests/test_extract.py`
- Create: `football_data/extract.py`
- Create: `football_data/model.py`
- Create: `football_data/__init__.py`

- [ ] Write failing tests for match metadata, shots, and physical data extraction from the existing PMSR PDFs.
- [ ] Implement PyMuPDF-based text extraction and deterministic parsers.
- [ ] Run `python -m pytest tests/test_extract.py -v` and confirm passing.

### Task 3: SQLite Loader and CLI

**Files:**
- Create: `tests/test_database.py`
- Create: `football_data/database.py`
- Create: `football_data/pipeline.py`
- Create: `scripts/update_dataset.py`

- [ ] Write failing tests for SQLite schema creation and loading extracted records.
- [ ] Implement schema, replacement load strategy, provenance tables, and update status output.
- [ ] Run `python -m pytest tests/test_database.py -v` and confirm passing.

### Task 4: Examples and Demo Site

**Files:**
- Create: `examples/*.sql`
- Create: `notebooks/*.ipynb`
- Create: `football_data/demo.py`
- Generate: `site/index.html`

- [ ] Add SQL examples for fastest players, longest running players, shot list, and team match stats.
- [ ] Add lightweight notebooks that demonstrate equivalent queries.
- [ ] Implement static HTML demo generation from `data/latest.sqlite`.
- [ ] Run the update script and inspect generated outputs.

### Task 5: GitHub Automation

**Files:**
- Create: `.github/workflows/update.yml`

- [ ] Add workflow triggers for `push`, daily schedule, and `workflow_dispatch`.
- [ ] Run update pipeline in CI, upload Pages artifact, and deploy GitHub Pages.
- [ ] Keep workflow polite: low frequency, public URLs only, no login bypassing, and failure artifacts/status.

### Task 6: Publish

**Files:**
- Modify generated project files as needed.

- [ ] Run full local verification: `python -m pytest` and `python scripts/update_dataset.py`.
- [ ] Commit intended files without raw PDFs.
- [ ] Create public GitHub repository with `gh repo create`.
- [ ] Push `main`.
- [ ] Confirm remote repository and generated data/demo files are visible.

