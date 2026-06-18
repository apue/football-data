# Workflow

Use this sequence when asked to publish or check Editor's Choices.

1. Inspect repository state:

```bash
git status --short
python scripts/check_status.py
```

2. Refresh data if the user asks for the latest available match day:

```bash
python scripts/update_dataset.py
```

3. Find available local match dates:

```bash
sqlite3 data/latest.sqlite \
  "select match_date, count(*) from matches group by match_date order by match_date;"
```

4. Generate editorial artifacts. Omit `--date` for the latest available local match date:

```bash
python scripts/generate_editorial.py --date YYYY-MM-DD
```

Outputs:

- `reports/editorial/YYYY-MM-DD.md`
- `site/editorial/YYYY-MM-DD/evidence.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html` is rebuilt by default so the homepage shows the latest cards.

Markdown is the human-readable source. `evidence.json` is the structured audit source. `choices.json` is compiled frontend data with rendered HTML.

5. Read `reports/editorial/YYYY-MM-DD.md`. Revise only the Markdown, and only when `evidence.json` or SQLite supports the wording.

6. If you revise Markdown, compile it back to frontend JSON/HTML:

```bash
python scripts/render_editorial.py --date YYYY-MM-DD
```

7. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

8. Follow `pr-policy.md` for publication.
