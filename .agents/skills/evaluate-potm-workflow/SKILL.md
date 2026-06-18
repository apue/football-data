---
name: evaluate-potm-workflow
description: Use when evaluating football-data POTM evidence quality, Firecrawl/Keypool candidate discovery, calibration readiness, source quality, noise ratio, or whether Editor's Choices can safely use current weak-label signals.
---

# Evaluate POTM Workflow

## Overview

Use this workflow to run deterministic quality checks on POTM evidence discovery and model-alignment readiness. The evaluation judges process quality; it does not select players or change scoring weights.

## Required Reference

Read `references/workflow.md` before running or interpreting an evaluation.

## Core Rules

- POTM is a weak label; evaluate it as a sanity check, not ground truth.
- Use Firecrawl and Keypool only when discovery is requested or evidence is missing.
- Prefer `scripts/evaluate_potm_workflow.py` over ad hoc manual scoring.
- Treat `calibration/evaluation/YYYY-MM-DD.md` as the human review surface.
- Do not change scoring weights from one evaluation. Look for repeated findings across match days.
