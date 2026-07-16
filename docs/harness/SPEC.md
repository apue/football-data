# Editorial Award Calibration

## Goal

Separate whole-match Player of the Day judgment from decisive-moment Impact Pick judgment so one event is not rewarded repeatedly and assist creators receive the context of the goals they create.

## In Scope

- Deterministic scoring configuration and flow-derived impact features.
- Candidate and selection-review evidence for Player of the Day challengers.
- Selector and review instructions that distinguish whole-match value from decisive moments.
- Dynamic one-match-day card counts in the active experiment.
- Regression coverage for the 2026 World Cup semi-finals.

## Non-goals

- Changing PMSR or FIFA timeline extraction.
- Publishing or pushing editorial output.
- Treating progression, defensive, or goalkeeper roles as new public award labels.
- Hard-coding Rodri or Messi by name in production logic.

## Product Decisions

- Player of the Day evaluates the strongest whole-match performance.
- Impact Pick evaluates a high-leverage match event.
- Scores build the candidate set and evidence; the bounded editor makes the final editorial judgment.
- Ambiguous cases remain reviewable, but the review must compare the selected Player of the Day with explicit challengers.
