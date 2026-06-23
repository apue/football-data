# Editorial V2 AI Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the editorial v1 deterministic final-selection workflow with an editorial v2 pipeline where deterministic scoring builds rankings/candidate pools and an AI selector makes the final bounded editorial choices.

**Architecture:** Keep the dataset pipeline stable. Add focused editorial v2 modules for registry loading, evidence/rankings, candidate pool creation, AI selection, validation, copy generation, artifacts, and queue execution. Preserve public Pages outputs (`site/editorial/latest.json`, dated `choices.json`, `site/index.html`) while keeping rich audit artifacts local/Actions-facing.

**Tech Stack:** Python 3.11+, SQLite, PyMuPDF data already in `data/latest.sqlite`, OpenAI Agents SDK through the existing thin client boundary, pytest, GitHub Actions, static GitHub Pages output.

## Global Constraints

- Do not modify the reproducible PMSR discovery/extract/database/timeline pipeline unless required for editorial v2 integration.
- Score is not the final selector; it only builds rankings, candidate pools, and diagnostics.
- AI final selection must be bounded to the candidate pool and must emit structured reasons for selected and skipped higher-ranked candidates.
- Public homepage should only show final editorial results, not experiment/audit internals.
- Audit artifacts must include rankings, candidate pool, selector input, selection decision, selection validation, and run manifest.
- Do not build a generic workflow platform or re-abstract OpenAI Agents SDK provider/runtime capabilities.
- Use tests-first for behavior changes.

---

### Task 1: Editorial V2 Registry And Candidate Configuration

**Files:**
- Create: `config/editorial/production.json`
- Create: `config/editorial/experiments/ai_rerank_baseline_v1.json`
- Create: `config/editorial/candidate_pools/rich_packet_v1.json`
- Create: `config/editorial/selector_profiles/strict_editor_v1.json`
- Create: `config/editorial/copy_profiles/zh_natural_v1.json`
- Create: `config/editorial/copy_profiles/en_plain_v1.json`
- Create: `football_data/editorial_registry.py`
- Test: `tests/test_editorial_v2.py`

**Interfaces:**
- Produces: `load_editorial_experiment(experiment_id: str | None = None, config_dir: str | Path = "config/editorial") -> dict[str, Any]`
- Produces: `load_candidate_pool_config(pool_id: str, config_dir: str | Path = "config/editorial") -> dict[str, Any]`
- Produces: `load_selector_profile(profile_id: str, config_dir: str | Path = "config/editorial") -> dict[str, Any]`
- Produces: `load_copy_profile(profile_id: str, config_dir: str | Path = "config/editorial") -> dict[str, Any]`

- [ ] **Step 1: Write failing registry tests**

Add tests that assert the default production experiment resolves to `ai_rerank_baseline_v1`, references `workflow_variant = ai_rerank_selection_v1`, and resolves candidate/selector/copy profiles.

- [ ] **Step 2: Run registry tests to verify they fail**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: FAIL because `football_data.editorial_registry` does not exist.

- [ ] **Step 3: Implement registry files and loader**

Create the JSON config files and `football_data/editorial_registry.py` with strict file lookup, JSON parsing, `id` validation, and helpful `ValueError` messages.

- [ ] **Step 4: Run registry tests to verify they pass**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: PASS.

### Task 2: Rankings And Candidate Pool

**Files:**
- Create: `football_data/editorial_rankings.py`
- Create: `football_data/editorial_candidates.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: `load_candidate_pool_config`
- Produces: `build_editorial_rankings(db_path: str | Path, match_date: str, scoring_config_path: str | Path) -> dict[str, Any]`
- Produces: `build_candidate_pool(rankings: dict[str, Any], pool_config: dict[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing rankings/candidate tests**

Assert rankings include `players`, `match_date`, `scoring_version`, `rankings.headline`, and score components. Assert candidate pool contains `selectable_candidates`, `near_misses`, `pool_reasons`, and does not rely on final deterministic choices.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: FAIL because modules/functions do not exist.

- [ ] **Step 3: Implement rankings using existing scoring helpers**

Reuse existing `_load_scoring_config`, `_player_rows_for_date`, `_score_player`, `build_match_flows`, and `player_flow_impacts`. Return public dictionaries with stable player ids based on `match_key/team/player_no`.

- [ ] **Step 4: Implement candidate pool**

Include headline top N, role top N, impact candidates, goalkeeper candidates, hidden gem candidates, and near misses. Preserve full rank and score component metadata for audit.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: PASS.

### Task 3: AI Rerank Selector And Validation

**Files:**
- Create: `football_data/editorial_selection.py`
- Create: `football_data/editorial_validation.py`
- Create: `football_data/llm_client.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: `candidate_pool`
- Produces: `build_selector_input(candidate_pool: dict[str, Any], experiment: dict[str, Any], *, shuffle_seed: str | None = None) -> dict[str, Any]`
- Produces: `run_ai_rerank_selector(selector_input: dict[str, Any], text_client: AgentTextClient, profile: dict[str, Any]) -> dict[str, Any]`
- Produces: `validate_selection_decision(decision: dict[str, Any], candidate_pool: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing selector tests**

Test that fake selector output can choose from a candidate pool, that selected player ids must exist in `selectable_candidates`, and that skipped higher-ranked candidates are required when a lower-ranked POTD is selected.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: FAIL because selection modules do not exist.

- [ ] **Step 3: Implement selector input and fake-friendly selector call**

Use existing `AgentTextClient` for calls. Keep OpenAI SDK usage inside the existing client. Add a deterministic fallback/fake mode for tests.

- [ ] **Step 4: Implement validation**

Validate candidate-pool membership, slot counts, duplicate player ids, required skipped-higher-ranked explanations, and evidence id shape.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_editorial_v2.py -q`
Expected: PASS.

### Task 4: V2 Copy, Artifacts, Runner, And Homepage Integration

**Files:**
- Create: `football_data/editorial_copy.py`
- Create: `football_data/editorial_artifacts.py`
- Create: `football_data/editorial_v2_runner.py`
- Create: `scripts/run_editorial_v2.py`
- Modify: `football_data/editorial_queue_runner.py`
- Modify: `scripts/run_editorial_queue.py`
- Modify: `football_data/demo.py`
- Modify: `tests/test_editorial_queue_runner.py`
- Modify: `tests/test_demo.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Produces: `run_editorial_v2(...) -> dict[str, Any]`
- Produces public artifacts: dated `choices.json`, `index.html`, `latest.json`, Markdown report, `manifests/editorial-v2-run.json`
- Produces audit artifacts under `agent-runs/YYYY-MM-DD/`

- [ ] **Step 1: Write failing runner/homepage tests**

Test `run_editorial_v2(..., fake=True, research=False)` writes public choices and audit files. Test homepage editorial section renders v2 output in the existing Editor's Choices area.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_editorial_v2.py tests/test_demo.py tests/test_editorial_queue_runner.py -q`
Expected: FAIL because runner and artifacts do not exist.

- [ ] **Step 3: Implement copy generation**

Generate copy from `selection_decision`; fake mode uses deterministic publishable text. Real mode uses the thin OpenAI Agents SDK text client and copy profiles.

- [ ] **Step 4: Implement artifacts**

Write public artifacts compatible with existing demo rendering, and audit artifacts with rankings/candidate/selector/validation data.

- [ ] **Step 5: Implement runner and CLI**

Wire registry -> rankings -> candidate pool -> selector -> validation -> copy -> artifacts -> homepage rebuild. Add queue support to call v2 by default.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/test_editorial_v2.py tests/test_demo.py tests/test_editorial_queue_runner.py -q`
Expected: PASS.

### Task 5: Actions, Docs, Cleanup, And Verification

**Files:**
- Modify: `.github/workflows/editorial.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CHANGELOG.md`
- Modify: tests that encode old v1-only assumptions

**Interfaces:**
- Actions production path runs v2.
- Manual dispatch can pass `match_date` and `fake`.
- Upload artifacts include `manifests/editorial-v2-run.json` and `agent-runs/**`.

- [ ] **Step 1: Write or update workflow/docs tests**

Update workflow tests to require `scripts/run_editorial_v2.py` or v2 queue path and v2 env names.

- [ ] **Step 2: Run workflow/docs tests to verify they fail**

Run: `uv run pytest tests/test_editorial_workflow.py tests/test_project_skill.py -q`
Expected: FAIL before docs/workflow updates.

- [ ] **Step 3: Update Actions and docs**

Switch editorial workflow to v2-compatible queue/runner, upload v2 artifacts, and document the new AI rerank selection model.

- [ ] **Step 4: Run local end-to-end**

Run: `python scripts/update_dataset.py`
Run: `python scripts/run_editorial_v2.py --date <latest-data-date> --fake --no-research --json`
Run: `uv run pytest`
Expected: PASS.

- [ ] **Step 5: Push branch, open PR, run Actions**

Push branch, create PR, trigger relevant workflows, inspect failures, and fix until green.
