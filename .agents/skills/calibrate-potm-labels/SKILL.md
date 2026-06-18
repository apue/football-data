---
name: calibrate-potm-labels
description: Use when auditing football-data scoring weights against FIFA Player of the Match labels, finding POTM evidence with Firecrawl or Keypool, investigating rank misses, or preparing calibration reports before Editor's Choices publication.
---

# Calibrate POTM Labels

## Overview

Use this workflow to compare the repository scoring model with external Player of the Match evidence. Firecrawl helps discover candidate sources; confirmed labels become weak labels for calibration reports, not direct scoring inputs.

## Required Reference

Read `references/workflow.md` before changing labels, reports, or scoring weights.

## Core Rules

- POTM is a weak label. It can trigger review and weight experiments, but it is not ground truth.
- Use Firecrawl and Keypool for discovery only; verify source context before adding a label.
- Do not use POTM as a scoring input in Editor's Choices.
- Prefer cumulative evidence over single-match reactions when proposing weight changes.
- Keep `.env.local` local. Never commit `KEYPOOL_KEY`.
- Run `scripts/calibrate_potm.py` after label changes and before changing scoring config.
