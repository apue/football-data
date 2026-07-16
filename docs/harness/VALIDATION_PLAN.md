# Validation Plan

## Validation Mode

Selected modes: regression-test, eval-driven, schema-check, smoke-test.

Reason: deterministic scoring and review contracts change, while final selection remains an editorial judgment.

Commands:

```bash
uv run pytest tests/test_match_flow.py tests/test_editorial_v2.py tests/test_editorial_loop.py -q
uv run pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

Pass criteria:

- Semi-final regression expectations pass.
- Review schema rejects missing Player of the Day comparisons.
- All existing tests and SQL examples pass.
- Production registry resolves v0.5 and dynamic loop v2.

Manual checks:

- Inspect 2026-07-14 and 2026-07-15 ranking deltas without overwriting existing audit artifacts.
- Confirm v0.4 and v1 remain loadable by explicit id/path.

Known gaps:

- No video-derived valuation or possession-value model is introduced.
