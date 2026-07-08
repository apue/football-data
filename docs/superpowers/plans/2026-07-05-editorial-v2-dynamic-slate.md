# Editorial V2 Dynamic Slate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a shadow `bounded_editorial_loop_v2` experiment that keeps the current deterministic editorial pipeline but changes slate sizing and review pressure so low-match-count days do not force weak public cards.

**Architecture:** Keep the current local Codex runtime and artifact workflow. Add shared deterministic slate policy helpers, wire them into selector input, selection validation, selection review payloads, and test helpers, then add v2 registry/profile config without switching `production.active_experiment`. Generate v2 artifacts under `agent-runs-ab/bounded_editorial_loop_v2/YYYY-MM-DD/` so v1 public outputs remain the control.

**Tech Stack:** Python 3.11, pytest, JSON config registry, local Codex artifact workflow, SQLite-backed deterministic data.

**Implementation status:** Completed on 2026-07-05. V2 shadow artifacts were generated under `agent-runs-ab/bounded_editorial_loop_v2/`, independent compiled previews were written under `agent-runs-ab/bounded_editorial_loop_v2/compiled_site/` and `agent-runs-ab/bounded_editorial_loop_v2/compiled_reports/`, and self-evaluation was written under `agent-runs-ab/bounded_editorial_loop_v2/comparison/`. Verification passed with `uv run pytest -q`, targeted `uv run ruff check ...`, and the examples SQL smoke loop.

## Global Constraints

- Do not change `config/editorial/production.json` active experiment in this task.
- Do not replace `scripts/prepare_editorial_packet.py`, `scripts/promote_editorial_loop.py`, or `scripts/compile_local_editorial.py`.
- Do not introduce OpenAI API or Agents SDK runtime dependencies.
- Keep selection, copy, validation, promotion, and static compilation artifact-compatible with the current local Codex workflow.
- New v2 outputs must be generated as shadow artifacts under `agent-runs-ab/bounded_editorial_loop_v2/`, not promoted over the existing v1 public site unless explicitly requested.
- The current public award types remain `player_of_the_day` and `impact_pick`.
- Progression, defensive, goalkeeper, and hidden-gem metrics remain audit/supporting evidence only.
- For one-match days, v2 recommends one public card and allows a second only for an independently strong public case.

---

## File Structure

- Create `football_data/editorial_slate.py`: shared slate count policy functions used by validation, review payloads, selector input, and tests.
- Modify `football_data/editorial_candidates.py`: include deterministic `matches` and `match_count` in `candidate_pool.json`.
- Modify `football_data/editorial_selection.py`: expose `public_card_count_context` in `selector_input.json`.
- Modify `football_data/editorial_validation.py`: validate selected count using the shared dynamic slate policy.
- Modify `football_data/editorial_loop.py`: use the shared dynamic slate policy when building review payloads and card-count challenger pressure.
- Modify `tests/editorial_test_helpers.py`: use the shared dynamic slate policy for v2 test selections.
- Modify `tests/test_editorial_v2.py`: preserve v1 assertions and add v2 dynamic slate regression tests.
- Create `config/editorial/experiments/bounded_editorial_loop_v2.json`: shadow experiment config.
- Create `config/editorial/selector_profiles/slate_dynamic_editor_v4.json`: v2 selector profile with slate plan and low-match-count guidance.
- Create `config/editorial/selection_review_profiles/selection_review_v2.json`: v2 review profile requiring slate-plan critique and revision target clarity.
- Create shadow run artifacts under `agent-runs-ab/bounded_editorial_loop_v2/2026-07-02`, `2026-07-03`, and `2026-07-04`.
- Create self-evaluation artifacts under `agent-runs-ab/bounded_editorial_loop_v2/comparison/`.

---

### Task 1: Shared Slate Count Policy

**Files:**
- Create: `football_data/editorial_slate.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: `selection_config: dict[str, Any]`, `candidate_pool: dict[str, Any]`
- Produces:
  - `match_count_for_candidate_pool(candidate_pool: dict[str, Any]) -> int`
  - `public_card_count_context(candidate_pool: dict[str, Any], selection_config: dict[str, Any]) -> dict[str, Any]`
  - `selection_public_card_count(candidate_pool: dict[str, Any], selection_config: dict[str, Any]) -> tuple[int, int] | None`

- [x] **Step 1: Write failing tests**

Add tests to `tests/test_editorial_v2.py`:

```python
def test_editorial_v2_dynamic_public_card_count_policy():
    from football_data.editorial_slate import (
        public_card_count_context,
        selection_public_card_count,
    )

    selection_config = {
        "public_card_count": {
            "min": 1,
            "max": 6,
            "match_count_rules": [
                {
                    "min_matches": 1,
                    "max_matches": 1,
                    "min": 1,
                    "recommended": 1,
                    "max": 2,
                    "guidance": "One match should normally produce one public card.",
                },
                {
                    "min_matches": 2,
                    "max_matches": 2,
                    "min": 2,
                    "recommended": 3,
                    "max": 4,
                    "guidance": "Two matches can support two to four cards.",
                },
                {
                    "min_matches": 3,
                    "max_matches": 3,
                    "min": 3,
                    "recommended": 4,
                    "max": 5,
                    "guidance": "Three matches can support three to five cards.",
                },
                {
                    "min_matches": 4,
                    "min": 3,
                    "recommended": 4,
                    "max": 6,
                    "guidance": "Four or more matches keep the broad slate range.",
                },
            ],
        }
    }

    one_match_pool = {
        "match_count": 1,
        "selectable_candidates": [{"match_key": "m1", "player_id": "a"}],
    }
    two_match_pool = {
        "selectable_candidates": [
            {"match_key": "m1", "player_id": "a"},
            {"match_key": "m2", "player_id": "b"},
        ]
    }
    four_match_pool = {
        "matches": [{"match_key": f"m{i}"} for i in range(4)],
        "selectable_candidates": [],
    }

    assert selection_public_card_count(one_match_pool, selection_config) == (1, 2)
    assert public_card_count_context(one_match_pool, selection_config) == {
        "selected": 0,
        "match_count": 1,
        "min": 1,
        "recommended": 1,
        "max": 2,
        "policy": "match_count_rule",
        "guidance": "One match should normally produce one public card.",
    }
    assert selection_public_card_count(two_match_pool, selection_config) == (2, 4)
    assert selection_public_card_count(four_match_pool, selection_config) == (3, 6)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_v2_dynamic_public_card_count_policy -q`

Expected: FAIL with `ModuleNotFoundError` or missing function import.

- [x] **Step 3: Implement `football_data/editorial_slate.py`**

Create:

```python
from __future__ import annotations

from typing import Any


def match_count_for_candidate_pool(candidate_pool: dict[str, Any]) -> int:
    raw_count = candidate_pool.get("match_count")
    if raw_count is not None:
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return count

    matches = candidate_pool.get("matches")
    if isinstance(matches, list):
        keys = {
            str(item.get("match_key") or item.get("match_no") or item)
            for item in matches
            if str(item.get("match_key") if isinstance(item, dict) else item).strip()
        }
        if keys:
            return len(keys)

    keys: set[str] = set()
    for group_name in ("selectable_candidates", "audit_candidates", "near_misses"):
        for item in candidate_pool.get(group_name, []):
            if isinstance(item, dict):
                key = str(item.get("match_key") or "")
                if key.strip():
                    keys.add(key)
    return len(keys)


def selection_public_card_count(
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any],
) -> tuple[int, int] | None:
    context = public_card_count_context(candidate_pool, selection_config)
    min_count = int(context.get("min") or 0)
    max_count = int(context.get("max") or 0)
    if min_count <= 0 or max_count <= 0:
        return None
    if min_count > max_count:
        min_count, max_count = max_count, min_count
    return min_count, max_count


def public_card_count_context(
    candidate_pool: dict[str, Any],
    selection_config: dict[str, Any],
    *,
    selected_count: int = 0,
) -> dict[str, Any]:
    raw_count = selection_config.get("public_card_count")
    if not isinstance(raw_count, dict):
        return {
            "selected": selected_count,
            "match_count": match_count_for_candidate_pool(candidate_pool),
            "min": None,
            "recommended": None,
            "max": None,
            "policy": "none",
            "guidance": "",
        }

    match_count = match_count_for_candidate_pool(candidate_pool)
    rule = _matching_match_count_rule(raw_count, match_count)
    if rule:
        min_count = int(rule.get("min") or raw_count.get("min") or 0)
        max_count = int(rule.get("max") or raw_count.get("max") or 0)
        recommended = int(rule.get("recommended") or min_count or max_count or 0)
        policy = "match_count_rule"
        guidance = str(rule.get("guidance") or "")
    else:
        min_count = int(raw_count.get("min") or 0)
        max_count = int(raw_count.get("max") or 0)
        recommended = int(raw_count.get("recommended") or min_count or 0)
        policy = "static_range"
        guidance = str(raw_count.get("guidance") or "")

    if min_count > max_count:
        min_count, max_count = max_count, min_count
    return {
        "selected": selected_count,
        "match_count": match_count,
        "min": min_count,
        "recommended": recommended,
        "max": max_count,
        "policy": policy,
        "guidance": guidance,
    }


def _matching_match_count_rule(raw_count: dict[str, Any], match_count: int) -> dict[str, Any] | None:
    rules = raw_count.get("match_count_rules")
    if not isinstance(rules, list):
        return None
    for item in rules:
        if not isinstance(item, dict):
            continue
        min_matches = int(item.get("min_matches") or 0)
        max_matches_raw = item.get("max_matches")
        max_matches = int(max_matches_raw) if max_matches_raw is not None else None
        if match_count >= min_matches and (max_matches is None or match_count <= max_matches):
            return item
    return None
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_v2_dynamic_public_card_count_policy -q`

Expected: PASS.

---

### Task 2: Candidate Pool Match Metadata

**Files:**
- Modify: `football_data/editorial_candidates.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: `rankings["matches"]`
- Produces: `candidate_pool["matches"]` and `candidate_pool["match_count"]`

- [x] **Step 1: Write failing test**

Add test:

```python
def test_editorial_candidate_pool_exposes_match_count():
    from football_data.editorial_candidates import build_candidate_pool
    from football_data.editorial_rankings import build_editorial_rankings
    from football_data.editorial_registry import (
        load_candidate_pool_config,
        load_editorial_experiment,
    )

    experiment = load_editorial_experiment()
    rankings = build_editorial_rankings("data/latest.sqlite", "2026-07-04", experiment["scoring_config"])
    pool = build_candidate_pool(rankings, load_candidate_pool_config(experiment["candidate_pool"]))

    assert pool["match_count"] == len(rankings["matches"])
    assert pool["matches"] == [
        {
            "match_key": item["match_key"],
            "match_no": item["match_no"],
            "home_team": item["home_team"],
            "away_team": item["away_team"],
            "home_score": item["home_score"],
            "away_score": item["away_score"],
        }
        for item in rankings["matches"]
    ]
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_candidate_pool_exposes_match_count -q`

Expected: FAIL with missing `match_count`.

- [x] **Step 3: Implement match metadata**

In `build_candidate_pool`, before the return payload:

```python
    matches = [
        {
            "match_key": item.get("match_key"),
            "match_no": item.get("match_no"),
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
            "home_score": item.get("home_score"),
            "away_score": item.get("away_score"),
        }
        for item in rankings.get("matches", [])
        if isinstance(item, dict)
    ]
```

Add `"matches": matches` and `"match_count": len(matches)` to the returned candidate pool.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_candidate_pool_exposes_match_count -q`

Expected: PASS.

---

### Task 3: Wire Dynamic Slate Context Into Selection Inputs and Validators

**Files:**
- Modify: `football_data/editorial_selection.py`
- Modify: `football_data/editorial_validation.py`
- Modify: `football_data/editorial_loop.py`
- Modify: `tests/editorial_test_helpers.py`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: `public_card_count_context(candidate_pool, selection_config, selected_count=...)`
- Produces:
  - `selector_input["public_card_count_context"]`
  - `selection_review_payload["public_card_count"]` with `recommended`
  - validation warning text using the dynamic min/max range

- [x] **Step 1: Write failing tests**

Add test:

```python
def test_dynamic_public_card_count_validation_accepts_one_card_single_match():
    from football_data.editorial_validation import validate_selection_decision

    experiment = {
        "selection": {
            "public_card_count": {
                "min": 1,
                "max": 6,
                "match_count_rules": [
                    {"min_matches": 1, "max_matches": 1, "min": 1, "recommended": 1, "max": 2}
                ],
            },
            "award_limits": {"player_of_the_day": 6, "impact_pick": 2},
        }
    }
    candidate_pool = {
        "match_count": 1,
        "selectable_candidates": [
            {
                "player_id": "p1",
                "player_name": "Player One",
                "team": "A",
                "match_key": "m1",
                "eligible_awards": ["player_of_the_day"],
                "headline_rank": 1,
                "award_contexts": {
                    "player_of_the_day": {
                        "evidence_chips": {"en": ["Goal"], "zh": ["进球"]}
                    }
                },
            }
        ],
    }
    decision = {
        "selected": [
            {
                "player_id": "p1",
                "player_name": "Player One",
                "team": "A",
                "award_type": "player_of_the_day",
                "editorial_reason": "The decisive public case is supported by direct match impact.",
                "selection_risk": "Low: the one-card slate matches a one-match day.",
                "evidence_used": ["Goal"],
            }
        ],
        "skipped_higher_ranked": [],
    }

    assert validate_selection_decision(decision, candidate_pool, experiment)["status"] == "pass"
```

Add test:

```python
def test_selector_input_includes_public_card_count_context():
    from football_data.editorial_selection import build_selector_input

    pool = {
        "match_date": "2026-07-05",
        "scoring_version": "v0.4",
        "match_count": 1,
        "selectable_candidates": [],
        "audit_candidates": [],
        "near_misses": [],
    }
    experiment = {
        "workflow_variant": "bounded_selection_copy_loop_v2",
        "selection": {
            "public_card_count": {
                "min": 1,
                "max": 6,
                "match_count_rules": [
                    {"min_matches": 1, "max_matches": 1, "min": 1, "recommended": 1, "max": 2}
                ],
            }
        },
    }

    selector_input = build_selector_input(pool, experiment)

    assert selector_input["public_card_count_context"]["match_count"] == 1
    assert selector_input["public_card_count_context"]["recommended"] == 1
    assert selector_input["public_card_count_context"]["max"] == 2
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_editorial_v2.py::test_dynamic_public_card_count_validation_accepts_one_card_single_match \
  tests/test_editorial_v2.py::test_selector_input_includes_public_card_count_context \
  -q
```

Expected: at least one FAIL because validator still uses static count and selector input does not expose context.

- [x] **Step 3: Implement wiring**

Use imports:

```python
from football_data.editorial_slate import public_card_count_context, selection_public_card_count
```

Changes:

- `football_data/editorial_selection.py`: add top-level `"public_card_count_context": public_card_count_context(candidate_pool, experiment.get("selection", {}))`.
- `football_data/editorial_validation.py`: replace local `_selection_public_card_count(selection_config)` with `selection_public_card_count(candidate_pool, selection_config)`.
- `football_data/editorial_loop.py`: replace local static `_selection_public_card_count` and `_public_card_count_context` logic with shared helper.
- `tests/editorial_test_helpers.py`: use `public_card_count_context(candidate_pool, selection_config)["recommended"]` as the preferred target when available, clamped to the dynamic min/max range.

- [x] **Step 4: Run targeted tests**

Run:

```bash
uv run pytest \
  tests/test_editorial_v2.py::test_dynamic_public_card_count_validation_accepts_one_card_single_match \
  tests/test_editorial_v2.py::test_selector_input_includes_public_card_count_context \
  tests/test_editorial_v2.py::test_editorial_v2_selection_validation_rejects_bad_local_editor_output \
  -q
```

Expected: PASS.

---

### Task 4: Add V2 Experiment and Review Profiles

**Files:**
- Create: `config/editorial/experiments/bounded_editorial_loop_v2.json`
- Create: `config/editorial/selector_profiles/slate_dynamic_editor_v4.json`
- Create: `config/editorial/selection_review_profiles/selection_review_v2.json`
- Modify: `tests/test_editorial_v2.py`

**Interfaces:**
- Consumes: existing registry loaders
- Produces: a non-production v2 experiment resolvable by `--experiment bounded_editorial_loop_v2`

- [x] **Step 1: Write failing registry test**

Add:

```python
def test_editorial_v2_dynamic_experiment_registry():
    from football_data.editorial_registry import (
        load_editorial_experiment,
        load_selection_review_profile,
        load_selector_profile,
    )

    experiment = load_editorial_experiment("bounded_editorial_loop_v2")

    assert experiment["id"] == "bounded_editorial_loop_v2"
    assert experiment["workflow_variant"] == "bounded_selection_copy_loop_v2"
    assert experiment["selector_profile"] == "slate_dynamic_editor_v4"
    assert experiment["selection_review_profile"] == "selection_review_v2"
    assert experiment["selection"]["public_card_count"]["match_count_rules"][0] == {
        "min_matches": 1,
        "max_matches": 1,
        "min": 1,
        "recommended": 1,
        "max": 2,
        "guidance": "One-match days should normally publish one Player of the Match level card; add a second only for an independently strong public case.",
    }

    selector = load_selector_profile("slate_dynamic_editor_v4")
    review = load_selection_review_profile("selection_review_v2")
    assert any("slate_plan" in item for item in selector["instructions"])
    assert "slate_plan_verdict" in review["required_slate_assessment_fields"]
    assert "revision_target" in review["required_slate_assessment_fields"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_v2_dynamic_experiment_registry -q`

Expected: FAIL with missing experiment/profile files.

- [x] **Step 3: Add config files**

Create `bounded_editorial_loop_v2.json` with:

```json
{
  "id": "bounded_editorial_loop_v2",
  "workflow_variant": "bounded_selection_copy_loop_v2",
  "scoring_config": "config/scoring/v0.4.json",
  "candidate_pool": "guarded_packet_v2",
  "selector_profile": "slate_dynamic_editor_v4",
  "selection_review_profile": "selection_review_v2",
  "copy_review_profile": "copy_review_v1",
  "loop_policy": {
    "selection_max_rounds": 3,
    "copy_max_rounds": 3,
    "max_rounds_exceeded_status": "needs_human_review",
    "promotion_requires": [
      "selection_loop_pass",
      "copy_loop_pass",
      "deterministic_selection_validation_pass",
      "deterministic_copy_validation_pass"
    ]
  },
  "copy_profiles": {
    "zh": "zh_matchnote_light_emotion_v1",
    "en": "en_plain_v1"
  },
  "selection": {
    "mode": "bounded_loop_local_editor",
    "strategy": "overall_slate_v1",
    "public_card_count": {
      "min": 1,
      "max": 6,
      "match_count_rules": [
        {
          "min_matches": 1,
          "max_matches": 1,
          "min": 1,
          "recommended": 1,
          "max": 2,
          "guidance": "One-match days should normally publish one Player of the Match level card; add a second only for an independently strong public case."
        },
        {
          "min_matches": 2,
          "max_matches": 2,
          "min": 2,
          "recommended": 3,
          "max": 4,
          "guidance": "Two-match days should stay compact unless the fourth card is independently strong."
        },
        {
          "min_matches": 3,
          "max_matches": 3,
          "min": 3,
          "recommended": 4,
          "max": 5,
          "guidance": "Three-match days can support three to five cards, but the fifth must add clear reader value."
        },
        {
          "min_matches": 4,
          "min": 3,
          "recommended": 4,
          "max": 6,
          "guidance": "Four or more matches keep the broad slate range; the upper bound is still capacity, not a target."
        }
      ]
    },
    "award_limits": {
      "player_of_the_day": 6,
      "impact_pick": 2
    },
    "overall_slate_award_preference": [
      "player_of_the_day",
      "impact_pick"
    ],
    "slate_constraints": {
      "max_per_match": 3,
      "max_per_team": 3
    },
    "slate_balance": {
      "default_max_public_cards_per_match": 2,
      "award_types_are_angles_not_quotas": true,
      "angle_awards_can_be_omitted": ["impact_pick"],
      "third_card_requires": [
        "top_five_rank_cluster",
        "dominant_team_result",
        "independent_direct_contribution",
        "strong_supporting_metric_profile",
        "hat_trick",
        "late_match_winning_goal"
      ]
    },
    "must_explain_skipped_higher_ranked_candidates": true,
    "must_include_slate_plan": true
  },
  "shuffle_strategy": "name_sorted",
  "status": "shadow"
}
```

Create selector/review profiles using the existing v1 profiles as the base plus:

- selector requires `slate_plan` with match count, recommended card count, final card count, weakest selected card, strongest omitted/add-card challenger, and why the slate is not padded.
- review requires `slate_plan_verdict` and `revision_target`, and treats unresolved selector/critic conflict as blocking.

- [x] **Step 4: Run registry test**

Run: `uv run pytest tests/test_editorial_v2.py::test_editorial_v2_dynamic_experiment_registry -q`

Expected: PASS.

---

### Task 5: Preserve V1 and Run Full Verification

**Files:**
- Modify only files touched by Tasks 1-4.

**Interfaces:**
- Consumes: v1 default experiment and v2 shadow experiment
- Produces: passing unit suite

- [x] **Step 1: Run targeted editorial tests**

Run: `uv run pytest tests/test_editorial_v2.py tests/test_editorial_loop.py tests/test_editorial_local.py tests/test_editorial_comparison.py -q`

Expected: PASS.

- [x] **Step 2: Run full tests**

Run: `uv run pytest -q`

Expected: PASS.

- [x] **Step 3: Run SQL smoke**

Run: `for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done`

Expected: exit code 0.

---

### Task 6: Generate V2 Shadow Runs for 2026-07-02, 2026-07-03, and 2026-07-04

**Files:**
- Create/update shadow artifacts under `agent-runs-ab/bounded_editorial_loop_v2/YYYY-MM-DD/`
- Do not overwrite `agent-runs/YYYY-MM-DD/`, `site/editorial/YYYY-MM-DD/`, or public reports.

**Interfaces:**
- Consumes: v2 experiment via `--experiment bounded_editorial_loop_v2`
- Produces: promoted v2 loop artifacts suitable for comparison

- [x] **Step 1: Prepare packets and fact packs**

For each date:

```bash
uv run python scripts/prepare_editorial_packet.py \
  --date YYYY-MM-DD \
  --experiment bounded_editorial_loop_v2 \
  --agent-runs-dir agent-runs-ab/bounded_editorial_loop_v2 \
  --json
uv run python scripts/inspect_editorial_day.py \
  --date YYYY-MM-DD \
  --agent-runs-dir agent-runs-ab/bounded_editorial_loop_v2 \
  --json
```

Expected: `candidate_pool.json`, `selector_input.json`, and `editorial_fact_pack.json` exist in each shadow date directory.

- [x] **Step 2: Write selection/copy loop artifacts**

For each date, write:

- `selection_rounds/round_1/selection_decision.json`
- `selection_rounds/round_1/selection_review.json`
- `copy_rounds/round_1/copy.json`
- `copy_rounds/round_1/copy_review.json`

Use v2 slate sizing. If review blocks, write round 2 rather than editing round 1.

- [x] **Step 3: Promote each v2 loop**

For each date:

```bash
uv run python scripts/promote_editorial_loop.py \
  --date YYYY-MM-DD \
  --agent-runs-dir agent-runs-ab/bounded_editorial_loop_v2 \
  --json
```

Expected: `editorial_loop_summary.json` status is `success`.

- [x] **Step 4: Validate shadow artifacts without public compile**

Run a local Python check that loads each v2 `selection_decision.json`, `copy.json`, and `editorial_loop_summary.json`, then calls the same deterministic validation functions used by compile.

Expected: selection validation, copy validation, and loop validation all pass for all three dates.

---

### Task 7: Self-Evaluate V2 Against Current V1

**Files:**
- Create: `agent-runs-ab/bounded_editorial_loop_v2/comparison/self_evaluation.json`
- Create: `agent-runs-ab/bounded_editorial_loop_v2/comparison/self_evaluation.md`

**Interfaces:**
- Consumes: v1 canonical artifacts under `agent-runs/YYYY-MM-DD/` and v2 shadow artifacts under `agent-runs-ab/bounded_editorial_loop_v2/YYYY-MM-DD/`
- Produces: self-evaluation verdict before asking user for feedback

- [x] **Step 1: Compare each date**

For each date, compare:

- public card count
- selected player names
- strongest removed v1 card
- strongest added v2 card
- factual safety
- Chinese title/body style risk
- whether v2 is better, tied, or worse

- [x] **Step 2: Write self-evaluation artifacts**

Write JSON:

```json
{
  "schema_version": 1,
  "variant_id": "bounded_editorial_loop_v2",
  "dates": ["2026-07-02", "2026-07-03", "2026-07-04"],
  "overall_verdict": "better_or_not_worse",
  "date_verdicts": []
}
```

Write Markdown summary with enough detail for human review.

- [x] **Step 3: Notify the user**

Use macOS notification:

```bash
osascript -e 'display notification "V2 editorial shadow runs are ready for review." with title "football-data"'
```

Expected: notification appears after all implementation, generation, validation, and self-evaluation work is done.

---

## Self-Review

- Spec coverage: The plan covers v2 experiment design, dynamic card-count logic, selection/review context, validation, 7/2-7/4 regeneration, self-evaluation, and macOS notification.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: Shared helper names are fixed as `match_count_for_candidate_pool`, `public_card_count_context`, and `selection_public_card_count`; downstream tasks use the same names.
